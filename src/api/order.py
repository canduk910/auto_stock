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

    ORD_DVSN (주문 구분) — cycle287(2026-09-12) 부터 시각이 거래소·호가유형을
    함께 정한다(`order_engine._route_exchange_by_clock` + `_apply_clock`).
    이 함수 자체는 값을 검증 없이 그대로 흘려보낸다(화이트리스트 금지 —
    `44` 를 조용히 지우는 함정을 만들지 않는다):

      | 구간 | 값 | 의미 | 비고 |
      |---|---|---|---|
      | 정규장·프리장 | "01" | 시장가(MARKET, 기본) | |
      | 정규장·프리장 폴백 | "00" | 지정가(LIMIT) | 매수 `step_up(5)` / 매도 `step_down(5)` |
      | NXT 프리마켓(08:00~08:50) 매수 승격(cycle291) | "27" | GTP지정가 | `ORD_UNPR=step_up(현재가,5)` — `00` 폴백과 **같은 값**(가격 행위 변경 0). 미체결잔량은 거래소가 08:50 에 일괄취소한다(GTP 의 정체성). 게이트 4중(실전·NXT·그 시각 유효·프리장) 중 하나라도 실패하면 `00` 이 그대로 나간다 — **매도는 여전히 `00`**(자문 §2, GTP 매도는 08:50 자동취소가 `_selling` 을 잠가 손절 재평가를 억제한다) |
      | KRX 애프터(16:00~20:00, 2026-09-14 신설) 1차 | "44" | 최유리지정가 | `ORD_UNPR="0"` — **정본 명시 없음**(현금주문 문서는 "시장가 등" 만 언급하는 비열거형 문구이고, 신용주문 문서는 "장전/장후 시간외·시장가" 를 열거하며 최유리(03)·최우선(04)는 **그 열거에서 빠져 있다** — 두 문서가 갈린다). `0` 을 고른 것은 비대칭 판단(§4-A: 0이 틀리면 즉시 거부돼 41 폴백이 받고, 가격을 실었는데 0이 맞았다면 무해 — 반대로 가격을 실었는데 0이 필요했다면 상한가 기준 주문금액 산정 위험이 있다). **시장가(01) 없음**. **ETP(ETF/ETN) 거래 불가**(공지 verbatim) |
      | KRX 애프터 폴백 | "41" | 지정가 | 우리가 가격을 통제(`step_down(5)`) |

      41~47 전체(41 지정가/42 IOC/43 FOK/44 최유리/45 IOC최유리/46 FOK최유리/
      47 최우선)가 애프터 전용이나, 이 시스템은 41·44 둘만 보낸다(`OrderDivision`
      멤버가 그 둘뿐 — IOC/FOK 는 잔량 자동취소로 손절 잔여를 잃고, 47 은 자기
      방향 최우선호가라 크로스하지 않아 체결 보장이 없다). 27~29(NXT GTP) 전체도
      같은 규율로 `27`(GTP지정가) 하나만 보낸다 — `28`(GTP최유리)은 `ORD_UNPR`
      규약이 현금·신용 문서 사이에서 갈리고 얇은 프리마켓 호가에서 1레벨에
      멈추며, `29`(GTP최우선)는 자기 방향 최우선호가라 크로스하지 않는다.

    EXCG_ID_DVSN_CD (거래소):
      - "KRX" = 한국거래소 메인 (기본). 09:00~15:30·16:00~20:00 은 시각이 강제한다
      - "NXT" = 넥스트 매매 (프리/애프터)
      - "SOR" = 스마트오더 라우팅 — cycle287 부터 우리 시스템은 새로 보내지 않는다
        (프리장·15:40~16:00 등 시각이 base 를 유지하는 창에서는 DB 값이 여전히
        나갈 수 있다)
      - 모의(VTS)는 KRX 만 허용 — NXT/SOR 실전 한정. 애프터 41~47 의 모의 지원
        여부도 정본에 없다(자문 §4-F) — 애프터 호가 변환은 `settings.is_production`
        일 때만 적용된다.

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
    order_division: str | None = None,
) -> OrderResult:
    """주문 정정 또는 취소를 실행한다.

    TR_ID: TTTC0013U (정정/취소 공용, 실전. 모의 VTTC0013U).
    `RVSE_CNCL_DVSN_CD`: "01" 정정 / "02" 취소.
    `exchange`: 원주문이 접수된 거래소. `KRX`(기본) / `NXT` / `SOR`.

    `order_division` — cycle291(2026-09-13) Stage A. **opt-in, 미전달 시
    `"00"` 하드코딩과 body byte 동일**(자문 §4). KIS 정본에 "취소 시 원주문
    호가유형을 실어라" 는 규약이 **없다**(국내주식 정정취소 필드표엔 그
    문장이 없고, 선물옵션 API 만 `[취소] 01 로 입력` = 고정값을 명시하며,
    KIS 공식 취소 샘플도 `ord_dvsn="00"` 을 쓴다). 그래서 이 인자는 **아직
    호출자 3곳(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)
    이 전달하지 않는 배관·매핑만이다** — Stage B(실제 전송) 전환은 D+1 이후
    `[after_cancel_result]` 의 `orig_dvsn` 층화 실측 + **매매 행위 변경 =
    별도 승인**이 필요하다. 값 화이트리스트는 두지 않는다(`44` 를 조용히
    지우는 함정을 재현하지 않는다) — falsy(`None`/`""`) 만 `"00"` 으로
    폴백한다. ⚠️ **KRX 애프터마켓(16:00~20:00, `ORD_DVSN` 41/44)·NXT 프리마켓
    GTP(27)에서 접수한 원주문의 취소가 `"00"` 으로 정상 처리되는지는
    미검증·미실측·미확인이다** — 그 창의 취소·부분체결 실적이 all-time
    0건이라 추측으로 바꾸면 작동 중인 정규장 취소를 위험에 넣는다. 관측
    자체는 구현돼 있다 — 호출부가 매 취소 시도마다 `[after_cancel_result]
    ticker= order_no= ord_dvsn= orig_dvsn= dvsn_src= exchange= result=ok|error
    err=` 1행을 남긴다. 첫 실측에서 `result=error` 가 비-`{00,01}` `orig_dvsn`
    에만 몰리면 그때 Stage B 를 검토한다 — 지금은 배관 + 관측만이다.
    """
    tr_id = settings.get_tr_id("TTTC0013U")

    body = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "KRX_FWDG_ORD_ORGNO": "",
        "ORGN_ODNO": original_order_no,
        "ORD_DVSN": order_division if order_division else "00",
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
