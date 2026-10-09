/**
 * `GET /api/market/breadth` 응답 타입 — 시장 등락 통계 (cycle416, 매크로 6번째 섹션).
 *
 * 정의 정본 = `src/engine/market_breadth.py`(leaf) · `src/routes/market_breadth.py`(라우트).
 * `ApiResponse<MarketBreadthData>` 래퍼를 쓴다(우리 `apiClient` 공통 계약) — macro 5섹션
 * (`types/macro.ts`)과 달리 이 엔드포인트는 KRX 백엔드가 직접 낸다.
 */

export type BreadthMarketKey = 'kospi' | 'kosdaq' | 'total'

/** 하루치 시장 하나의 집계(leaf `aggregate_rows`/`merge_stats` → `stats_to_dict`, 11키). */
export interface BreadthDayStats {
  rows: number
  traded: number
  up: number
  down: number
  flat: number
  limit_up: number
  limit_down: number
  no_trade: number
  out_of_band: number
  unparsed: number
  /** `round(up/traded, 4)`. traded 가 0 이면 null. */
  up_ratio: number | null
}

/** 창 전체 합(leaf `summarize` → `stats_to_dict`, 9키). */
export interface BreadthSummary {
  n_days: number
  up: number
  down: number
  flat: number
  limit_up: number
  limit_down: number
  no_trade: number
  up_ratio: number | null
  /** `round(Σup/Σdown×100, 1)`. Σdown 이 0 이면 null. */
  adr: number | null
}

export interface BreadthDay {
  /** KST `YYYY-MM-DD` */
  date: string
  kospi: BreadthDayStats
  kosdaq: BreadthDayStats
  total: BreadthDayStats
}

export interface BreadthWindow {
  from: string
  to: string
  /** 실제로 채운 날 수(빠진 날 제외) */
  n_days: number
  /** 요청한 영업일 수(쿼리 `days`) */
  requested: number
  /** 한도 안에서 요청한 날 수를 다 채웠는가 */
  complete: boolean
  lookback_from: string
}

export interface MarketBreadthData {
  /** 응답을 만든 시각(ISO, KST 또는 UTC — 화면은 `formatKstDateTime` 으로 환산) */
  asof_kst: string
  window: BreadthWindow
  /** 최신 날짜 먼저 */
  days: BreadthDay[]
  summary: Record<BreadthMarketKey, BreadthSummary>
  adr_reference: { oversold: number; overheated: number }
  source: string
  /** KRX 응답이 없어 빈 칸인 평일(최신 먼저) */
  missing_dates: string[]
  /** 거래소가 쉰 날(빈 응답, 정상) — 화면에는 표시하지 않는다 */
  empty_dates: string[]
  /** 아직 KRX 에 올라오지 않은 당일(= d-1) 날짜, 없으면 null */
  pending_date: string | null
}
