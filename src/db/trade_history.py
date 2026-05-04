"""trade_history CRUD."""

import logging
from datetime import datetime, timezone, timedelta

from src.db.supabase import supabase
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def insert_trade(record: TradeRecord) -> None:
    """거래 기록을 삽입한다."""
    data = {
        "ticker": record.ticker,
        "ticker_name": record.ticker_name,
        "trade_type": record.trade_type.value,
        "price": float(record.price),
        "quantity": record.quantity,
        "profit_loss": float(record.profit_loss),
        "status": record.status.value,
        "strategy": record.strategy,
        "order_no": record.order_no,
        "timestamp": datetime.now(KST).isoformat(),
    }
    supabase.table("trade_history").insert(data).execute()
    logger.debug("거래 기록 삽입: %s %s (전략: %s)", record.trade_type.value, record.ticker, record.strategy)


async def update_trade_status(
    ticker: str,
    trade_type: TradeType,
    status: TradeStatus,
    strategy: str = "momentum",
    price: int | None = None,
    profit_loss: float | None = None,
) -> None:
    """최신 거래 기록의 상태를 업데이트한다."""
    update_data: dict = {"status": status.value}
    if price is not None:
        update_data["price"] = float(price)
    if profit_loss is not None:
        update_data["profit_loss"] = float(profit_loss)
    supabase.table("trade_history").update(
        update_data
    ).eq(
        "ticker", ticker
    ).eq(
        "trade_type", trade_type.value
    ).eq(
        "status", TradeStatus.PENDING.value
    ).eq(
        "strategy", strategy
    ).execute()
    logger.debug("거래 상태 변경: %s %s -> %s (전략: %s)", ticker, trade_type.value, status.value, strategy)


async def get_today_trades_for_settlement(strategy: str | None = None) -> list[dict]:
    """정산용 — 당일 체결 거래 전체(중복 dedup 없음, 매수+매도 합산용).

    COMPLETED + PARTIAL 상태만 포함. 매매 cashflow / 실현손익 합 계산에 사용.
    """
    from datetime import date
    today = date.today().isoformat()
    query = (
        supabase.table("trade_history")
        .select("*")
        .gte("timestamp", f"{today}T00:00:00")
        .in_("status", ["COMPLETED", "PARTIAL"])
        .order("timestamp", desc=False)
    )
    if strategy:
        query = query.eq("strategy", strategy)
    result = query.execute()
    return result.data or []


async def get_today_buy_trades(strategy: str | None = None) -> list[dict]:
    """당일 매수 기록을 조회한다 (포지션 복구용)."""
    from datetime import date
    today = date.today().isoformat()
    query = (
        supabase.table("trade_history")
        .select("*")
        .eq("trade_type", "BUY")
        .gte("timestamp", f"{today}T00:00:00")
        .in_("status", ["PENDING", "COMPLETED", "PARTIAL"])
        .order("timestamp", desc=True)
    )
    if strategy:
        query = query.eq("strategy", strategy)
    result = query.execute()
    # 같은 종목이 여러 번 매수된 경우 최신 기록만 사용
    seen: dict[str, dict] = {}
    for row in result.data:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


async def get_today_sell_trades(strategy: str | None = None) -> list[dict]:
    """당일 매도 기록을 조회한다 (동기화용)."""
    from datetime import date
    today = date.today().isoformat()
    query = (
        supabase.table("trade_history")
        .select("*")
        .eq("trade_type", "SELL")
        .gte("timestamp", f"{today}T00:00:00")
        .in_("status", ["COMPLETED", "PARTIAL"])
        .order("timestamp", desc=True)
    )
    if strategy:
        query = query.eq("strategy", strategy)
    result = query.execute()
    seen: dict[str, dict] = {}
    for row in result.data:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


async def get_trades(
    limit: int = 50,
    offset: int = 0,
    ticker: str | None = None,
    strategy: str | None = None,
) -> tuple[list[dict], int]:
    """거래 내역을 조회한다. (데이터, 전체 건수) 반환."""
    # 전체 건수 조회
    count_query = supabase.table("trade_history").select("*", count="exact")
    if ticker:
        count_query = count_query.eq("ticker", ticker)
    if strategy:
        count_query = count_query.eq("strategy", strategy)
    count_result = count_query.execute()
    total = count_result.count or 0

    # 데이터 조회
    query = supabase.table("trade_history").select("*").order(
        "timestamp", desc=True
    ).range(offset, offset + limit - 1)
    if ticker:
        query = query.eq("ticker", ticker)
    if strategy:
        query = query.eq("strategy", strategy)
    result = query.execute()

    return result.data, total


async def get_trades_in_range(
    start_date,
    end_date,
    strategy: str | None = None,
) -> list[dict]:
    """[start_date, end_date] 범위의 거래 기록을 timestamp 기준 inclusive하게 조회한다.

    파라미터 추천 모듈 등에서 N영업일치 통계 산출에 사용한다.
    """
    start_iso = f"{start_date.isoformat()}T00:00:00"
    end_iso = f"{end_date.isoformat()}T23:59:59.999999"
    query = (
        supabase.table("trade_history")
        .select("*")
        .gte("timestamp", start_iso)
        .lte("timestamp", end_iso)
        .order("timestamp", desc=False)
    )
    if strategy:
        query = query.eq("strategy", strategy)
    result = query.execute()
    return result.data or []
