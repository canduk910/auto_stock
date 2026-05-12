export interface Holding {
  ticker: string
  name: string
  quantity: number
  sellable_quantity: number
  avg_price: number
  purchase_amount: number
  current_price: number
  eval_amount: number
  eval_profit_loss: number
  eval_profit_rate: number
  // J1 (2026-05-11) — stock_master 캐시 조인 결과.
  // 미캐시/조회 예외 시 null/undefined — UI 는 "확인중" 표시.
  nxt_tradable?: boolean | null
  krx_halted?: boolean | null
  excg_dvsn_cd?: string | null
}

export interface BalanceSummary {
  deposit: number
  stock_eval_amount: number
  total_eval_amount: number
  net_asset: number
  purchase_total: number
  eval_total: number
  profit_loss_total: number
}

export interface BalanceData {
  holdings: Holding[]
  summary: BalanceSummary
}
