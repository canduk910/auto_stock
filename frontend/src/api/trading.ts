import apiClient from './client'
import type { TradingStatusData, ActionResult, StrategiesResponse } from '../types/trading'
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

export const getStrategies = async (): Promise<StrategiesResponse> => {
  const { data } = await apiClient.get<ApiResponse<Record<string, unknown>>>('/strategies')
  const raw = data.data ?? {}
  // API는 { momentum: {...}, volatility_breakout: {...} } 객체를 반환
  // 프론트용 배열로 변환
  const strategies = Object.entries(raw).map(([key, val]) => {
    const v = val as { name: string; enabled: boolean; weight: number; params?: Record<string, unknown>; total_investment?: number; invested_amount?: number; min_weight?: number }
    return { key, name: v.name, enabled: v.enabled, weight: v.weight, params: v.params, total_investment: v.total_investment, invested_amount: v.invested_amount, min_weight: v.min_weight }
  })
  return { strategies }
}

// tradable_boards (string[]) / exchange (string) / k_value_* (number) / 기타 number 등 혼합 허용
export type StrategyParamValue = number | string | string[] | null
export const updateStrategyParams = async (
  strategyId: string,
  params: Record<string, StrategyParamValue>,
): Promise<ActionResult> => {
  const { data } = await apiClient.put<ApiResponse<null>>(
    `/strategies/${strategyId}/params`,
    { params },
  )
  return { success: data.success, message: data.message }
}

export const updateStrategyWeights = async (
  weights: Record<string, number>,
): Promise<ActionResult> => {
  const { data } = await apiClient.put<ApiResponse<null>>('/strategies/weights', { weights })
  if (!data.success) {
    throw new Error(data.message || '비중 변경 실패')
  }
  return { success: data.success, message: data.message }
}

export const manualSell = async (
  ticker: string,
  quantity: number,
): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/manual-sell', { ticker, quantity })
  return { success: data.success, message: data.message }
}
