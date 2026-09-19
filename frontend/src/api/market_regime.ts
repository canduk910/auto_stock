/**
 * 사이클 2 (2026-05-17): 시장 레짐 API.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketRegimeCurrent, MarketRegimeSnapshotItem } from '../types/market_regime'

export const getMarketRegimeCurrent = async (): Promise<MarketRegimeCurrent> => {
  const { data } = await apiClient.get<ApiResponse<MarketRegimeCurrent>>('/market-regime/current')
  return data.data
}

/**
 * ⚠️ **dead — 호출자 0건이다** (cycle315 전수 확인: `frontend/src`·`e2e` 어디에서도
 * 부르지 않는다). 백엔드 `GET /api/market-regime/history` 와 `market_regime_snapshots`
 * 테이블은 살아 있으므로 함수는 남겨 두되, 이번 사이클에 화면을 붙이지는 않았다.
 * 되살릴 때는 이 주석을 지우고 소비 화면과 목을 같이 만든다.
 */
export const getMarketRegimeHistory = async (days = 30): Promise<MarketRegimeSnapshotItem[]> => {
  const { data } = await apiClient.get<ApiResponse<MarketRegimeSnapshotItem[]>>(
    `/market-regime/history?days=${days}`,
  )
  return data.data ?? []
}

export const setAutoRegimeAdjust = async (
  enabled: boolean,
): Promise<{ success: boolean; message: string; auto_regime_adjust: boolean }> => {
  const { data } = await apiClient.put<ApiResponse<{ auto_regime_adjust: boolean }>>(
    '/market-regime/auto-adjust',
    { enabled },
  )
  return {
    success: data.success,
    message: data.message,
    auto_regime_adjust: data.data?.auto_regime_adjust ?? enabled,
  }
}
