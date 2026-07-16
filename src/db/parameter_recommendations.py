"""parameter_recommendations CRUD — OpenAI 기반 파라미터 추천 영속화.

사이클 M3a (Supabase→RDS 이전 단계3, 분석·관찰 비 hot-path): supabase-py → `src.db.pg`
(asyncpg) 전환. 함수 시그니처·반환형·graceful 100% 보존 — 호출부(recommendation_engine 등)
diff 0.

영속 의무:
- (target_date, strategy_id) UNIQUE(부분 인덱스 pending) 충돌 → None (duplicate/unique/23505 분기).
- JSONB(current_params/recommended_params/metrics/backtest_summary) dict 직접 바인딩(codec).
- TIMESTAMPTZ(created_at/applied_at/rejected_at) = datetime 바인딩(M1 패턴 2, str 금지).
- NUMERIC nullable(recommended_weight/applied_weight) — None 바인딩 허용.
- status ENUM 보존 (pending/applied/partial/rejected/expired/applied_auto).
"""

from __future__ import annotations

import asyncio  # noqa: F401 — Red autouse fixture 호환(monkeypatch.setattr(pr.asyncio, ...))
import logging
from datetime import date, datetime, timezone, timedelta

import src.db.pg as pg
from src.db._kst import KST, now_kst_iso, today_kst

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_TABLE = "parameter_recommendations"


async def insert_recommendation(
    target_date: date,
    strategy_id: str,
    current_params: dict,
    recommended_params: dict,
    reasoning: str,
    metrics: dict,
    recommended_weight: float | None = None,
    code_review_notes: str | None = None,
    weight_reasoning: str | None = None,
) -> dict | None:
    """파라미터 추천을 INSERT한다.

    Phase J4 (2026-05-12) — 신규 컬럼 3종 지원:
      - recommended_weight: AI 추천 전략 weight (0.0~1.0), null = 변경 권고 없음
      - code_review_notes: 로직/파라미터 자유 텍스트 자문, null = 변경 권고 없음
      - applied_weight: INSERT 시점은 항상 None (apply 시점에 채워짐)

    사이클 1 (2026-05-17) — weight_reasoning 추가:
      - weight_reasoning: 비중 변경 권고 사유 (별도 필드, 최대 1000자).
        recommended_weight 가 null 이면 weight_reasoning 도 null.
        J4 의 통합 `reasoning` 에 묻혀 있던 비중 사유를 UI 자산 배정 카드에서
        amber 배경 영역으로 분리 강조하기 위함.

    동일 (target_date, strategy_id) 조합이 unique index에 의해 거부되면 None 반환.
    """
    sql = f"""
        INSERT INTO {_TABLE} (
            target_date, strategy_id, current_params, recommended_params,
            reasoning, metrics, status, recommended_weight, code_review_notes,
            weight_reasoning, applied_weight, created_at
        ) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6::jsonb, $7, $8, $9, $10, $11, $12)
        RETURNING *
    """
    args = (
        target_date,
        strategy_id,
        current_params,
        recommended_params,
        reasoning,
        metrics,
        "pending",
        recommended_weight,
        code_review_notes,
        weight_reasoning,
        None,
        datetime.fromisoformat(now_kst_iso()),
    )
    try:
        row = await pg.fetchrow(sql, *args)
        if row:
            logger.info(
                "파라미터 추천 INSERT: %s (%s, 추천 %d개)",
                strategy_id, target_date, len(recommended_params),
            )
            return row
        return None
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            logger.warning(
                "파라미터 추천 중복 — 이미 존재함: %s (%s)", strategy_id, target_date,
            )
            return None
        logger.exception("파라미터 추천 INSERT 실패: %s", strategy_id)
        return None


async def list_recommendations(days: int = 30) -> list[dict]:
    """최근 N일의 추천 목록을 created_at 내림차순으로 반환."""
    cutoff = today_kst() - timedelta(days=days)
    rows = await pg.fetch(
        f"SELECT * FROM {_TABLE} WHERE target_date >= $1 ORDER BY created_at DESC",
        cutoff,
    )
    return rows or []


async def get_recommendation(rec_id: str) -> dict | None:
    """단일 추천 레코드를 조회한다."""
    row = await pg.fetchrow(f"SELECT * FROM {_TABLE} WHERE id = $1", rec_id)
    return row


