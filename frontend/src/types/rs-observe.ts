/**
 * RS·재무 관찰 화면 — `GET /api/rs-observe` 응답(`src/routes/rs_observe.py`).
 * 칸 = `candidate_score_snapshots`(migration 052) 1:1. 점수 칸 null = 「모름」(0 이 아니다).
 */

export type RsObserveRole = 'candidate' | 'held'

export interface RsObserveRow {
  target_date: string
  strategy_id: string
  ticker: string
  name: string
  role: RsObserveRole | string
  rs_raw: number | null
  rs_pct: number | null
  sector_key: string | null
  vs_sector: number | null
  sector_pct: number | null
  in_sector_pct: number | null
  revision_breadth: number | null
  target_median_change: number | null
  opinion_brokers: number | null
  fin_quarter: string | null
  op_income_q: number | null
  op_income_q_yoy: number | null
  op_turnaround: boolean | null
  op_yoy_growth: number | null
  revenue_yoy_growth: number | null
  net_turnaround: boolean | null
  roe: number | null
  debt_ratio_latest: number | null
  debt_ratio_down_years: number | null
  ttm_op_to_max_ratio: number | null
  rs_population: number | null
  computed_at: string
}

export interface RsObserveData {
  /** 보이는 날짜(기록이 하나도 없으면 null) */
  target_date: string | null
  /** 기록이 있는 날짜 — 최근 먼저 */
  dates: string[]
  strategies: string[]
  rows: RsObserveRow[]
}
