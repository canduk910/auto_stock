"""backtest_runs CRUD — 외부 MCP 백테스트 실행 영속화 (Phase 2).

테이블: ``backtest_runs`` (supabase/migrations/019).
PK: ``id`` (uuid 자동 생성). UNIQUE: (target_date, strategy_id, params_kind).

흐름:
1. ``insert_run(...)`` — status=queued 로 INSERT. 동일 키 중복은 None.
2. ``update_status(run_id, "running", mcp_job_id=...)`` — MCP 제출 직후.
3. ``update_status(run_id, "completed", metrics=...)`` — 폴 완료 시.
4. ``update_status(run_id, "failed", error_message=...)`` — 예외/타임아웃.

사이클 M1-2 (Supabase→RDS 이전 단계1 증분2): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존.

핵심 안전 원칙:
- 중복 INSERT 는 UNIQUE 충돌 → None 반환 (자문 사이클 재진입 안전).
- 운영 매매 흐름 영역 미침범. backtest 전용 모듈.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)

TABLE_NAME = "backtest_runs"


def _now_iso() -> str:
    """사이클 68 G-9 — KST ISO 문자열 반환 (UTC 폐기)."""
    return now_kst_iso()


async def insert_run(
    target_date: date,
    strategy_id: str,
    params_kind: str,
    params_snapshot: dict[str, Any],
) -> Optional[dict]:
    """backtest_runs 1 row INSERT (status=queued).

    동일 ``(target_date, strategy_id, params_kind)`` 가 이미 있으면 UNIQUE 충돌 → None.
    Phase 3 의 ``_enqueue_backtest_jobs`` 가 자문 사이클 재진입 시 멱등하게 처리.
    """
    if params_kind not in ("current", "recommended"):
        raise ValueError(
            f"params_kind 는 'current' 또는 'recommended' — 입력: {params_kind!r}"
        )

    # M6 — target_date DATE 컬럼 바인딩. str 입력도 date 로 강제 변환.
    bound_target_date = to_date(target_date)

    # 중복 키 사전 차단
    existing = await pg.fetch(
        """
        SELECT id FROM backtest_runs
        WHERE target_date = $1 AND strategy_id = $2 AND params_kind = $3
        """,
        bound_target_date,
        strategy_id,
        params_kind,
    )
    if existing:
        logger.info(
            "backtest_runs 중복 — skip: target_date=%s strategy=%s kind=%s",
            target_date, strategy_id, params_kind,
        )
        return None

    run_id = str(uuid.uuid4())
    sql = """
        INSERT INTO backtest_runs (
            id, target_date, strategy_id, params_kind, params_snapshot,
            metrics, status, mcp_job_id, error_message, created_at, completed_at
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11)
        RETURNING *
    """
    try:
        row = await pg.fetchrow(
            sql,
            run_id,
            bound_target_date,
            strategy_id,
            params_kind,
            dict(params_snapshot or {}),
            None,
            "queued",
            None,
            None,
            datetime.fromisoformat(now_kst_iso()),
            None,
        )
    except Exception as e:
        msg = str(e).lower()
        # PostgreSQL 23505 = unique_violation (운영 응답)
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            logger.warning(
                "backtest_runs UNIQUE 충돌 (race): %s/%s/%s",
                target_date, strategy_id, params_kind,
            )
            return None
        logger.exception("backtest_runs INSERT 실패: %s/%s", strategy_id, target_date)
        return None
    if row:
        logger.info(
            "[backtest_runs] insert: %s/%s/%s id=%s",
            target_date, strategy_id, params_kind, run_id[:8],
        )
        return row
    return None


async def get_by_id(run_id: str) -> Optional[dict]:
    """단일 run 조회."""
    return await pg.fetchrow(
        "SELECT * FROM backtest_runs WHERE id = $1 LIMIT 1",
        run_id,
    )


async def list_by_date(target_date: date) -> list[dict]:
    """특정 영업일의 모든 run 반환 (전략 × kind = 최대 12 row)."""
    rows = await pg.fetch(
        "SELECT * FROM backtest_runs WHERE target_date = $1",
        to_date(target_date),
    )
    return list(rows or [])


async def update_status(
    run_id: str,
    status: str,
    *,
    mcp_job_id: Optional[str] = None,
    error_message: Optional[str] = None,
    metrics: Optional[dict] = None,
) -> dict:
    """status 갱신 + completed/failed 시 completed_at 자동 기록.

    - ``running``: mcp_job_id 부여 (MCP 제출 직후).
    - ``completed``: metrics 첨부 + completed_at.
    - ``failed``: error_message + completed_at.
    - ``skipped``: YAML DSL 미지원 전략. completed_at 기록.
    """
    if status not in ("queued", "running", "completed", "failed", "skipped"):
        raise ValueError(f"unknown status: {status!r}")

    set_clauses: list[str] = ["status = $1"]
    args: list[Any] = [status]

    if mcp_job_id is not None:
        args.append(mcp_job_id)
        set_clauses.append(f"mcp_job_id = ${len(args)}")
    if error_message is not None:
        args.append(error_message)
        set_clauses.append(f"error_message = ${len(args)}")
    if metrics is not None:
        args.append(dict(metrics))
        set_clauses.append(f"metrics = ${len(args)}::jsonb")
    if status in ("completed", "failed", "skipped"):
        args.append(datetime.fromisoformat(now_kst_iso()))
        set_clauses.append(f"completed_at = ${len(args)}")

    args.append(run_id)
    sql = f"""
        UPDATE backtest_runs SET {", ".join(set_clauses)}
        WHERE id = ${len(args)}
        RETURNING *
    """
    row = await pg.fetchrow(sql, *args)
    run_id_short = str(run_id)[:8]
    if not row:
        logger.warning("backtest_runs update_status 적용 row 0건: id=%s", run_id_short)
        return {}
    logger.info("[backtest_runs] update: id=%s status=%s", run_id_short, status)
    return row
