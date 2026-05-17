/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 API 클라이언트.
 * 사이클 8 (2026-05-18) 확장: 매수 가드 4 모드 + 4 임계값.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  BuyBlockState,
  BuyBlockUpdateRequest,
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

// ---------------------------------------------------------------------------
// 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값
// ---------------------------------------------------------------------------
export async function getBuyBlock(): Promise<BuyBlockState> {
  const { data } = await apiClient.get<ApiResponse<BuyBlockState>>(
    '/integrations/buy-block',
  )
  return data.data
}

export async function setBuyBlock(
  payload: BuyBlockUpdateRequest,
): Promise<BuyBlockState> {
  const { data } = await apiClient.put<ApiResponse<BuyBlockState>>(
    '/integrations/buy-block',
    payload,
  )
  return data.data
}
