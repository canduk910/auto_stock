/**
 * RS·재무 관찰 화면 API(읽기 전용). 래퍼를 통째로 돌려준다 — `success=false` 면 화면이 서버 사유를 그대로 보인다.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { RsObserveData } from '../types/rs-observe'

export async function getRsObserve(date?: string | null): Promise<ApiResponse<RsObserveData | null>> {
  const params = date ? { date } : undefined
  const resp = await apiClient.get<ApiResponse<RsObserveData | null>>('/rs-observe', { params })
  return resp.data
}
