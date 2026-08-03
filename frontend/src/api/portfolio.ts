/**
 * 사이클 I (2026-08-03): 포트폴리오 리스크 관찰 API.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { PortfolioRisk } from '../types/portfolio'

export const getPortfolioRisk = async (): Promise<PortfolioRisk> => {
  const { data } = await apiClient.get<ApiResponse<PortfolioRisk>>('/portfolio/risk')
  return data.data
}
