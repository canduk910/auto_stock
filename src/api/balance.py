"""잔고조회, 매수가능조회 API 모듈.

- 잔고조회 (TTTC8434R)
- 매수가능조회 (TTTC8908R)
"""

import logging

from src.api.base import KisApiError, kis_get
from src.config import settings
from src.models.balance import AccountSummary, BuyableInfo, StockHolding

logger = logging.getLogger(__name__)

BALANCE_URL = "/uapi/domestic-stock/v1/trading/inquire-balance"
PSBL_ORDER_URL = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"


# 장운영시간 외 / 매매 불가 시간 거부 키워드.
# KIS 가 같은 msg_cd(APBK0918)로 보유부족·자금부족·시간외 거부를 모두 내보내기 때문에
# msg1 키워드로 가드한다. 매칭되면 위 두 분류 모두 False — 매도/매수 모두 락 걸지 않는다.
_MARKET_CLOSED_KEYWORDS = (
    "장운영시간",
    "매매 불가 시간",
    "매매불가시간",
    "운영시간이 아",   # "운영시간이 아닙니다" 변형 보존 가드
    "거래시간 외",
    "거래시간외",
    "장시간 외",
    "장시간외",
)


# 시장가 주문 거부 키워드.
# msg_cd 는 운영 trace 누적 후 화이트리스트화 예정 — 현재는 msg1 키워드 기반.
# 이 키워드에 해당하면 is_insufficient_cash / is_insufficient_quantity 는 False 를 반환해야
# 하며(상호 배타), 매수 지정가 폴백 분기를 타게 된다.
_MARKET_ORDER_DISALLOWED_KEYWORDS = (
    "시장가매매불가",
    "시장가 매매 불가",
    "시장가 주문 불가",
    "시장가 호가 불가",
    # 2026-05-11 계양전기(012200) 09:00:21 매도 거부 (APBK1943) — 띄어쓰기 없는 변형.
    # 매수/매도 양쪽 폴백 분기에서 인식되도록 추가.
    "시장가호가불가",
    # Phase H1 — 2026-05-11 NXT 애프터(16:05~16:28) 매도 거부 ×3 (APBK3013).
    # msg1: "[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다."
    # 특이성 높은 키워드만 추가 — "지정가" 단독은 정상 안내와 충돌하므로 금지.
    "최유리/최우선지정가 주문만",
    "지정가 및 최유리",
    # cycle229 (P1-5, 2026-08-28) — APBK3013 단일가 세션 변형:
    # "[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다"
    # 기존 "지정가 및 최유리" 는 중간 "주문(신규/정정/취소)" 삽입으로 substring 불성립
    # → 8/20~8/27 매수 9건이 미분류 raise 로 on_tick 을 죽여 매일 15:30 WS 재연결.
    # 주 실익은 **매도** — 미분류 매도 거부는 3회 재시도 후 무기록 포기(TTL 미등록)라
    # 랜덤엔드 창 청산 실패가 기록조차 안 됐다. 낮은 매도 지정가는 단일가 세션 유효
    # 주문 = step_down 폴백이 정확한 처방. 장운영 키워드 부재라 closed 와 무교차.
    "단일가매매",
)


def is_market_order_disallowed(err: KisApiError) -> bool:
    """KIS 응답이 '시장가 주문 불가' 류의 거부인지 판단.

    계양전기(012200) "시장가매매불가" 거부 대응 (2026-05-11).
    msg_cd 누적: APBK1943 (계양전기 매도) + APBK3013 (NXT 애프터 매도).
    현재는 msg1 키워드 (`_MARKET_ORDER_DISALLOWED_KEYWORDS`) 기반 — 운영 로그 누적 후 화이트리스트화 예정.

    ⚠️ **`is_market_closed_rejection` 과 이중 매칭이 실재한다** (2026-08-06 정정 —
    종전 "상호 배타" 서술은 프리마켓 msg1 에서 거짓): APBK0918
    "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)" 은 양쪽 키워드에
    동시 매칭된다. `execute_sell` 은 market_closed 를 **먼저** 검사하므로 이중
    매칭은 "보류(포지션 보존 + 다음 09:00 TTL)" 로 떨어진다 — **이 우선순위가
    의도된 계약**이다: 프리장은 왜곡 시세라 지정가 폴백으로 즉시 파는 것보다
    09:00 KRX 보류가 안전하다(2026-08-06 사용자 결정). 순서를 뒤집지 마라.
    `is_insufficient_*` 2종과는 상호 배타 유지.
    호출자: OrderEngine 의 시장가 거부 → 지정가 5호가 폴백 1회 분기.
    """
    msg1 = err.msg1 or ""
    return any(kw in msg1 for kw in _MARKET_ORDER_DISALLOWED_KEYWORDS)


