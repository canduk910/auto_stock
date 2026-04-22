import apiClient from './client'
import type { TradeHistoryData } from '../types/trading'
import type { ApiResponse } from '../types/common'

export interface HistoryParams {
  page?: number
  size?: number
  ticker?: string
}

export const getTradeHistory = async (
  params: HistoryParams = {},
): Promise<TradeHistoryData> => {
  const { data } = await apiClient.get<ApiResponse<TradeHistoryData>>('/history', { params })
  return data.data
}
