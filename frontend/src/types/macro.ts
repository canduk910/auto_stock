/**
 * `/api/macro/*` 5개 엔드포인트 응답 타입 (cycle303 — macro_lite 이식 1단계).
 *
 * 🔴 이 응답들은 우리 `ApiResponse<T>` 래퍼(`{success, data, message}`)를 쓰지 않는다.
 * macro 서비스(`macro/main.py`)는 독립 FastAPI 프로세스이고, `macro_lite/router.py` 가
 * 각 GET 을 원본 그대로 반환한다(원본 `stock-manager` 의 `routers/macro.py` 계약을
 * 그대로 따른다 — `packaging/macro_lite/backend/macro_lite/service.py` 의 5개 함수가
 * 전부 `{ <section>: T | null, updated_at: str, errors: list[str] }` 형태를 리턴).
 * 따라서 `frontend/src/api/macro.ts` 는 axios 응답의 `.data` 를 그대로 돌려준다
 * (`.data.data` 로 한 번 더 벗기지 않는다).
 *
 * 필드 출처 = `packaging/macro_lite/backend/macro_lite/{fetcher,cycle,regime,service}.py`
 * (2026-09-18 읽음) + `packaging/macro_lite/backend/tests/test_service_router.py` 의
 * 실측 mock 반환값. 타입 계약 2가지(팀장 명세 §6, cycle303 spec §6)는 아래 두 곳에
 * 그대로 보존한다 — `MacroCycleResponse.cycle` 을 **optional** 로 두어
 * `MacroCycleSection` 의 `data.cycle || data` 폴백을, `RegimeData` 를 프롭에서
 * **optional/nullable** 로 받아 `regime?.regime` optional chaining 을 계약으로 지킨다.
 */

// ── 공통 ──────────────────────────────────────────────────────────────────

/** 스파크라인 포인트 — `fetcher.py` 의 환율/원자재 fetch 는 `{date, v}` 객체를 담는다. */
export interface MacroSparklinePoint {
  date?: string
  v: number
}

/** NBER 침체 / S&P 약세장 구간(`events.py` 정적 상수 → `service.py::_events_for_history` 임베드). */
export interface MacroEvent {
  start: string
  end: string
  label: string
}

export interface MacroEvents {
  recessions: MacroEvent[]
  bear_markets: MacroEvent[]
}

// ── 환율 (`GET /api/macro/currencies`) ──────────────────────────────────────

export interface CurrencyQuote {
  symbol: string
  name: string
  price: number
  prev_close: number
  change: number
  change_pct: number
  sparkline: MacroSparklinePoint[]
}

export interface CurrenciesResponse {
  currencies: CurrencyQuote[]
  updated_at: string
  errors: string[]
}

// ── 원자재 (`GET /api/macro/commodities`) ───────────────────────────────────

export interface CommodityQuote {
  symbol: string
  name: string
  price: number
  prev_close: number
  change: number
  change_pct: number
  sparkline: MacroSparklinePoint[]
}

export interface CommoditiesResponse {
  commodities: CommodityQuote[]
  updated_at: string
  errors: string[]
}

// ── 장단기 금리차 (`GET /api/macro/yield-curve`) ─────────────────────────────

export interface YieldCurveCurrent {
  "3m"?: number | null
  "5y"?: number | null
  "10y"?: number | null
  "30y"?: number | null
}

export interface YieldCurveHistoryRow {
  date: string
  y3m: number | null
  y10y: number | null
  spread: number | null
}

export interface YieldCurveData {
  current: YieldCurveCurrent
  spread_10y_3m: number | null
  history: YieldCurveHistoryRow[]
  inverted: boolean
  /** `service.py::_events_for_history` 가 매번 재주입(정적 상수라 비용 0). */
  events?: MacroEvents
}

export interface YieldCurveResponse {
  yield_curve: YieldCurveData | null
  updated_at: string
  errors: string[]
}

// ── 하이일드 스프레드 (`GET /api/macro/credit-spread`) ───────────────────────

export type OasSentiment = "extreme_greed" | "greed" | "normal" | "fear" | "extreme_fear"

export interface OasHistoryRow {
  date: string
  oas: number
}

export interface OasStats {
  p10?: number | null
  p25?: number | null
  p75?: number | null
  p90?: number | null
  mean?: number | null
  max?: number | null
  max_date?: string | null
  [key: string]: number | string | null | undefined
}

export interface CreditSpreadData {
  oas_current: number | null
  oas_history_10y?: OasHistoryRow[]
  oas_history_5y?: OasHistoryRow[]
  oas_history?: OasHistoryRow[]
  oas_stats?: OasStats
  oas_percentile: number | null
  oas_zscore?: number | null
  oas_sentiment?: OasSentiment | null
  ig_current: number | null
  hy_ig_spread: number | null
  /** `hy_oas`/`ig_oas` 가 섞여 있으면 백엔드(`service.py`)가 캐시를 폐기하고 재조회한다. */
  partial_failure: string[]
  events?: MacroEvents
}

export interface CreditSpreadResponse {
  credit_spread: CreditSpreadData | null
  updated_at: string
  errors: string[]
}

// ── 경기 사이클 + 투자 체제 (`GET /api/macro/macro-cycle`) ───────────────────

export type CyclePhase = "recovery" | "expansion" | "overheating" | "contraction"

export interface CycleScoreItem {
  score: number
  weight: number
  signal: string
}

/** `cycle.py::determine_cycle_phase` 반환값. */
export interface MacroCycleData {
  phase: CyclePhase
  phase_label: string
  phase_desc: string
  confidence: number
  scores: Record<string, CycleScoreItem>
  leader_sectors: string[]
}

export type InvestmentRegime = "accumulation" | "selective" | "cautious" | "defensive"

/** `regime.py::determine_regime` 반환값. */
export interface RegimeData {
  regime: InvestmentRegime
  regime_desc: string
  params?: Record<string, unknown>
  vix?: number | null
  buffett_ratio?: number | null
  fear_greed_score?: number | null
  buffett_level?: string | null
  fg_level?: string | null
  credit_adjustment?: number | null
  credit_override?: boolean | null
}

/**
 * 타입 계약 1(cycle303 spec §6) — `cycle` 을 optional 로 둔다.
 * `MacroCycleSection.tsx` 의 `const cycle = data.cycle || data` 폴백이 이 optionality 에
 * 기대어 산다(일부 배포/프록시 경로가 `{cycle, regime}` 로 감싸지 않고 `MacroCycleData` 를
 * 바로 줄 가능성을 방어한 원본 코드 — "불필요한 방어"로 지우지 않는다).
 */
export interface MacroCycleResponse {
  cycle?: MacroCycleData | null
  regime?: RegimeData | null
  updated_at: string
  errors: string[]
}
