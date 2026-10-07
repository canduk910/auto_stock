// cycle411 — 실비용 추정 API client. scheduler 무접촉 경로(새 leaf `cost_overlay.py`).
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { CostTodayData, CostDailyData } from '../types/costs'

export async function getCostsToday(strategy?: string): Promise<CostTodayData> {
  const { data } = await apiClient.get<ApiResponse<CostTodayData>>('/costs/today', {
    params: strategy ? { strategy } : undefined,
  })
  return data.data
}

export async function getCostsDaily(from: string, to: string): Promise<CostDailyData> {
  const { data } = await apiClient.get<ApiResponse<CostDailyData>>('/costs/daily', {
    params: { from, to },
  })
  return data.data
}
