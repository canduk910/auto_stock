"""positions CRUD — 보유 포지션 영속화.

체결통보 수신 시 INSERT/DELETE, 재기동 시 SELECT로 정확한 포지션 복구.
KIS 잔고 API가 아닌 DB가 포지션의 진실의 원천.

supabase 동기 호출은 모두 asyncio.to_thread()로 위임 — 이벤트 루프 블로킹 차단.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def save_position(
    ticker: str,
    ticker_name: str,
    buy_price: int,
    quantity: int,
    order_no: str,
    strategy_id: str,
    buy_date: date,
    high_since_buy: int = 0,
) -> None:
    """포지션을 저장(upsert)한다."""
    data = {
        "ticker": ticker,
        "ticker_name": ticker_name,
        "buy_price": buy_price,
        "quantity": quantity,
        "order_no": order_no,
        "strategy_id": strategy_id,
        "buy_date": buy_date.isoformat(),
        "high_since_buy": high_since_buy or buy_price,
    }
    await asyncio.to_thread(
        lambda: supabase.table("positions").upsert(data, on_conflict="ticker").execute()
    )
    logger.debug("포지션 저장: %s %d주 @ %d (전략: %s)", ticker, quantity, buy_price, strategy_id)


async def delete_position(ticker: str) -> None:
    """포지션을 삭제한다 (매도 체결 시)."""
    await asyncio.to_thread(
        lambda: supabase.table("positions").delete().eq("ticker", ticker).execute()
    )
    logger.debug("포지션 삭제: %s", ticker)


async def load_all() -> list[dict]:
    """모든 포지션을 로드한다."""
    result = await asyncio.to_thread(
        lambda: supabase.table("positions").select("*").execute()
    )
    return result.data


async def update_high(ticker: str, high: int) -> None:
    """고점을 갱신한다."""
    await asyncio.to_thread(
        lambda: supabase.table("positions").update(
            {"high_since_buy": high}
        ).eq("ticker", ticker).execute()
    )


async def clear_all() -> None:
    """모든 포지션을 삭제한다 (정산 시)."""
    await asyncio.to_thread(
        lambda: supabase.table("positions").delete().neq("ticker", "").execute()
    )
    logger.info("DB 포지션 전체 삭제")
