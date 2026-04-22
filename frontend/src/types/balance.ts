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
