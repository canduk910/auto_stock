"""trade_history 데이터 모델."""

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
    trade_type: TradeType
    price: float
    quantity: int
    profit_loss: float = 0
    status: TradeStatus = TradeStatus.PENDING
