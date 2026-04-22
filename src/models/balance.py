"""잔고 데이터 모델."""

from pydantic import BaseModel


class StockHolding(BaseModel):
    ticker: str                # pdno
    name: str                  # prdt_name
    quantity: int              # hldg_qty
    sellable_quantity: int     # ord_psbl_qty
    avg_price: float           # pchs_avg_pric
    purchase_amount: int       # pchs_amt
    current_price: int         # prpr
    eval_amount: int           # evlu_amt
    eval_profit_loss: int      # evlu_pfls_amt
    eval_profit_rate: float    # evlu_pfls_rt


class AccountSummary(BaseModel):
    deposit: int               # dnca_tot_amt (예수금총금액)
    stock_eval_amount: int     # scts_evlu_amt (유가평가금액)
    total_eval_amount: int     # tot_evlu_amt (총평가금액)
    net_asset: int             # nass_amt (순자산금액)
    purchase_total: int        # pchs_amt_smtl_amt (매입금액합계)
    eval_total: int            # evlu_amt_smtl_amt (평가금액합계)
    profit_loss_total: int     # evlu_pfls_smtl_amt (평가손익합계)


class BuyableInfo(BaseModel):
    cash_available: int        # ord_psbl_cash
    max_buy_amount: int        # max_buy_amt
    max_buy_quantity: int      # max_buy_qty