def is_market_closed_rejection(err: KisApiError) -> bool:
    """KIS 응답이 '장운영시간 외' 류의 시간 거부인지 판단.

    동일 msg_cd(APBK0918) 가 보유부족/자금부족/시간외 거부 모두에 사용되므로
    msg1 키워드 (`_MARKET_CLOSED_KEYWORDS`) 로 분리한다.
    True 면 `is_insufficient_*` 는 모두 False 로 떨어져야 한다.
    호출자: `execute_sell` 이 positions(메모리/DB)·`_selling` 보존 + 재시도 중단 결정.
    `SellRejectionTracker.is_blocked()` 2단계 TTL (KRX 메인 5분 / NXT 다음 09:00) 가드.
    """
    msg1 = err.msg1 or ""
    return any(kw in msg1 for kw in _MARKET_CLOSED_KEYWORDS)


def is_insufficient_cash(err: KisApiError) -> bool:
    """KIS 매수 실패 응답이 '주문가능금액 부족'(예수금 부족) 사유인지 판단.

    msg_cd 화이트리스트: APBK0919 / EGW00120.
    msg1 키워드 ("부족" + "주문가능금액/예수금/현금") 동시 만족 시도 True.
    APBK0918 은 동일 msg_cd 가 시간외 거부에도 쓰이므로 msg1 의 현금부족 키워드를 확인한다.
    호출자: OrderEngine 의 `block_buy(now + 900s)` 매수 락 결정.
    """
    msg_cd = (err.msg_cd or "").upper()
    msg1 = err.msg1 or ""

    # 1) 명시적 시간외 거부면 자금 락 걸지 않는다 (단, msg1 에 현금 키워드가 동반되면 후속 가드에서 True)
    cash_keyword = "부족" in msg1 and (
        "주문가능금액" in msg1 or "예수금" in msg1 or "현금" in msg1
    )
    if is_market_closed_rejection(err) and not cash_keyword:
        return False

    if msg_cd in {"APBK0919", "EGW00120"}:
        return True
    # APBK0918 은 msg1 에 현금 키워드가 있을 때만 자금 부족으로 분류 (시간외 거부와 분리)
    if msg_cd == "APBK0918":
        return cash_keyword
    if cash_keyword:
        return True
    return False


def is_sell_qty_exceeded(err: KisApiError) -> bool:
    """KIS 매도 거부가 '주문 가능한 수량 초과'(APBK0400) 인지 판단 (cycle236, N2).

    의미 = "요청 수량 > 매도 가능 수량" — **부분 보유가 내재된 코드**라
    `is_insufficient_quantity`(positions 통째 삭제 경로)에 흡수하면 안 된다:
    257720 실사고(08-28)처럼 실보유 2주가 남은 상태에서 삭제하면 잔여 수량이
    손절 감시 밖으로 떨어진다. 호출자(`execute_sell`)는 이 분류에서 잔고를
    재대조해 수량을 보정 후 재시도한다.

    보수 매칭 = msg_cd **APBK0400** ∧ msg1 에 "수량"·"초과" 동시(정본 오류코드
    사전이 MCP/로컬 문서에 없어 실측 3건(TTTC0011U 매도, 08-28 15:20)이 근거 —
    APBK0400 이 다른 문맥에 재사용돼도 문구 불일치로 오분류 차단). 소비처는
    매도 경로 한정.
    """
    msg_cd = (err.msg_cd or "").upper()
    msg1 = err.msg1 or ""
    return msg_cd == "APBK0400" and ("수량" in msg1 and "초과" in msg1)


def is_insufficient_quantity(err: KisApiError) -> bool:
    """KIS 매도 실패 응답이 '매도가능수량 부족'(보유 부족) 사유인지 판단.

    msg_cd 화이트리스트: APBK1234.
    msg1 키워드 ("부족" + "매도가능/보유수량/잔고") 동시 만족 시도 True.
    APBK0918 은 동일 msg_cd 가 시간외 거부에도 쓰이므로 msg1 키워드로 분리한다.
    시간외 거부면 positions 보존을 위해 False 를 반환한다.
    호출자: `execute_sell` 이 3회 재시도 생략 + 즉시 break + 메모리/DB positions 정리.
    """
    msg_cd = (err.msg_cd or "").upper()
    msg1 = err.msg1 or ""

    holding_keyword = "부족" in msg1 and (
        "매도가능" in msg1 or "보유수량" in msg1 or "잔고" in msg1
    )

    # 1) 시간외 거부 + 보유부족 키워드 없음 → 보유 부족 아님 (positions 보존)
    if is_market_closed_rejection(err) and not holding_keyword:
        return False

    if msg_cd == "APBK1234":
        return True
    # APBK0918 은 msg1 에 보유부족 키워드가 있을 때만 True (시간외 거부와 분리)
    if msg_cd == "APBK0918":
        return holding_keyword
    if holding_keyword:
        return True
    return False


