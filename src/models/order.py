"""주문 데이터 모델."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderDivision(str, Enum):
    LIMIT = "00"       # 지정가
    MARKET = "01"      # 시장가


class CancelType(str, Enum):
    REVISE = "01"      # 정정
    CANCEL = "02"      # 취소


class OrderRequest(BaseModel):
    ticker: str
    side: OrderSide
    quantity: int
    price: int = 0
    order_division: OrderDivision = OrderDivision.MARKET


class OrderResult(BaseModel):
    order_no: str          # ODNO
    order_time: str        # ORD_TMD
    krx_org_no: str = ""   # KRX_FWDG_ORD_ORGNO
