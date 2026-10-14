/**
 * cycle456 — 시장 유닛 결정 과정 차트 API client(읽기 전용).
 * 래퍼를 통째로 돌려준다 — `success=false` 면 카드가 서버 사유를 그대로 보인다.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketUnitChartData } from '../types/market-unit-chart'

export async function fetchMarketUnitChart(): Promise<ApiResponse<MarketUnitChartData | null>> {
  const resp = await apiClient.get<ApiResponse<MarketUnitChartData | null>>('/market-unit/chart')
  return resp.data
}
