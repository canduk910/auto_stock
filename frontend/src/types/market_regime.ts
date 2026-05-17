/**
 * 사이클 2 (2026-05-17): 시장 레짐 타입 정의.
 *
 * 백엔드 `src/models/market_regime.py` 와 1:1.
 */

export interface MarketRegimeCurrent {
  regime: string | null
  regime_desc: string | null
  cycle_phase: string | null
  vix: number | null
  fear_greed_score: number | null
  buffett_ratio: number | null
  cash_min: number | null
  buy_blocked: boolean
  block_reason: string | null
  auto_regime_adjust: boolean
  cash_usage_ratio: number
  enabled: boolean
}

export interface MarketRegimeSnapshotItem {
  snapshot_date: string
  regime: string
  regime_desc: string | null
  cycle_phase: string | null
  vix: number | null
  fear_greed_score: number | null
  buffett_ratio: number | null
  computed_cash_usage_ratio: number | null
  buy_blocked: boolean
  block_reason: string | null
  created_at: string | null
}
