// cycle411 — 실비용(수수료·세금) 추정 엔드포인트 응답 타입.
// `GET /api/costs/today?strategy=` · `GET /api/costs/daily?from=&to=`
// 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md`.

export type CostStatus = 'settled' | 'estimated' | 'mixed'
export type CostRateSource = 'measured' | 'default'

export interface CostTotal {
  gross_pnl: number
  fee: number
  tax: number
  net_pnl: number
}

export interface CostTodayStrategy extends CostTotal {
  strategy: string
}

export interface CostTodayData {
  date: string
  fee_rate: number
  tax_rate: number
  rate_source: CostRateSource
  cost_status: CostStatus
  strategies: CostTodayStrategy[]
  total: CostTotal
}

export interface CostDailyDay {
  date: string
  fee: number
  tax: number
  slippage_won: number | null
  slippage_n: number
  cost_status: CostStatus
}

export interface CostDailyData {
  from: string
  to: string
  days: CostDailyDay[]
}
