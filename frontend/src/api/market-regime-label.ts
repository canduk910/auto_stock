/**
 * cycle410 — 6장세 라벨 API client(관찰 전용).
 *
 * 래퍼를 통째로 돌려준다 — 데이터 부족이면 서버가 `success=false` + 사유를 보내고
 * 카드가 그 사유를 그대로 보여야 하기 때문이다.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketRegimeLabelData } from '../types/market-regime-label'

export async function fetchMarketRegimeLabel(): Promise<ApiResponse<MarketRegimeLabelData | null>> {
  const resp = await apiClient.get<ApiResponse<MarketRegimeLabelData | null>>('/market-regime-label')
  return resp.data
}
