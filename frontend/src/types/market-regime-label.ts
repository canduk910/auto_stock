/**
 * cycle410 — `GET /api/market-regime-label` 응답 타입(6장세 라벨, 관찰 전용).
 * 정의 정본 = `src/engine/market_regime_label.py`.
 */
export type RegimeDirection = 'up' | 'flat' | 'down'
export type RegimeVolatility = 'stable' | 'volatile'
export type RegimeLabel =
  | 'stable_up'
  | 'volatile_up'
  | 'stable_flat'
  | 'volatile_flat'
  | 'stable_down'
  | 'volatile_down'

export interface MarketRegimeLabelToday {
  /** 라벨을 매긴 날(KST, YYYY-MM-DD) */
  date: string
  label: RegimeLabel
  direction: RegimeDirection
  volatility: RegimeVolatility
  /** 60일선의 20일 기울기(%) */
  slope_pct: number
  /** 20일 변동성(연율 %) */
  vol_pct: number
  /** 쓴 마지막 봉 날짜 — 오늘 봉은 쓰지 않는다(D-1 기준) */
  basis_date: string
}

export type MarketUnitMode = 'off' | 'shadow' | 'enforce'
export type MarketUnitState = 'up_rising' | 'up_falling' | 'down_rising' | 'down_falling'

/** 시장 유닛 — 운영 판정 `market_unit.classify` 그대로(직전 영업일 봉까지 80봉). */
export interface MarketUnitToday {
  /** 신규 진입 설계 랏 배수(1 / 0.75 / 0.5 / 0). 못 매기면 null */
  m: number | null
  state: MarketUnitState | null
  above_sma60: boolean | null
  sma60_rising: boolean | null
  close: number | null
  sma60: number | null
  basis_date: string
  /** `db_recompute` = 엔진 메모리 값이 아니라 운영 DB 종가로 같은 판정 함수를 다시 부른 값 */
  source: 'db_recompute'
  /** 축소 대상 전략별 `market_unit_mode`(엔진 값). null = 모른다(미등록·읽기 실패) */
  modes: Record<string, MarketUnitMode | null>
}

export interface MarketRegimeLabelData {
  today: MarketRegimeLabelToday
  /** 최근 60거래일(마지막 = 오늘) */
  history: { date: string; label: RegimeLabel; m: number | null }[]
  /** 오늘 장세가 이어진 첫 날 */
  since: string
  /** true 면 since 는 읽은 이력의 첫 라벨일 — 실제 시작은 그보다 이르다 */
  since_truncated: boolean
  /** 읽은 첫 봉 날짜(상태를 걸어 온 출발점) */
  warmup_from: string
  market_unit: MarketUnitToday
  thresholds: {
    ma_window: number
    slope_lookback: number
    vol_window: number
    dir_enter_pct: number
    dir_exit_pct: number
    vol_high_pct: number
    vol_low_pct: number
  }
}
