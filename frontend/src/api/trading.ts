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

// J3 (2026-05-12) — 매매 가용 자금 비율
// system_config.cash_usage_ratio. 범위 [0.5, 1.0], 5% 단위. 기본 1.0.
// 변경 즉시 적용 안 됨 — 다음 영업일 _boot() 부터 반영.
export const getCashUsageRatio = async (): Promise<number> => {
  const { data } = await apiClient.get<ApiResponse<{ ratio: number }>>(
    '/strategies/system/cash-usage-ratio',
  )
  return data.data?.ratio ?? 1.0
}

export const updateCashUsageRatio = async (ratio: number): Promise<number> => {
  const { data } = await apiClient.put<ApiResponse<{ ratio: number }>>(
    '/strategies/system/cash-usage-ratio',
    { ratio },
  )
  if (!data.success) {
    throw new Error(data.message || '가용 자금 비율 저장 실패')
  }
  // 백엔드가 5% 단위로 보정한 값을 반환 (예: 0.83 → 0.85)
  return data.data?.ratio ?? ratio
}
