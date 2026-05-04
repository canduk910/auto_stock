"""daily_performance CRUD."""

import logging
from datetime import date

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def upsert_daily_performance(
    target_date: date,
    total_asset: float,
    daily_profit_rate: float,
    strategy: str = "total",
    *,
    net_external_cashflow: float = 0.0,
    daily_realized_pnl: float = 0.0,
    deposit: float = 0.0,
    cumulative_return_rate: float = 0.0,
) -> None:
    """일일 실적을 저장(upsert)한다.

    daily_profit_rate: 평가손익 기반 일별 수익률 (호환성 유지).
    cumulative_return_rate: TWR 복리 누적 수익률 (실현손익 기반).
    """
    data = {
        "date": target_date.isoformat(),
        "total_asset": total_asset,
        "daily_profit_rate": daily_profit_rate,
        "strategy": strategy,
        "net_external_cashflow": net_external_cashflow,
        "daily_realized_pnl": daily_realized_pnl,
        "deposit": deposit,
        "cumulative_return_rate": cumulative_return_rate,
    }
    supabase.table("daily_performance").upsert(data).execute()
    logger.info(
        "일일 실적 저장: %s 전략=%s (실현 %.2f%%, 누적 %.2f%%, 외부입출금 %.0f)",
        target_date, strategy, daily_profit_rate, cumulative_return_rate, net_external_cashflow,
    )


async def get_performance(days: int = 30, strategy: str = "total") -> list[dict]:
    """최근 N일 실적을 조회한다."""
    result = (
        supabase.table("daily_performance")
        .select("*")
        .eq("strategy", strategy)
        .order("date", desc=True)
        .limit(days)
        .execute()
    )
    return sorted(result.data, key=lambda r: r["date"])


async def get_latest_performance(strategy: str = "total") -> dict | None:
    """가장 최근 영업일의 실적 1행을 반환한다.

    TWR 누적 baseline + Δ예수금 계산용.
    """
    result = (
        supabase.table("daily_performance")
        .select("*")
        .eq("strategy", strategy)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
