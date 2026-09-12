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
    # cycle287 (2026-09-12) — KRX 애프터마켓(16:00~20:00, 2026-09-14 신설) 청산 수단.
    # 41~47 전체 표는 place_order docstring 참조. IOC/FOK(42/43/45/46)는 잔량을
    # 자동취소해 손절 잔여를 잃고, 47(최우선지정가)은 자기 방향 최우선호가라
    # 크로스하지 않아 체결 보장이 없다 — 손절 수단으로 41/44 둘만 추가한다.
    KRX_AFTER_LIMIT = "41"   # KRX 애프터마켓 지정가 (폴백)
    KRX_AFTER_BEST = "44"    # KRX 애프터마켓 최유리지정가 (1차)


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
