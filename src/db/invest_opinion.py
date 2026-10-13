"""invest_opinion_history · estimate_perform_snapshot CRUD (supabase/migrations/051).

모든 함수는 graceful — DB 예외는 로깅 후 0/False/[] (매매 경로 무관 관찰 데이터).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)


async def upsert_opinions(ticker: str, rows: list[dict[str, Any]]) -> int:
    """투자의견 행 upsert(멱등). 성공 시 보낸 행 수, 실패 0."""
    if not rows:
        return 0
    now = datetime.fromisoformat(now_kst_iso())
    args_list = [
        (
            ticker, to_date(r["bsop_date"]), r["mbcr_name"],
            r.get("invt_opnn"), r.get("rgbf_invt_opnn"), r.get("hts_goal_prc"),
            r.get("stck_prdy_clpr"), r.get("dprt"), dict(r.get("raw") or {}), now,
        )
        for r in rows
    ]
    sql = """
        INSERT INTO invest_opinion_history
            (ticker, bsop_date, mbcr_name, invt_opnn, rgbf_invt_opnn, hts_goal_prc,
             stck_prdy_clpr, dprt, raw, fetched_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
        ON CONFLICT (ticker, bsop_date, mbcr_name) DO UPDATE SET
            invt_opnn = EXCLUDED.invt_opnn,
            rgbf_invt_opnn = EXCLUDED.rgbf_invt_opnn,
            hts_goal_prc = EXCLUDED.hts_goal_prc,
            stck_prdy_clpr = EXCLUDED.stck_prdy_clpr,
            dprt = EXCLUDED.dprt,
            raw = EXCLUDED.raw,
            fetched_at = EXCLUDED.fetched_at
    """
    try:
        await pg.executemany(sql, args_list)
    except Exception:
        logger.exception("invest_opinion_history upsert 실패: %s rows=%d", ticker, len(rows))
        return 0
    return len(args_list)


async def upsert_estimate_snapshot(ticker: str, snapshot_month: date, data: dict[str, Any]) -> bool:
    """추정실적 월 스냅샷 upsert. 성공 True."""
    sql = """
        INSERT INTO estimate_perform_snapshot (ticker, snapshot_month, settle_months, raw, fetched_at)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (ticker, snapshot_month) DO UPDATE SET
            settle_months = EXCLUDED.settle_months,
            raw = EXCLUDED.raw,
            fetched_at = EXCLUDED.fetched_at
    """
    try:
        await pg.execute(
            sql, ticker, to_date(snapshot_month),
            list(data.get("settle_months") or []), data.get("raw") or {},
            datetime.fromisoformat(now_kst_iso()),
        )
    except Exception:
        logger.exception("estimate_perform_snapshot upsert 실패: %s %s", ticker, snapshot_month)
        return False
    return True


async def get_opinions(ticker: str, date_from: date, date_to: date) -> list[dict]:
    """기간 내 투자의견(최신순)."""
    try:
        rows = await pg.fetch(
            """
            SELECT ticker, bsop_date, mbcr_name, invt_opnn, rgbf_invt_opnn, hts_goal_prc,
                   stck_prdy_clpr, dprt
            FROM invest_opinion_history
            WHERE ticker = $1 AND bsop_date BETWEEN $2 AND $3
            ORDER BY bsop_date DESC
            """,
            ticker, date_from, date_to,
        )
    except Exception:
        logger.exception("invest_opinion_history 조회 실패: %s", ticker)
        return []
    return [dict(r) for r in rows or []]
