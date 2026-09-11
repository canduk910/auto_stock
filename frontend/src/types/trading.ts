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
  // 사이클 175 — 코스피200∪코스닥150 합집합 (시총/거래대금 컷 전, DB funnel step1 정합)
  universe_union?: number
  universe_candidates?: number
  universe_filtered?: number
  candle_fetch_ok?: number
  donchian_pass?: number
  ema_uptrend_pass?: number
  volume_pass?: number
  atr_pass?: number
  final_prepared?: number
  last_run_at?: string | null
  // 고지로 대순환 전용 깔때기 키 (kojiro `_empty_scan_stats` 정합, 백엔드 미배포 시점 호환 옵셔널)
  band_pass?: number
  stage_valid_pass?: number
  stage1_uptrend_pass?: number
  strict_entry_pass?: number
}

// 고지로 후보 종목 상태 (get_targets_status). StrategyInfo.targets 엔트리 캐스팅용.
export interface KojiroTarget {
  name?: string            // 종목명 (백엔드 resolve_ticker_name, miss 시 "" 또는 부재 — ticker 폴백)
  prev_close: number
  atr: number
  stage: number           // 대순환 스테이지 1~6 (0 = 판별 불가)
  ema_s: number
  ema_m: number
  ema_l: number
  atr_ratio?: number       // atr/prev_close (백엔드 노출, 부재 시 프론트 계산)
  target_price?: number
}

// VCP(vcp_breakout)/BFB(bull_flag_breakout) 후보 진단 그리드 전용 (get_targets_status).
// StrategyInfo.targets 엔트리 캐스팅용 — "왜 안 사는가" 원인 규명 필드 (2026-08-06).
// VCP: base_high/base_low/ema50 전용. BFB: pole_*/flag_*/measured_target/breakout_seen_at/
// retention_minutes 전용. target_price(돌파선)/stop_line(손절선)은 양쪽 공통(백엔드가
// VCP=base_high→target_price, BFB=flag_high→target_price 로 이미 별칭 처리해 보냄).
export interface BreakoutDiagTarget {
  name?: string             // 종목명 (resolve_ticker_name, miss 시 "" — ticker 폴백)
  prev_close: number
  atr14: number
  stop_line: number         // 이탈 시 STOP_LOSS 가 나는 선 (VCP=base_low / BFB=flag_low)
  volume_threshold: number
  bought_today: boolean
  in_cooldown: boolean
  cooldown_until?: string | null   // ISO date(YYYY-MM-DD) 또는 null
  target_price: number      // 돌파선 (VCP=base_high / BFB=flag_high)
  // VCP 전용
  base_high?: number
  base_low?: number
  ema50?: number
  // BFB 전용
  pole_start?: number
  pole_high?: number
  flag_high?: number
  flag_low?: number
  measured_target?: number
  breakout_seen_at?: string | null  // BFB 첫 돌파 감지 KST ISO — retention_minutes 대기 기준
  retention_minutes?: number
  // VB 호환 키 (scheduler._confirm_breakout_open_prices 8영역 소비 계약 — 무시해도 됨)
  k?: number
  open_price?: number
  target_offset?: number
  open_confirmed?: boolean | Record<string, boolean>
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
  // 사이클 18 (2026-05-19, C-1) — 전략별 매매 가능 보드 (DEFAULT_TRADABLE_BOARDS 또는 params).
  // 옵셔널 — 백엔드 미반영 시점 호환. ScanMonitor 가 활성 보드 ∩ tradable_boards = ∅ 시
  // "돌파 (대기 — 보드라벨)" 회색 라벨로 분기.
  tradable_boards?: string[]
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
  // G3 (2026-05-12) — tick_coverage 4종. 운영자 가시화용 보조 카운트.
  // 백엔드 미반영 시점 호환을 위해 optional. ScanMonitor 가 색상 배지로 노출.
  tick_coverage_total?: number
  tick_coverage_acked?: number
  tick_coverage_fresh?: number
  tick_coverage_stale?: number
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
  open_price?: number
  target_price?: number
  k?: number
  board?: string         // VB/LTV 보드별 분리 (main/pre_nxt/post_nxt) — Phase 5
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

export interface TradePair {
  buy_date: string | null
  buy_time: string | null
  sell_date: string | null
  sell_time: string | null
  ticker: string
  ticker_name: string
  buy_price: number
  buy_qty: number
  sell_price: number | null
  sell_qty: number | null
  profit_loss: number | null
  profit_rate: number | null
  status: 'closed' | 'open'
  strategy: string
  // cycle276 — AI 매수평가 조인 키. 손익 화면은 테이블이 아니라 `get_trade_pairs` 가
  // 매번 계산하는 뷰라 행을 가리키는 안정적 키가 없었다(명세 §8). 한 페어가 매수 주문
  // 2건 이상을 품은 사례가 운영 DB 전 기간 614행 중 9건이라 **단수 필드로는 부족**하다.
  //   `pair_key` = `strategy:ticker:첫 매수 order_no` — 빈 값이면 null(버튼 비활성).
  buy_order_nos: string[]
  sell_order_nos: string[]
  pair_key: string | null
}

export interface TradePnLSummary {
  realized_total_krw: number
  realized_rate_pct: number
  win_count: number
  loss_count: number
  even_count: number
  win_rate_pct: number
  closed_count: number
}

export interface TradePnLData {
  pairs: TradePair[]
  page: number
  size: number
  total: number
  total_pages: number
  summary?: TradePnLSummary
}

export interface ActionResult {
  success: boolean
  message: string
}
