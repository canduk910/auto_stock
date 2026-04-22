export interface TradingStatusData {
  running: boolean
  env: string
  positions: number
  pending_buys: number
  position_tickers: string[]
  phase: string
  scan: ScanStatus
  positions_detail: Record<string, PositionDetail>
  orders: OrderStatus
  strategy: StrategyStatus
}

export interface TickerPrice {
  current_price: number
  open_price: number
  change_rate: number
  prdy_ctrt: number
}

export interface ScanStatus {
  filtered_tickers: string[]
  filtered_count: number
  subscribed_tickers: string[]
  subscribed_count: number
  last_scan_time: string | null
  ticker_names: Record<string, string>
  ticker_prices: Record<string, TickerPrice>
  ticker_market_info: Record<string, TickerMarketInfo>
}

export interface TickerMarketInfo {
  market_cap: number
  trade_amount: number
}

export interface PositionDetail {
  name?: string
  buy_price: number
  quantity: number
  high_since_buy: number
  is_next_day: boolean
}

export interface OrderFill {
  filled_qty: number
  order_qty: number
}

export interface OrderStatus {
  pending_buy_tickers: string[]
  fills: Record<string, OrderFill>
  pending_cancels: string[]
}

export interface BuySignal {
  ticker: string
  name?: string
  price: number
  open_price: number
  change_rate: number
  time: string
}

export interface StrategyStatus {
  buy_disabled: boolean
  daily_realized_pnl: number
  total_investment: number
  buy_signals: BuySignal[]
}

export interface PerformanceSummary {
  total_days: number
  total_profit_rate: number
  avg_daily_profit_rate: number
  latest_asset: number
}

export interface DailyPerformance {
  date: string
  total_asset: number
  daily_profit_rate: number
}

export interface MonthlyPerformance {
  month: string
  trading_days: number
  total_profit_rate: number
  latest_asset: number
}

export interface TradeRecord {
  [key: string]: unknown
}

export interface TradeHistoryData {
  trades: TradeRecord[]
  page: number
  size: number
  total: number
  total_pages: number
}

export interface ActionResult {
  success: boolean
  message: string
}
