"""trade_history 데이터 모델."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


class TradeRecord(BaseModel):
    id: str | None = None
    timestamp: datetime | None = None
    ticker: str
    ticker_name: str = ""
    trade_type: TradeType
    price: float
    quantity: int
    profit_loss: float = 0
    status: TradeStatus = TradeStatus.PENDING
    strategy: str = "momentum"
    order_no: str = ""
    # cycle409 — 사용자 결정 10-04 Q4: 주문가. 명시하면 `insert_trade` 가 그대로 쓰고, 비우면
    # PENDING ∧ BUY 의 `price` 를 쓴다(매도 PENDING 의 `price` 는 매수가라 호출부가 따로 넘긴다).
    order_price: float | None = None
