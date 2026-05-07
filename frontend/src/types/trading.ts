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
  strategies: Record<string, StrategyInfo>
}

export interface ScanStats {
  universe_candidates?: number
  universe_filtered?: number
  candle_fetch_ok?: number
  donchian_pass?: number
  ema_uptrend_pass?: number
  volume_pass?: number
  atr_pass?: number
  final_prepared?: number
  last_run_at?: string | null
}

export interface StrategyInfo {
  name: string
  enabled: boolean
  weight: number
  positions: number
  pending_buys: number
  position_tickers: string[]
  total_investment: number
  daily_realized_pnl: number
  buy_disabled: boolean
  buy_signals: BuySignal[]
  positions_detail: Record<string, PositionDetail>
  pending_buy_tickers: string[]
  scanned_count?: number
  scanned_tickers?: string[]
  targets?: Record<string, unknown>
  scan_stats?: ScanStats | null
  params?: Record<string, unknown>
  invested_amount?: number
  min_weight?: number
}

export interface StrategyListItem {
  key: string
  name: string
  enabled: boolean
  weight: number
  params?: Record<string, unknown>
  min_weight?: number
  invested_amount?: number
  total_investment?: number
}

export interface StrategiesResponse {
  strategies: StrategyListItem[]
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

export interface PendingBuyOrder {
  ticker: string
  name?: string
  price: number
  quantity: number
}

export interface OrderStatus {
  pending_buy_tickers: string[]
  pending_buy_orders: Record<string, PendingBuyOrder>
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
  daily_realized_pnl?: number
  net_external_cashflow?: number
  deposit?: number
  cumulative_return_rate?: number
}

export interface TradeRecord {
  id: number
  timestamp: string
  ticker: string
  ticker_name: string
  trade_type: string
  price: number
  quantity: number
  profit_loss: number
  status: string
  strategy: string
  order_no: string
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
