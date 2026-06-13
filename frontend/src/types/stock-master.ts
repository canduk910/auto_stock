/**
 * stock_master UI 타입 정의 (사이클 85, 2026-06-09).
 *
 * 백엔드 GET 라우트 응답 스키마 1:1 매핑:
 *   GET /api/stock-master/stats
 *   GET /api/stock-master/list
 *   GET /api/stock-master/scan-pool/summary
 *   GET /api/stock-master/{ticker}
 *   GET /api/stock-master/{ticker}/history
 *   GET /api/stock-master/{ticker}/daily  — 사이클 124 신규
 *
 * 모두 ApiResponse<T> 래퍼 (success / data / message) — data.data 추출.
 */

export interface StockMasterStats {
  count_all: number
  bfdy_clpr_present: number  // 사이클 81 키 정합 가시화 (prdy_clpr → bfdy_clpr 시정 효과)
  nxt_tradable_count: number
  top_10_recent: Array<{ ticker: string; name: string; refreshed_at: string }>
  // 사이클 124 Q3=A — 4 신규 stats 키
  with_hts_avls: number        // 시가총액 보유 종목 수
  with_acml_tr_pbmn: number    // 누적 거래대금 보유 종목 수
  total_daily_rows: number     // 일봉 총 행 수
  last_daily_load_at: string | null  // 마지막 일봉 적재 시각 (KST ISO, null = 미적재)
}

/**
 * 사이클 124 Q1=A — 일봉 데이터 행 타입.
 * GET /api/stock-master/{ticker}/daily?days=30 응답 배열의 개별 원소.
 */
export interface StockMasterDailyRow {
  bas_dd: string        // 기준일자 (YYYYMMDD)
  open_price: number
  high_price: number
  low_price: number
  close_price: number
  volume: number
  trade_value: number   // 거래대금 (원)
  change_rate: number   // 등락률 (%)
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

/**
 * 사이클 126 — POST /api/stock-master/basics/refresh 응답 타입.
 * KIS CTPF1002R 매스 보강 (NXT/정지/관리종목 영역 시정).
 */
export interface BasicsRefreshResult {
  total: number
  updated: number
  skipped: number
  failed: number
  elapsed_ms: number
}

/**
 * 사이클 126 — POST /api/stock-master/daily/refresh 응답 타입.
 * 일봉 적재 수동 trigger (사이클 122 자동 task 와 동일 함수 호출).
 */
export interface DailyRefreshResult {
  total: number
  fetched: number
  upserted_rows: number
  skipped_fresh: number
  failed: number
  db_write_failures: number
  elapsed_ms: number
  mode: string
}

/**
 * 사이클 127 — fire-and-forget 응답 (3 POST 라우트 공통).
 *
 * 배경: 사이클 126 push 후 사용자 보고 = "기본정보 새로고침" 13분 39초 후
 * "KIS API 일시 결함" 토스트. 진짜 결함 = axios 디폴트 timeout silent 결함.
 * 시정: POST 라우트 fire-and-forget + GET /refresh-progress 5초 폴링.
 */
export type RefreshTaskKey = 'universe' | 'basics' | 'daily'
export type RefreshStatus = 'idle' | 'running' | 'completed' | 'failed'

export interface RefreshStartedResponse {
  status: 'started'
  task_key: RefreshTaskKey
}

/**
 * 사이클 127 — 3 작업 진행 state schema (10 키 정확 영속).
 * 회귀 가드 영속 의무 (G-STATE1 / G-ROUTE-GET1).
 */
export interface RefreshProgress {
  status: RefreshStatus
  total: number
  processed: number
  updated: number
  skipped: number
  failed: number
  started_at: string | null  // KST +09:00 ISO
  finished_at: string | null
  elapsed_ms: number
  error_message: string | null
}

/**
 * 사이클 127 — GET /refresh-progress 응답 (3 작업 통합).
 *
 * 5초 폴링으로 RefreshProgressBanner 가 상단 가시화.
 */
export interface AllRefreshProgress {
  universe: RefreshProgress
  basics: RefreshProgress
  daily: RefreshProgress
}
