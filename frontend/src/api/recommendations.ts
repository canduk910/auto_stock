import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { RecommendationItem } from '../types/recommendations'

export const listRecommendations = async (): Promise<RecommendationItem[]> => {
  const { data } = await apiClient.get<ApiResponse<RecommendationItem[]>>('/recommendations')
  return data.data ?? []
}

export interface ApplyOptions {
  /**
   * Phase J4 (2026-05-12) — `recommended_weight` 적용 토글.
   * true 이면 백엔드가 strategy_config.weight 를 갱신.
   * recommended_weight 가 null 이면 백엔드 400 반환.
   */
  applyWeight?: boolean
}

export const applyRecommendation = async (
  id: string,
  keys: string[],
  options: ApplyOptions = {},
): Promise<{ success: boolean; message: string; appliedWeight?: number | null }> => {
  const body: Record<string, unknown> = { keys }
  if (options.applyWeight) {
    body.apply_weight = true
  }
  const { data } = await apiClient.post<ApiResponse<RecommendationItem | null>>(
    `/recommendations/${id}/apply`,
    body,
  )
  return {
    success: data.success,
    message: data.message,
    appliedWeight: data.data?.applied_weight ?? null,
  }
}

export const rejectRecommendation = async (
  id: string,
): Promise<{ success: boolean; message: string }> => {
  const { data } = await apiClient.post<ApiResponse<null>>(`/recommendations/${id}/reject`)
  return { success: data.success, message: data.message }
}
