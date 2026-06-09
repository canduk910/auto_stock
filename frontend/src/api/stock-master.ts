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
