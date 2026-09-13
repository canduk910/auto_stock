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
    # cycle291 (2026-09-13) — NXT 프리마켓 전용호가 GTP(Good Till Pre-Market),
    # 2026-09-14 신설. 미체결잔량을 거래소가 프리마켓 종료(08:50)에 일괄취소한다 —
    # 그 취소 규약이 GTP 의 정체성이고, 우리가 이 코드를 쓰는 유일한 이유다
    # (지정가 `00` 은 09-14 이후에도 프리마켓에서 유효하다 — GTP 는 "필수" 가
    #  아니라 "추가" 다. 공지 2026-09-09 verbatim: 애프터마켓만 "호가 유형선택 필수").
    # 28(GTP최유리)·29(GTP최우선)는 넣지 않는다 — 28 은 `ORD_UNPR` 규약이 현금·신용
    # 문서 사이에서 갈리고 얇은 프리마켓 호가에서 1레벨에 멈추며, 29 는 자기 방향
    # 최우선호가라 크로스하지 않아 체결 보장이 없다(cycle287 `47` 배제와 동일 논거).
    NXT_GTP_LIMIT = "27"     # NXT GTP 지정가 (프리마켓 매수 전용)


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
