import apiClient from './client'
import type { TradingStatusData, ActionResult } from '../types/trading'
import type { ApiResponse } from '../types/common'

export const getTradingStatus = async (): Promise<TradingStatusData> => {
  const { data } = await apiClient.get<ApiResponse<TradingStatusData>>('/trading/status')
  return data.data
}

export const startTrading = async (): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/start')
  return { success: data.success, message: data.message }
}

export const stopTrading = async (): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/stop')
  return { success: data.success, message: data.message }
}

export const restartTrading = async (): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/restart')
  return { success: data.success, message: data.message }
}
