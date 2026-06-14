/**
 * stock_master API 클라이언트 (사이클 85, 2026-06-09).
 *
 * 엔드포인트:
 *   GET  /api/stock-master/stats           — 전체 통계
 *   GET  /api/stock-master/list            — 종목 목록 (페이징)
 *   GET  /api/stock-master/scan-pool/summary — 스캔 풀 요약
 *   GET  /api/stock-master/{ticker}        — 단일 종목 상세
 *   GET  /api/stock-master/{ticker}/history — 변경 이력
 *
 * 응답 래퍼: ApiResponse<T> = { success, data, message }
 * 패턴 답습: price-filter.ts (사이클 64) / trade-amount-filter.ts (사이클 65)
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  StockMasterStats,
  StockMasterListItem,
  StockMasterListResponse,
  StockMasterDetail,
  StockMasterHistoryItem,
  ScanPoolSummary,
  RefreshUniverseResult,
  StockMasterDailyRow,
  BasicsRefreshResult,
  DailyRefreshResult,
  AllRefreshProgress,
  RefreshStartedResponse,
} from '../types/stock-master'

export async function fetchStats(): Promise<StockMasterStats> {
  const { data } = await apiClient.get<ApiResponse<StockMasterStats>>(
    '/stock-master/stats',
  )
  return data.data
}

/**
 * 사이클 128 — GET /api/stock-master/list 4 필터 + 페이징 + total 응답 schema 확장.
 *
 * 사용자 결정 Q2=A — 상단 인라인 4 컨트롤 (시장 select + 시총 min + 거래대금 min + 종목명 substr).
 * 응답 schema: list[dict] → {items, total, limit, offset} 객체 wrapping (T-1 빈 필터 = 전체 영속).
 *
 * 호환 layer (사이클 128 hotfix 안전 영속):
 * - 백엔드 fire-and-forget 미반영 영역 호환 (Array 직접 반환 시 items/total 추출).
 *
 * 단위 변환 의무 (T-2):
 * - minMarketCapEok / minTradeAmountEok 는 억원 단위 (프론트 UI 친숙)
 * - 백엔드 /list 라우트가 _eok_to_won 헬퍼로 원 단위 변환 후 list_paged_by_filter 호출
 */
export async function fetchList(
  params: {
    limit?: number
    offset?: number
    market?: 'KOSPI' | 'KOSDAQ' | null
    minMarketCapEok?: number
    minTradeAmountEok?: number
    nameSubstr?: string
  } = {},
): Promise<StockMasterListResponse> {
  const queryParams: Record<string, string | number> = {
    limit: params.limit ?? 100,
    offset: params.offset ?? 0,
  }
  if (params.market) queryParams.market = params.market
  if (params.minMarketCapEok && params.minMarketCapEok > 0) {
    queryParams.min_market_cap = params.minMarketCapEok
  }
  if (params.minTradeAmountEok && params.minTradeAmountEok > 0) {
    queryParams.min_trade_amount = params.minTradeAmountEok
  }
  if (params.nameSubstr && params.nameSubstr.trim()) {
    queryParams.name_substr = params.nameSubstr.trim()
  }

  const { data } = await apiClient.get<
    ApiResponse<StockMasterListResponse | StockMasterListItem[]>
  >('/stock-master/list', { params: queryParams })

  const payload = data.data
  // 사이클 128 신규 envelope 응답
  if (payload && !Array.isArray(payload) && 'items' in payload) {
    return payload as StockMasterListResponse
  }
  // 백엔드 미배포 환경 graceful fallback (사이클 124 hotfix 패턴 답습)
  const items = Array.isArray(payload) ? payload : []
  return {
    items,
    total: items.length,
    limit: queryParams.limit as number,
    offset: queryParams.offset as number,
  }
}

export async function fetchScanPoolSummary(): Promise<ScanPoolSummary> {
  const { data } = await apiClient.get<ApiResponse<ScanPoolSummary>>(
    '/stock-master/scan-pool/summary',
  )
  return data.data
}

export async function fetchDetail(ticker: string): Promise<StockMasterDetail> {
  const { data } = await apiClient.get<ApiResponse<StockMasterDetail>>(
    `/stock-master/${ticker}`,
  )
  return data.data
}

export async function fetchHistory(
  ticker: string,
  limit = 100,
): Promise<StockMasterHistoryItem[]> {
  const { data } = await apiClient.get<ApiResponse<StockMasterHistoryItem[]>>(
    `/stock-master/${ticker}/history`,
    { params: { limit } },
  )
  return data.data
}

