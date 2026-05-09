"""daily_performance CRUD."""

from __future__ import annotations

import asyncio
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
    await asyncio.to_thread(
        lambda: supabase.table("daily_performance").upsert(data).execute()
    )
    logger.info(
        "일일 실적 저장: %s 전략=%s (실현 %.2f%%, 누적 %.2f%%, 외부입출금 %.0f)",
        target_date, strategy, daily_profit_rate, cumulative_return_rate, net_external_cashflow,
    )


async def get_performance(days: int = 30, strategy: str = "total") -> list[dict]:
    """최근 N일 실적을 조회한다."""
    result = await asyncio.to_thread(
        lambda: supabase.table("daily_performance")
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
    result = await asyncio.to_thread(
        lambda: supabase.table("daily_performance")
        .select("*")
        .eq("strategy", strategy)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def recompute_from_trades() -> bool:
    """trade_history 기반 daily_performance 일괄 재계산 (소급 정산).

    Supabase에 등록된 PostgreSQL 함수 `recompute_daily_performance()`를 RPC 호출.
    멱등이므로 매일 정산 후 호출해도 안전.

    수행 단계 (DB 함수 내부):
    1) SELL profit_loss 합 → daily_realized_pnl (전략별 + total)
    2) daily_profit_rate = daily_realized_pnl / 전일 total_asset * 100
    3) cumulative_return_rate = TWR 복리 누적
    """
    try:
        await asyncio.to_thread(
            lambda: supabase.rpc("recompute_daily_performance", {}).execute()
        )
        logger.info("daily_performance 일괄 재계산 완료 (recompute_daily_performance)")
        return True
    except Exception:
        logger.exception("daily_performance 재계산 실패")
        return False