async def update_recommendation_status(
    rec_id: str,
    status: str,
    applied_params: dict | None = None,
    applied_weight: float | None = None,
) -> dict:
    """추천 레코드의 status를 갱신한다.

    Phase J4 (2026-05-12): `applied_weight` 키워드로 실제 적용된 weight 트래킹.

    applied/partial 셋 시 applied_at, rejected 셋 시 rejected_at 자동 기록.
    """
    now_dt = datetime.now(KST)
    set_clauses = ["status = $2"]
    args: list = [rec_id, status]
    idx = 3

    if status in ("applied", "partial", "applied_auto"):
        # 사이클 23: applied_auto 는 자동 적용 전용 (운영자 수동 'applied' 와 분리)
        set_clauses.append(f"applied_at = ${idx}")
        args.append(now_dt)
        idx += 1
        if applied_params is not None:
            set_clauses.append(f"applied_params = ${idx}::jsonb")
            args.append(applied_params)
            idx += 1
        if applied_weight is not None:
            set_clauses.append(f"applied_weight = ${idx}")
            args.append(applied_weight)
            idx += 1
    elif status == "rejected":
        set_clauses.append(f"rejected_at = ${idx}")
        args.append(now_dt)
        idx += 1

    sql = f"UPDATE {_TABLE} SET {', '.join(set_clauses)} WHERE id = $1 RETURNING *"
    row = await pg.fetchrow(sql, *args)
    logger.info("파라미터 추천 상태 갱신: %s -> %s", rec_id, status)
    return row or {}


async def update_backtest_summary(
    rec_id: str,
    summary: dict,
) -> dict:
    """Phase 3 (2026-05-16) — `backtest_summary` JSONB 컬럼 단일 row 갱신.

    `summary` 구조:
        {
          "current":     { "<strategy_id>": { 8 metrics } | None, ... },
          "recommended": { "<strategy_id>": { 8 metrics } | None, ... },
          "diff":        { "<strategy_id>": { "<key>": <delta>, ... }, ... }
        }

    적용 row 0건 (미존재 ID) 이면 빈 dict 반환 — 예외 전파 안 함.
    """
    try:
        row = await pg.fetchrow(
            f"UPDATE {_TABLE} SET backtest_summary = $2::jsonb WHERE id = $1 RETURNING *",
            rec_id, dict(summary or {}),
        )
    except Exception:
        logger.exception("backtest_summary 갱신 실패: %s", rec_id)
        return {}
    if not row:
        logger.warning("backtest_summary 갱신 대상 미존재: rec_id=%s", rec_id)
        return {}
    logger.info("backtest_summary 갱신: rec_id=%s", rec_id)
    return row


async def list_recommendations_pending_backtest(target_date: date) -> list[dict]:
    """Phase 3 폴 루프 진입 가드 — `target_date` 의 `backtest_summary IS NULL` row 만 반환.

    `idx_param_recommendations_backtest_pending` 부분 인덱스(마이그 020) 가
    매칭되어 EXPLAIN 상 인덱스 스캔이 일어난다.
    """
    rows = await pg.fetch(
        f"SELECT * FROM {_TABLE} WHERE target_date = $1 AND backtest_summary IS NULL",
        target_date,
    )
    return rows or []


async def list_pending_by_date(target_date: date) -> list[dict]:
    """사이클 23 P3-1 — target_date 의 status='pending' 자문 전체 조회.

    auto_apply_recommendations() 에서 자동 적용 대상 조회에 사용.
    """
    rows = await pg.fetch(
        f"SELECT * FROM {_TABLE} WHERE target_date = $1 AND status = $2",
        target_date, "pending",
    )
    return rows or []


async def expire_pending_before(target_date: date) -> int:
    """target_date 이전의 pending 레코드를 expired로 일괄 마킹한다.

    Returns:
        만료 처리된 레코드 수.
    """
    result = await pg.execute(
        f"UPDATE {_TABLE} SET status = 'expired' WHERE status = 'pending' AND target_date < $1",
        target_date,
    )
    expired_count = _parse_affected(result)
    if expired_count > 0:
        logger.info("이전 pending 추천 %d건 expired로 마킹", expired_count)
    return expired_count


def _parse_affected(status: str) -> int:
    """asyncpg 상태 문자열('UPDATE N' / 'INSERT 0 N' / 'DELETE N') → 영향 행수 int."""
    try:
        return int(status.strip().split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0