async def get_balance(afhr_flpr: str = "N") -> tuple[list[StockHolding], AccountSummary]:
    """주식 잔고 및 계좌 요약을 조회한다.

    `afhr_flpr`: `N`(기본, 정규장) / `Y`(시간외 단일가) / `X`(NXT 정규장).
    """
    params = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "AFHR_FLPR_YN": afhr_flpr,
        "OFL_YN": "",
        "INQR_DVSN": "01",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    data = await kis_get(BALANCE_URL, settings.get_tr_id("TTTC8434R"), params)

    holdings = [
        StockHolding(
            ticker=item["pdno"],
            name=item["prdt_name"],
            quantity=int(item["hldg_qty"]),
            sellable_quantity=int(item["ord_psbl_qty"]),
            avg_price=float(item["pchs_avg_pric"]),
            purchase_amount=int(item["pchs_amt"]),
            current_price=int(item["prpr"]),
            eval_amount=int(item["evlu_amt"]),
            eval_profit_loss=int(item["evlu_pfls_amt"]),
            eval_profit_rate=float(item["evlu_pfls_rt"]),
        )
        for item in data.get("output1", [])
        if int(item.get("hldg_qty", "0")) > 0
    ]

    summary_data = data.get("output2", [{}])
    s = summary_data[0] if summary_data else {}
    summary = AccountSummary(
        deposit=int(s.get("dnca_tot_amt", 0)),
        stock_eval_amount=int(s.get("scts_evlu_amt", 0)),
        total_eval_amount=int(s.get("tot_evlu_amt", 0)),
        net_asset=int(s.get("nass_amt", 0)),
        purchase_total=int(s.get("pchs_amt_smtl_amt", 0)),
        eval_total=int(s.get("evlu_amt_smtl_amt", 0)),
        profit_loss_total=int(s.get("evlu_pfls_smtl_amt", 0)),
    )

    return holdings, summary


async def get_daily_orders(target_date: str = "", exchange: str = "ALL") -> list[dict]:
    """당일(또는 지정일) 주문체결내역을 조회한다.

    KIS 주식일별주문체결조회 API (TTTC0081R).
    `exchange`: `ALL`(기본, KRX+NXT+SOR) / `KRX` / `NXT` / `SOR`.
    """
    from datetime import datetime as _datetime, timedelta as _timedelta, timezone as _timezone
    if not target_date:
        _KST = _timezone(_timedelta(hours=9))
        target_date = _datetime.now(_KST).date().strftime("%Y%m%d")

    params = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "INQR_STRT_DT": target_date,
        "INQR_END_DT": target_date,
        "SLL_BUY_DVSN_CD": "00",  # 전체
        "INQR_DVSN": "00",
        "PDNO": "",
        "CCLD_DVSN": "00",  # 전체
        "ORD_GNO_BRNO": "",
        "ODNO": "",
        "INQR_DVSN_3": "00",
        "INQR_DVSN_1": "",
        "EXCG_ID_DVSN_CD": exchange,
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    data = await kis_get(
        "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
        settings.get_tr_id("TTTC0081R"),
        params,
    )
    return data.get("output1", [])


async def get_buyable(ticker: str = "", price: int = 0) -> BuyableInfo:
    """매수 가능 금액/수량을 조회한다."""
    params = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "PDNO": ticker,
        "ORD_UNPR": str(price),
        "ORD_DVSN": "01",  # 시장가
        "CMA_EVLU_AMT_ICLD_YN": "N",
        "OVRS_ICLD_YN": "N",
    }

    data = await kis_get(PSBL_ORDER_URL, settings.get_tr_id("TTTC8908R"), params)
    output = data["output"]

    return BuyableInfo(
        cash_available=int(output["ord_psbl_cash"]),
        max_buy_amount=int(output["max_buy_amt"]),
        max_buy_quantity=int(output["max_buy_qty"]),
    )
