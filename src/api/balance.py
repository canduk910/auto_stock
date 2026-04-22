"""잔고조회, 매수가능조회 API 모듈.

- 잔고조회 (TTTC8434R)
- 매수가능조회 (TTTC8908R)
"""

import logging

from src.api.base import kis_get
from src.config import settings
from src.models.balance import AccountSummary, BuyableInfo, StockHolding

logger = logging.getLogger(__name__)

BALANCE_URL = "/uapi/domestic-stock/v1/trading/inquire-balance"
PSBL_ORDER_URL = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"


async def get_balance() -> tuple[list[StockHolding], AccountSummary]:
    """주식 잔고 및 계좌 요약을 조회한다."""
    params = {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "AFHR_FLPR_YN": "N",
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
