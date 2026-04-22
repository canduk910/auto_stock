"""trade_history CRUD."""

import logging

from src.db.supabase import supabase
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)


async def insert_trade(record: TradeRecord) -> None:
    """거래 기록을 삽입한다."""
    data = {
        "ticker": record.ticker,
        "trade_type": record.trade_type.value,
        "price": float(record.price),
        "quantity": record.quantity,
        "profit_loss": float(record.profit_loss),
        "status": record.status.value,
    }
    supabase.table("trade_history").insert(data).execute()
    logger.debug("거래 기록 삽입: %s %s", record.trade_type.value, record.ticker)


async def update_trade_status(
    ticker: str,
    trade_type: TradeType,
    status: TradeStatus,
) -> None:
    """최신 거래 기록의 상태를 업데이트한다."""
    supabase.table("trade_history").update(
        {"status": status.value}
    ).eq(
        "ticker", ticker
    ).eq(
        "trade_type", trade_type.value
    ).eq(
        "status", TradeStatus.PENDING.value
    ).execute()
    logger.debug("거래 상태 변경: %s %s -> %s", ticker, trade_type.value, status.value)


async def get_trades(
    limit: int = 50,
    offset: int = 0,
    ticker: str | None = None,
) -> tuple[list[dict], int]:
    """거래 내역을 조회한다. (데이터, 전체 건수) 반환."""
    # 전체 건수 조회
    count_query = supabase.table("trade_history").select("*", count="exact")
    if ticker:
        count_query = count_query.eq("ticker", ticker)
    count_result = count_query.execute()
    total = count_result.count or 0

    # 데이터 조회
    query = supabase.table("trade_history").select("*").order(
        "timestamp", desc=True
    ).range(offset, offset + limit - 1)
    if ticker:
        query = query.eq("ticker", ticker)
    result = query.execute()

    return result.data, total
