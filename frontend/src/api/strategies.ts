/**
 * 사이클 F — TE(트레이딩 예지치)/RR(손익비) 전략별 성과 API client.
 *
 * 백엔드 `GET /api/strategies/te?months=3` 1:1 매핑. 관찰 전용.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { TeRrMetrics } from '../types/strategy'

export async function getStrategyTeRr(months = 3): Promise<TeRrMetrics[]> {
  const resp = await apiClient.get<ApiResponse<TeRrMetrics[]>>('/strategies/te', {
    params: { months },
  })
  return resp.data.data
}
