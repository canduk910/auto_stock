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
)


def is_market_order_disallowed(err: KisApiError) -> bool:
    """KIS 응답이 '시장가 주문 불가' 류의 거부인지 판단.

    계양전기(012200) "시장가매매불가" 거부 대응 (2026-05-11).
    msg_cd 는 운영 로그(Phase A1) 누적 후 화이트리스트화 — 현재는 msg1 키워드 기반.
    기존 3종 분류(is_market_closed_rejection / is_insufficient_cash / is_insufficient_quantity)와
    상호 배타 — 이 함수가 True 이면 다른 3종은 모두 False 를 반환한다.
    """
    msg1 = err.msg1 or ""
    return any(kw in msg1 for kw in _MARKET_ORDER_DISALLOWED_KEYWORDS)


def is_market_closed_rejection(err: KisApiError) -> bool:
    """KIS 응답이 '장운영시간 외' 류의 시간 거부인지 판단.

    동일 msg_cd(APBK0918)가 보유부족/자금부족/시간외 거부 모두에 사용되므로
    msg1 키워드로 분리한다. True 면 `is_insufficient_*` 는 모두 False 로 떨어져야 한다.
    """
    msg1 = err.msg1 or ""
    return any(kw in msg1 for kw in _MARKET_CLOSED_KEYWORDS)


def is_insufficient_cash(err: KisApiError) -> bool:
    """KIS 매수 실패 응답이 '주문가능금액 부족'(예수금 부족) 사유인지 판단.

    msg_cd가 정확히 일치하지 않을 가능성에 대비해 msg1 키워드도 함께 본다.
    APBK0918 은 동일 msg_cd 가 시간외 거부에도 쓰이므로 msg1 의 현금부족 키워드를 확인한다.
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


def is_insufficient_quantity(err: KisApiError) -> bool:
    """KIS 매도 실패 응답이 '매도가능수량 부족'(보유 부족) 사유인지 판단.

    APBK0918 은 동일 msg_cd 가 시간외 거부에도 쓰이므로 msg1 키워드로 분리한다.
    시간외 거부면 positions 보존을 위해 False 를 반환한다.
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
    from datetime import date as _date
    if not target_date:
        target_date = _date.today().strftime("%Y%m%d")

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
