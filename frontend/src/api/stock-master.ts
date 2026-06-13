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
 * 사이클 90 — POST /api/stock-master/refresh-universe (Q24=B 수동 trigger).
 *
 * Q25=A: asyncio.Lock + 409 Conflict 동시 호출 가드 (백엔드 영역).
 * Q26=A: stats 카드 상단 우측 "지금 새로고침" 버튼.
 * Q27=A: 사이클 89 [stock_master_bulk_refresh] emit 영속 활용.
 * 사이클 75 G-RT 영속: useMutation retry:1 명시 의무 (StockMaster.tsx 영역).
 * 사이클 84 L-2 영속: POST 1개 예외 허용 (백엔드 AST 가드 갱신 영역).
 */
export async function refreshUniverseNow(): Promise<RefreshUniverseResult> {
  const { data } = await apiClient.post<ApiResponse<RefreshUniverseResult>>(
    '/stock-master/refresh-universe',
  )
  return data.data
}

/**
 * 사이클 126 — POST /api/stock-master/basics/refresh (KIS CTPF1002R 매스 보강).
 * KRX 1차 폴백 NXT/정지/관리종목 하드코딩 False 결함 시정.
 * useMutation retry: false 의무 (장시간 작업, KIS 호출 중복 방지).
 */
export async function refreshBasicsNow(): Promise<BasicsRefreshResult> {
  const { data } = await apiClient.post<ApiResponse<BasicsRefreshResult>>(
    '/stock-master/basics/refresh',
  )
  return data.data
}

/**
 * 사이클 126 — POST /api/stock-master/daily/refresh (일봉 적재 수동 trigger).
 * 사이클 122 자동 task 와 동일 함수 호출. force=true 디폴트.
 * useMutation retry: false 의무 (장시간 작업, KIS 호출 중복 방지).
 */
export async function refreshDailyNow(): Promise<DailyRefreshResult> {
  const { data } = await apiClient.post<ApiResponse<DailyRefreshResult>>(
    '/stock-master/daily/refresh',
  )
  return data.data
}
