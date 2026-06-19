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
    exchange: str = "KRX",
) -> OrderResult:
    """현금 매수 또는 매도 주문을 실행한다.

    TR_ID 분기:
      - 실전 매수: TTTC0012U / 실전 매도: TTTC0011U
      - 모의 자동 변환: `settings.get_tr_id()` 가 T → V 치환
        (실전 TTTC0012U → 모의 VTTC0012U)

    ORD_DVSN (주문 구분):
      - "01" = 시장가 (MARKET, 기본)
      - "00" = 지정가 (LIMIT). 시장가 거부 폴백 시 사용 — 매수는 `step_up(5)`,
        매도는 `step_down(5)` 호가 단위 정렬.

    EXCG_ID_DVSN_CD (거래소):
      - "KRX" = 한국거래소 메인 (기본)
      - "NXT" = 넥스트 매매 (프리/애프터)
      - "SOR" = 스마트오더 라우팅
      - 모의(VTS)는 KRX 만 허용 — NXT/SOR 실전 한정.

    호출자 의무 (사이클 165 명문화):
      `execute_buy/execute_sell` 가 응답 직후 동기 영역에서 주문번호 매핑
      (`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록 후
      `await insert_trade(PENDING)` 호출. 매핑은 `await` 진입 *전* 완료 필수
      (체결통보 race 차단, CLAUDE.md "절대 깨지 말 것" 영속).
    """
    base_tr_id = "TTTC0012U" if side == OrderSide.BUY else "TTTC0011U"
    tr_id = settings.get_tr_id(base_tr_id)

    body = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "PDNO": ticker,
        "ORD_DVSN": order_division.value,
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price),
        "EXCG_ID_DVSN_CD": exchange,
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
    exchange: str = "KRX",
) -> OrderResult:
    """주문 정정 또는 취소를 실행한다.

    TR_ID: TTTC0013U (정정/취소 공용, 실전. 모의 VTTC0013U).
    `RVSE_CNCL_DVSN_CD`: "01" 정정 / "02" 취소.
    `exchange`: 원주문이 접수된 거래소. `KRX`(기본) / `NXT` / `SOR`.
    """
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
        "EXCG_ID_DVSN_CD": exchange,
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
