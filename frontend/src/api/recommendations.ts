import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { RecommendationItem } from '../types/recommendations'

export const listRecommendations = async (): Promise<RecommendationItem[]> => {
  const { data } = await apiClient.get<ApiResponse<RecommendationItem[]>>('/recommendations')
  return data.data ?? []
}

export const applyRecommendation = async (
  id: string,
  keys: string[],
): Promise<{ success: boolean; message: string }> => {
  const { data } = await apiClient.post<ApiResponse<null>>(`/recommendations/${id}/apply`, { keys })
  return { success: data.success, message: data.message }
}

export const rejectRecommendation = async (
  id: string,
): Promise<{ success: boolean; message: string }> => {
  const { data } = await apiClient.post<ApiResponse<null>>(`/recommendations/${id}/reject`)
  return { success: data.success, message: data.message }
}
