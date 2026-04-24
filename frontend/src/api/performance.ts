import apiClient from './client'
import type {
  PerformanceSummary,
  DailyPerformance,
  MonthlyPerformance,
} from '../types/trading'
import type { ApiResponse } from '../types/common'

export const getPerformanceSummary = async (strategy?: string): Promise<PerformanceSummary> => {
  const { data } = await apiClient.get<ApiResponse<PerformanceSummary>>('/performance/summary', {
    params: strategy ? { strategy } : undefined,
  })
  return data.data
}

export const getDailyPerformance = async (days = 30, strategy?: string): Promise<DailyPerformance[]> => {
  const { data } = await apiClient.get<ApiResponse<DailyPerformance[]>>('/performance/daily', {
    params: { days, ...(strategy ? { strategy } : {}) },
  })
  return data.data
}

export const getMonthlyPerformance = async (strategy?: string): Promise<MonthlyPerformance[]> => {
  const { data } = await apiClient.get<ApiResponse<MonthlyPerformance[]>>('/performance/monthly', {
    params: strategy ? { strategy } : undefined,
  })
  return data.data
}
