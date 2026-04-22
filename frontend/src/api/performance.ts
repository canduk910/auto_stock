import apiClient from './client'
import type {
  PerformanceSummary,
  DailyPerformance,
  MonthlyPerformance,
} from '../types/trading'
import type { ApiResponse } from '../types/common'

export const getPerformanceSummary = async (): Promise<PerformanceSummary> => {
  const { data } = await apiClient.get<ApiResponse<PerformanceSummary>>('/performance/summary')
  return data.data
}

export const getDailyPerformance = async (days = 30): Promise<DailyPerformance[]> => {
  const { data } = await apiClient.get<ApiResponse<DailyPerformance[]>>('/performance/daily', {
    params: { days },
  })
  return data.data
}

export const getMonthlyPerformance = async (): Promise<MonthlyPerformance[]> => {
  const { data } = await apiClient.get<ApiResponse<MonthlyPerformance[]>>('/performance/monthly')
  return data.data
}
