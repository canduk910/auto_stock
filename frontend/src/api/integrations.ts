/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 API 클라이언트.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  IntegrationKey,
  IntegrationToggleStatus,
} from '../types/integrations'

async function getToggle(key: IntegrationKey): Promise<IntegrationToggleStatus> {
  const { data } = await apiClient.get<ApiResponse<IntegrationToggleStatus>>(
    `/integrations/${key}`,
  )
  return data.data
}

async function setToggle(
  key: IntegrationKey,
  enabled: boolean,
): Promise<IntegrationToggleStatus> {
  const { data } = await apiClient.put<ApiResponse<IntegrationToggleStatus>>(
    `/integrations/${key}`,
    { enabled },
  )
  return data.data
}

export const getDkstockRegime = () => getToggle('dkstock-regime')
export const setDkstockRegime = (enabled: boolean) =>
  setToggle('dkstock-regime', enabled)

export const getKisMcp = () => getToggle('kis-mcp')
export const setKisMcp = (enabled: boolean) => setToggle('kis-mcp', enabled)

export const getAutoRegimeAdjust = () => getToggle('auto-regime-adjust')
export const setAutoRegimeAdjustToggle = (enabled: boolean) =>
  setToggle('auto-regime-adjust', enabled)
