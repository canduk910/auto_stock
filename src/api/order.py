"""국내주식 주문 API 모듈.

- 현금 매수/매도 (TTTC0012U / TTTC0011U)
- 정정/취소 (TTTC0013U)
"""

import logging

from src.api.base import kis_post
from src.auth.hashkey import generate_hashkey
from src.config import settings
from src.models.order import (
    CancelType,
    OrderDivision,
    OrderResult,
    OrderSide,
)

logger = logging.getLogger(__name__)

ORDER_CASH_URL = "/uapi/domestic-stock/v1/trading/order-cash"
ORDER_RVSECNCL_URL = "/uapi/domestic-stock/v1/trading/order-rvsecncl"


async def place_order(
    ticker: str,
    side: OrderSide,
    quantity: int,
    price: int = 0,
    order_division: OrderDivision = OrderDivision.MARKET,
) -> OrderResult:
    """현금 매수 또는 매도 주문을 실행한다."""
    base_tr_id = "TTTC0012U" if side == OrderSide.BUY else "TTTC0011U"
    tr_id = settings.get_tr_id(base_tr_id)

    body = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "PDNO": ticker,
        "ORD_DVSN": order_division.value,
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price),
    }

    hashkey = await generate_hashkey(body)
    data = await kis_post(ORDER_CASH_URL, tr_id, body, hashkey=hashkey)
    output = data["output"]

    result = OrderResult(
        order_no=output["ODNO"],
        order_time=output["ORD_TMD"],
        krx_org_no=output.get("KRX_FWDG_ORD_ORGNO", ""),
    )
    logger.info(
        "%s 주문 완료: %s %s주 @ %s (주문번호: %s)",
        side.value,
        ticker,
        quantity,
        price,
        result.order_no,
    )
    return result


async def cancel_order(
    original_order_no: str,
    quantity: int,
    cancel_type: CancelType = CancelType.CANCEL,
    price: int = 0,
    *,
    cancel_all: bool = True,
) -> OrderResult:
    """주문 정정 또는 취소를 실행한다."""
    tr_id = settings.get_tr_id("TTTC0013U")

    body = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "KRX_FWDG_ORD_ORGNO": "",
        "ORGN_ODNO": original_order_no,
        "ORD_DVSN": "00",
        "RVSE_CNCL_DVSN_CD": cancel_type.value,
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price),
        "QTY_ALL_ORD_YN": "Y" if cancel_all else "N",
    }

    hashkey = await generate_hashkey(body)
    data = await kis_post(ORDER_RVSECNCL_URL, tr_id, body, hashkey=hashkey)
    output = data["output"]

    result = OrderResult(
        order_no=output["ODNO"],
        order_time=output["ORD_TMD"],
        krx_org_no=output.get("KRX_FWDG_ORD_ORGNO", ""),
    )
    logger.info(
        "%s 완료: 원주문 %s → 신주문 %s",
        cancel_type.value,
        original_order_no,
        result.order_no,
    )
    return result
