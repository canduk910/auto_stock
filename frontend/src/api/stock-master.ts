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

export async function fetchList(
  limit = 100,
  offset = 0,
): Promise<StockMasterListItem[]> {
  const { data } = await apiClient.get<ApiResponse<StockMasterListItem[]>>(
    '/stock-master/list',
    { params: { limit, offset } },
  )
  return data.data
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
