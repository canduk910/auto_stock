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
