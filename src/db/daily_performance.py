"""daily_performance CRUD."""

import logging
from datetime import date

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def upsert_daily_performance(
    target_date: date,
    total_asset: float,
    daily_profit_rate: float,
) -> None:
    """일일 실적을 저장(upsert)한다."""
    data = {
        "date": target_date.isoformat(),
        "total_asset": total_asset,
        "daily_profit_rate": daily_profit_rate,
    }
    supabase.table("daily_performance").upsert(data).execute()
    logger.info("일일 실적 저장: %s (수익률: %.2f%%)", target_date, daily_profit_rate)


async def get_performance(days: int = 30) -> list[dict]:
    """최근 N일 실적을 조회한다."""
    result = (
        supabase.table("daily_performance")
        .select("*")
        .order("date", desc=True)
        .limit(days)
        .execute()
    )
    return result.data
