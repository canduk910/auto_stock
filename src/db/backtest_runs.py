"""backtest_runs CRUD — 외부 MCP 백테스트 실행 영속화 (Phase 2).

테이블: ``backtest_runs`` (supabase/migrations/019).
PK: ``id`` (uuid 자동 생성). UNIQUE: (target_date, strategy_id, params_kind).

흐름:
1. ``insert_run(...)`` — status=queued 로 INSERT. 동일 키 중복은 None.
2. ``update_status(run_id, "running", mcp_job_id=...)`` — MCP 제출 직후.
3. ``update_status(run_id, "completed", metrics=...)`` — 폴 완료 시.
4. ``update_status(run_id, "failed", error_message=...)`` — 예외/타임아웃.

핵심 안전 원칙:
- supabase 동기 SDK 호출은 모두 ``asyncio.to_thread`` 위임 (src/db/CLAUDE.md 규약).
- 중복 INSERT 는 UNIQUE 충돌 → None 반환 (자문 사이클 재진입 안전).
- 운영 매매 흐름 영역 미침범. backtest 전용 모듈.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from src.db.supabase import supabase

logger = logging.getLogger(__name__)

TABLE_NAME = "backtest_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    # 중복 키 사전 차단 (FakeSupabase 호환 — supabase-py 도 동일 UNIQUE 에러 반환)
    existing = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME)
        .select("id")
        .eq("target_date", target_date.isoformat())
        .eq("strategy_id", strategy_id)
        .eq("params_kind", params_kind)
        .execute()
    )
    if existing.data:
        logger.info(
            "backtest_runs 중복 — skip: target_date=%s strategy=%s kind=%s",
            target_date, strategy_id, params_kind,
        )
        return None

    row = {
        "id": str(uuid.uuid4()),
        "target_date": target_date.isoformat(),
        "strategy_id": strategy_id,
        "params_kind": params_kind,
        "params_snapshot": dict(params_snapshot or {}),
        "metrics": None,
        "status": "queued",
        "mcp_job_id": None,
        "error_message": None,
        "created_at": _now_iso(),
        "completed_at": None,
    }
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME).insert(row).execute()
        )
    except Exception as e:
        msg = str(e).lower()
        # PostgreSQL 23505 = unique_violation (운영 supabase 응답)
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            logger.warning(
                "backtest_runs UNIQUE 충돌 (race): %s/%s/%s",
                target_date, strategy_id, params_kind,
            )
            return None
        logger.exception("backtest_runs INSERT 실패: %s/%s", strategy_id, target_date)
        return None
    if result.data:
        logger.info(
            "[backtest_runs] insert: %s/%s/%s id=%s",
            target_date, strategy_id, params_kind, row["id"][:8],
        )
        return result.data[0]
    return None


async def get_by_id(run_id: str) -> Optional[dict]:
    """단일 run 조회."""
    result = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME)
        .select("*")
        .eq("id", run_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


async def list_by_date(target_date: date) -> list[dict]:
    """특정 영업일의 모든 run 반환 (전략 × kind = 최대 12 row)."""
    result = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME)
        .select("*")
        .eq("target_date", target_date.isoformat())
        .execute()
    )
    return list(result.data or [])


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

    patch: dict[str, Any] = {"status": status}
    if mcp_job_id is not None:
        patch["mcp_job_id"] = mcp_job_id
    if error_message is not None:
        patch["error_message"] = error_message
    if metrics is not None:
        patch["metrics"] = dict(metrics)
    if status in ("completed", "failed", "skipped"):
        patch["completed_at"] = _now_iso()

    result = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME).update(patch).eq("id", run_id).execute()
    )
    if not result.data:
        logger.warning("backtest_runs update_status 적용 row 0건: id=%s", run_id[:8])
        return {}
    logger.info("[backtest_runs] update: id=%s status=%s", run_id[:8], status)
    return result.data[0]