/**
 * 사이클 124 Q1=A — GET /api/stock-master/{ticker}/daily?days=N
 * 일봉 데이터 최대 N일치 조회 (기본 30일).
 * retry:1 의무 (사이클 65 H3 영속).
 */
export async function fetchDaily(
  ticker: string,
  days = 30,
): Promise<StockMasterDailyRow[]> {
  const { data } = await apiClient.get<ApiResponse<StockMasterDailyRow[]>>(
    `/stock-master/${ticker}/daily`,
    { params: { days } },
  )
  return data.data
}

/**
 * 사이클 90 + 사이클 127 — POST /api/stock-master/refresh-universe (fire-and-forget).
 *
 * 사이클 127 — fire-and-forget 전환:
 * - 즉시 202 (status="started", task_key="universe") 응답 — axios timeout silent 결함 영구 차단
 * - 진행 상황은 fetchRefreshProgress() 5초 폴링으로 조회
 * - 409 Conflict 시 "이미 진행 중" 토스트
 *
 * 사이클 90 영속: 사이클 89 [stock_master_bulk_refresh] emit 영속 활용.
 * 사이클 75 G-RT 영속: useMutation retry: false 명시 의무.
 * 사이클 84 L-2 영속: POST 화이트리스트.
 */
export async function refreshUniverseNow(): Promise<RefreshStartedResponse | RefreshUniverseResult> {
  const { data } = await apiClient.post<ApiResponse<RefreshStartedResponse | RefreshUniverseResult>>(
    '/stock-master/refresh-universe',
  )
  return data.data
}

/**
 * 사이클 126 + 사이클 127 — POST /api/stock-master/basics/refresh (fire-and-forget).
 * KRX 1차 폴백 NXT/정지/관리종목 하드코딩 False 결함 시정.
 *
 * 사이클 127 — fire-and-forget 전환: 13분 39초 → 즉시 202 응답.
 * 진행 상황은 fetchRefreshProgress() 5초 폴링.
 */
export async function refreshBasicsNow(): Promise<RefreshStartedResponse | BasicsRefreshResult> {
  const { data } = await apiClient.post<ApiResponse<RefreshStartedResponse | BasicsRefreshResult>>(
    '/stock-master/basics/refresh',
  )
  return data.data
}

/**
 * 사이클 126 + 사이클 127 — POST /api/stock-master/daily/refresh (fire-and-forget).
 * 사이클 122 자동 task 와 동일 함수 호출. force=true 디폴트.
 *
 * 사이클 127 — fire-and-forget 전환: 즉시 202 응답.
 */
export async function refreshDailyNow(): Promise<RefreshStartedResponse | DailyRefreshResult> {
  const { data } = await apiClient.post<ApiResponse<RefreshStartedResponse | DailyRefreshResult>>(
    '/stock-master/daily/refresh',
  )
  return data.data
}

/**
 * 사이클 129 — POST /api/stock-master/master/refresh (fire-and-forget).
 *
 * KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 적재 수동 trigger.
 * 사이클 129 자동 task (`TIME_STOCK_MASTER_MASTER_LOAD=16:30 KST`) 와 동일 함수 호출.
 *
 * 사용자 결정 영구 영속:
 * - Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼
 * - Q12 시정: 시총 환산 × 100 (사용자 verbatim 정합)
 *
 * 사이클 127 fire-and-forget BackgroundTasks 패턴 100% 답습.
 * 사이클 84 L-2 영속: POST 4번째 화이트리스트 (master/refresh).
 */
export async function refreshMasterNow(): Promise<RefreshStartedResponse> {
  const { data } = await apiClient.post<ApiResponse<RefreshStartedResponse>>(
    '/stock-master/master/refresh',
  )
  return data.data
}

/**
 * 사이클 127 — GET /api/stock-master/refresh-progress (5초 폴링).
 *
 * 3 작업 (universe / basics / daily) 진행 state 통합 조회.
 * RefreshProgressBanner 컴포넌트가 useQuery refetchInterval: 5000 폴링.
 *
 * 사이클 65 H3 retry:1 영속 (useQuery 영역).
 */
export async function fetchRefreshProgress(): Promise<AllRefreshProgress> {
  const { data } = await apiClient.get<ApiResponse<AllRefreshProgress>>(
    '/stock-master/refresh-progress',
  )
  return data.data
}
