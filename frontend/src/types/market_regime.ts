/**
 * 사이클 2 (2026-05-17): 시장 레짐 타입 정의.
 * 사이클 E-1 (2026-07-31) → 사이클 I (2026-08-03): 지수ETF 레짐 4 필드 추가 +
 * `buy_blocked` 항상 false 로 전환(레짐 매수 게이트 제거) — `block_reason` 은
 * 관찰용 "레짐 경보 사유" 로만 유지.
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
  etf_kospi_stage: number | null
  etf_kosdaq_stage: number | null
  etf_defensive: boolean | null
  etf_enabled: boolean
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
