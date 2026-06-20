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
  // 사이클 129 — master_raw 별도 컬럼 영역 (Q6=C 영속 + 사이클 81 G-AST1 raw 분리 보호).
  // KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) record 영역.
  // KOSPI 70 컬럼 / KOSDAQ 64 컬럼 (전체 ~70 컬럼 영역, Q4=A 마스터 우선).
  master_raw?: Record<string, unknown> | null
  master_raw_updated_at?: string | null  // KST +09:00 ISO (16:30 task 갱신 시각)
}

/**
 * 사이클 128 — GET /api/stock-master/list 응답 schema 확장 (list[dict] → 객체 wrapping).
 * 4 query param 흡수: market / min_market_cap / min_trade_amount / name_substr.
 * total 필드 = 페이지네이션 정확도 (PostgREST count="exact" 사이클 126 패턴 답습).
 */
export interface StockMasterListResponse {
  items: StockMasterListItem[]
  total: number
  limit: number
  offset: number
}

/**
 * 사이클 128 — 종목목록 4 필터 입력 타입.
 * - market: 'KOSPI' | 'KOSDAQ' | null (전체)
 * - minMarketCapEok: 억원 단위 (운영자 친숙 — 백엔드 _eok_to_won 변환)
 * - minTradeAmountEok: 억원 단위
 * - nameSubstr: 부분 문자열 (대소문자 무시, 한글 IME composition 중 trigger 차단 의무)
 */
export interface StockMasterListFilter {
  market: 'KOSPI' | 'KOSDAQ' | null
  minMarketCapEok: number  // 0 = 무필터
  minTradeAmountEok: number
  nameSubstr: string  // 빈 문자열 = 무필터
}

export type StockMasterDetail = StockMasterListItem

/**
 * 사이클 169 (2026-06-20) — migration 036 (사이클 150) 신 스키마 동기화.
 *
 * 사이클 150 데이터폭주/Supabase 용량초과 시정 시 stock_master_history 를
 * `(ticker, seq)` PK 로 재설계: id/before_raw/after_raw 제거 → seq+raw 신설.
 * seq=0 최신본 스냅샷 / seq=1 직전본 스냅샷. 92K→7,146 row 용량 절감.
 * `change_type` 은 INSERT/UPDATE/DELETE 3종 (사이클 150 trigger 가 'TTL_REFRESH'
 * 미발화 — `OLD.raw IS DISTINCT FROM NEW.raw` 조건).
 */
export interface StockMasterHistoryItem {
  ticker: string
  seq: 0 | 1
  change_type: 'INSERT' | 'UPDATE' | 'DELETE'
  raw: Record<string, unknown> | null
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
// 사이클 129 — master TaskKey 4 확장 (universe/basics/daily/master).
// 백엔드 src/engine/refresh_progress.py L34 Literal + L37 tuple 2 위치 동행 영속.
export type RefreshTaskKey = 'universe' | 'basics' | 'daily' | 'master'
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
  master: RefreshProgress  // 사이클 129 — KIS 종목 마스터 파일 (16:30 KST) 적재 진행 영역
}
