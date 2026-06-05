/**
 * 가격 필터 API 클라이언트 (사이클 62, 2026-06-05).
 *
 * 엔드포인트:
 *   GET  /api/system/price-filter — 현재 설정 조회
 *   PUT  /api/system/price-filter — 부분 갱신 (즉시 반영, 60s TTL 캐시 invalidate)
 *
 * 응답 래퍼: ApiResponse<PriceFilter> = { success, data, message }
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { PriceFilter, PriceFilterUpdate } from '../types/price-filter'

export async function getPriceFilter(): Promise<PriceFilter> {
  const { data } = await apiClient.get<ApiResponse<PriceFilter>>(
    '/system/price-filter',
  )
  return data.data
}

export async function updatePriceFilter(
  payload: PriceFilterUpdate,
): Promise<PriceFilter> {
  const { data } = await apiClient.put<ApiResponse<PriceFilter>>(
    '/system/price-filter',
    payload,
  )
  return data.data
}
