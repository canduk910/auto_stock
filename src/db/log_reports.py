"""daily_log_reports CRUD.

사이클 M1-2 (Supabase→RDS 이전 단계1 증분2): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존 — 호출부(log_analysis_engine 등) diff 0.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

import src.db.pg as pg
from src.db._kst import now_kst_iso

logger = logging.getLogger(__name__)


async def insert_log_report(
    *,
    target_date: date,
    summary: str,
    findings: list[dict],
    metrics: dict,
    model: str | None,
    # 사이클 58 V-2 (2026-06-04) — OpenAI 메타 컬럼
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: int | None = None,
    cost_estimate_usd: Decimal | None = None,
) -> dict | None:
    """일일 로그 분석 리포트를 INSERT한다.

    (target_date) UNIQUE — 동일 영업일 재실행 시 None 반환.

    사이클 58 V-2: OpenAI 호출 메타(tokens/latency/cost)를 함께 기록한다.
    모두 NULL 허용 — 기존 row 자연 보존.
    """
    sql = """
        INSERT INTO daily_log_reports (
            target_date, summary, findings, metrics, model,
            input_tokens, output_tokens, total_tokens, latency_ms,
            cost_estimate_usd, created_at
        ) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, $8, $9, $10, $11)
        RETURNING *
    """
    try:
        row = await pg.fetchrow(
            sql,
            target_date,
            summary,
            findings,
            metrics,
            model,
            input_tokens,
            output_tokens,
            total_tokens,
            latency_ms,
            float(cost_estimate_usd) if cost_estimate_usd is not None else None,
            datetime.fromisoformat(now_kst_iso()),
        )
        return row
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "23505" in msg:
            logger.info("daily_log_reports 중복 (이미 존재): %s", target_date)
            return None
        logger.exception("daily_log_reports INSERT 실패")
        raise


async def list_log_reports(days: int = 30) -> list[dict]:
    """최근 N일치 리포트를 신규순으로 조회한다."""
    rows = await pg.fetch(
        "SELECT * FROM daily_log_reports ORDER BY target_date DESC LIMIT $1",
        days,
    )
    return rows or []


async def get_log_report(target_date: date) -> dict | None:
    """단일 영업일 리포트를 조회한다."""
    return await pg.fetchrow(
        "SELECT * FROM daily_log_reports WHERE target_date = $1 LIMIT 1",
        target_date,
    )
