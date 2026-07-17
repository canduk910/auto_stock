"""positions CRUD — 보유 포지션 영속화.

체결통보 수신 시 INSERT/DELETE, 재기동 시 SELECT로 정확한 포지션 복구.
KIS 잔고 API가 아닌 DB가 포지션의 진실의 원천.

사이클 M1-1 (Supabase→RDS 이전 단계1): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존 — 호출부(order_engine 등) diff 0.
"""

from __future__ import annotations

import logging
from datetime import date

import src.db.pg as pg
from src.db._kst import to_date

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
    resolved_high = high_since_buy or buy_price
    sql = """
        INSERT INTO positions (
            ticker, ticker_name, buy_price, quantity, order_no,
            strategy_id, buy_date, high_since_buy
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (ticker) DO UPDATE SET
            ticker_name = EXCLUDED.ticker_name,
            buy_price = EXCLUDED.buy_price,
            quantity = EXCLUDED.quantity,
            order_no = EXCLUDED.order_no,
            strategy_id = EXCLUDED.strategy_id,
            buy_date = EXCLUDED.buy_date,
            high_since_buy = EXCLUDED.high_since_buy
    """
    # M6 — buy_date DATE 컬럼 바인딩. str 입력도 date 로 강제 변환.
    await pg.execute(
        sql,
        ticker,
        ticker_name,
        buy_price,
        quantity,
        order_no,
        strategy_id,
        to_date(buy_date),
        resolved_high,
    )
    logger.debug("포지션 저장: %s %d주 @ %d (전략: %s)", ticker, quantity, buy_price, strategy_id)


async def delete_position(ticker: str) -> None:
    """포지션을 삭제한다 (매도 체결 시)."""
    await pg.execute("DELETE FROM positions WHERE ticker = $1", ticker)
    logger.debug("포지션 삭제: %s", ticker)


async def load_all() -> list[dict]:
    """모든 포지션을 로드한다."""
    return await pg.fetch("SELECT * FROM positions")


async def update_high(ticker: str, high: int) -> None:
    """고점을 갱신한다."""
    await pg.execute(
        "UPDATE positions SET high_since_buy = $1 WHERE ticker = $2", high, ticker
    )


async def clear_all() -> None:
    """모든 포지션을 삭제한다 (정산 시)."""
    await pg.execute("DELETE FROM positions")
    logger.info("DB 포지션 전체 삭제")
