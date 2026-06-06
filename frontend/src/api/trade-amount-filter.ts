/**
 * 거래대금 필터 API 클라이언트 (사이클 65, 2026-06-06).
 *
 * 엔드포인트:
 *   GET  /api/system/trade-amount-filter — 현재 설정 조회
 *   PUT  /api/system/trade-amount-filter — 부분 갱신 (즉시 반영, 60s TTL 캐시 invalidate)
 *
 * 응답 래퍼: ApiResponse<TradeAmountFilter> = { success, data, message }
 * 패턴 답습: price-filter.ts (사이클 64)
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  TradeAmountFilter,
  TradeAmountFilterUpdate,
} from '../types/trade-amount-filter'

export async function getTradeAmountFilter(): Promise<TradeAmountFilter> {
  const { data } = await apiClient.get<ApiResponse<TradeAmountFilter>>(
    '/system/trade-amount-filter',
  )
  return data.data
}

export async function updateTradeAmountFilter(
  payload: TradeAmountFilterUpdate,
): Promise<TradeAmountFilter> {
  const { data } = await apiClient.put<ApiResponse<TradeAmountFilter>>(
    '/system/trade-amount-filter',
    payload,
  )
  return data.data
}
