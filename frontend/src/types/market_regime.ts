/**
 * 사이클 2 (2026-05-17): 시장 레짐 타입 정의.
 * 사이클 E-1 (2026-07-31) → 사이클 I (2026-08-03): 지수ETF 레짐 4 필드 추가 +
 * `buy_blocked` 항상 false 로 전환(레짐 매수 게이트 제거) — `block_reason` 은
 * 관찰용 "레짐 경보 사유" 로만 유지.
 *
 * 백엔드 `src/models/market_regime.py` 와 1:1. **필드는 cycle315 에서도 그대로다.**
 *
 * 값의 출처만 바뀌었다 — 외부 dkstock.cloud(2026-08-18 철거)가 아니라 **우리 macro
 * 컨테이너**(`macro/macro_lite`)가 계산한 값을 백엔드가 실어 보낸다. 그래서:
 * - `regime` 은 `accumulation | selective | cautious | defensive` 4종 중 하나다
 *   (`macro/macro_lite/regime.py::REGIME_MATRIX`). `neutral`·`aggressive` 는 없다.
 * - `cycle_phase` 는 `recovery | expansion | overheating | contraction` 4국면이다.
 * - `buffett_ratio` 는 **비율**이다(시총/GDP, 예: 2.626 = 262.6%). 퍼센트가 아니다.
 * - `cash_min` 은 퍼센트 정수다(25/35/50/75). 자금 사용률 = (100 − cash_min)%.
 * - 이 응답은 `_boot()` 시점 **스냅샷**이다. 라이브 값은 `/macro` 화면이 따로 본다.
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
