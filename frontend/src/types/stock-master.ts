/**
 * stock_master UI 타입 정의 (사이클 85, 2026-06-09).
 *
 * 백엔드 5 GET 라우트 응답 스키마 1:1 매핑:
 *   GET /api/stock-master/stats
 *   GET /api/stock-master/list
 *   GET /api/stock-master/scan-pool/summary
 *   GET /api/stock-master/{ticker}
 *   GET /api/stock-master/{ticker}/history
 *
 * 모두 ApiResponse<T> 래퍼 (success / data / message) — data.data 추출.
 */

export interface StockMasterStats {
  count_all: number
  bfdy_clpr_present: number  // 사이클 81 키 정합 가시화 (prdy_clpr → bfdy_clpr 시정 효과)
  nxt_tradable_count: number
  top_10_recent: Array<{ ticker: string; name: string; refreshed_at: string }>
}

export interface StockMasterListItem {
  ticker: string
  name: string
  excg_dvsn_cd: string | null
  nxt_tradable: boolean
  krx_halted: boolean
  admin_item: boolean
  refreshed_at: string  // KST +09:00 ISO
  raw: Record<string, unknown>
}

export type StockMasterDetail = StockMasterListItem

export interface StockMasterHistoryItem {
  id: number
  ticker: string
  change_type: 'INSERT' | 'UPDATE' | 'DELETE' | 'TTL_REFRESH'
  before_raw: Record<string, unknown> | null
  after_raw: Record<string, unknown> | null
  changed_at: string  // KST +09:00 ISO
}

export interface ScanPoolSummary {
  eager_refresh_today: number  // 사이클 83 [scan_pool_eager_refresh] emit 카운트
}

/**
 * 사이클 90 — POST /api/stock-master/refresh-universe 응답 타입 (Q25=A + Q26=A).
 * universe: 즉시 적재된 ticker 수, elapsed_ms: KIS 조회 소요 시간.
 */
export interface RefreshUniverseResult {
  universe: number
  elapsed_ms: number
}
