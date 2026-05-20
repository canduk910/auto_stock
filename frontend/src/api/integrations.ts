/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 API 클라이언트.
 * 사이클 8 (2026-05-18) 확장: 매수 가드 4 모드 + 4 임계값.
 * 사이클 23 (2026-05-20) 확장: AI 자문 자동 적용 토글.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  AutoApplyStatus,
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

// ---------------------------------------------------------------------------
// 사이클 23 (2026-05-20) — AI 자문 자동 적용 토글
// ---------------------------------------------------------------------------
export async function getAutoApply(): Promise<AutoApplyStatus> {
  const { data } = await apiClient.get<ApiResponse<AutoApplyStatus>>(
    '/integrations/auto-apply',
  )
  return data.data
}

export async function setAutoApply(enabled: boolean): Promise<AutoApplyStatus> {
  const { data } = await apiClient.put<ApiResponse<AutoApplyStatus>>(
    '/integrations/auto-apply',
    { enabled },
  )
  return data.data
}
