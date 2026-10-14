/**
 * cycle456 — `GET /api/market-unit/chart` 응답 타입(시장 유닛 결정 과정 차트, 읽기 전용).
 * 정본 = `src/routes/market_unit_chart.py`. 판정 정의 = `src/engine/market_unit.py`.
 */
import type { MarketUnitMode, MarketUnitState } from './market-regime-label'

export type MarketKey = 'kospi' | 'kosdaq'

/** 봉 하나 — 그 봉 기준 판정은 다음 거래일 신규 진입에 쓰인다. 80봉 미만이면 판정 칸은 null. */
export interface MarketUnitBar {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  sma60: number | null
  /** 20봉 전의 60일선 */
  sma60_prev: number | null
  above: boolean | null
  rising: boolean | null
  state: MarketUnitState | null
  m: number | null
}

/** 스냅샷(운영 로더 재계산 또는 엔진 메모리). ok=false 면 m=1(fail-open) */
export interface MarketUnitSnapshot {
  ok: boolean
  state: MarketUnitState | 'unavailable' | null
  m: number | null
  reason: string | null
  bar_date: string | null
  expected_head: string | null
  close: number | null
  sma60: number | null
  sma60_prev: number | null
  above: boolean | null
  rising: boolean | null
}

export interface MarketUnitEffective {
  m: number | null
  /** `-` 제 시장 값 · `other_market` 다른 시장 값 · `none` 둘 다 결측 → 1 · `not_computed` 엔진 미계산 */
  fallback: '-' | 'other_market' | 'none' | 'not_computed'
  from_market: MarketKey | null
}

export interface MarketUnitChartMarket {
  index_code: string
  name: string
  rows: number
  bars: MarketUnitBar[]
  decision: MarketUnitSnapshot | null
  engine: MarketUnitSnapshot | null
  effective: MarketUnitEffective
}

export interface MarketUnitChartData {
  as_of: string
  markets: Record<MarketKey, MarketUnitChartMarket>
  modes: Record<string, MarketUnitMode | null>
  rules: {
    ma_window: number
    slope_lookback: number
    min_rows: number
    multipliers: Record<MarketUnitState, number>
  }
}
