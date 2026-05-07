import apiClient from './client'
import type { TradeHistoryData, TradePnLData } from '../types/trading'
import type { ApiResponse } from '../types/common'

export interface HistoryParams {
  page?: number
  size?: number
  ticker?: string
  strategy?: string
}

export const getTradeHistory = async (
  params: HistoryParams = {},
): Promise<TradeHistoryData> => {
  const { data } = await apiClient.get<ApiResponse<TradeHistoryData>>('/history', { params })
  return data.data
}

export const getTradePnL = async (
  params: HistoryParams = {},
): Promise<TradePnLData> => {
  const { data } = await apiClient.get<ApiResponse<TradePnLData>>('/history/pnl', { params })
  return data.data
}
