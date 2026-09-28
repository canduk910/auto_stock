/**
 * 종목 차트(KLineChart, 최근 5년 일·주·월봉) 응답 타입 — cycle387.
 *
 * 백엔드 `src/models/candle_chart.py::CandleBar`/`CandleChart` 와 1:1(필드명 동일).
 * 정본: `_workspace/red/cycle387_stock_chart_spec.md` §1.2.
 */

export type ChartPeriod = 'D' | 'W' | 'M'

export type IncompleteReason = 'call_cap' | 'time_budget' | 'window_error' | 'no_progress'

export interface StockChartBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
}

export interface StockChartData {
  ticker: string
  name: string | null
  period: ChartPeriod
  years: number
  adjusted: boolean
  market: string
  start_date: string
  end_date: string
  bars: StockChartBar[]
  complete: boolean
  incomplete_reason: IncompleteReason | null
  last_bar_provisional: boolean
  dropped_bars: number
  kis_calls: number
  cached: boolean
  fetched_at: string
}
