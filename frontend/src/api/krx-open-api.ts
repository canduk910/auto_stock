/**
 * 사이클 112 (2026-06-12): KRX 정식 OPEN API 키 관리 API.
 *
 * 백엔드 `src/routes/system_integrations.py::get_krx_open_api / set_krx_open_api` 호출.
 * `ApiResponse<KrxOpenApiStatus>` 래퍼 → 프론트 `data.data` 추출 (사이클 64 답습).
 *
 * 보안: 평문 key 는 PUT body 에만 사용. 응답은 항상 `key_masked` 만 포함.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  KrxOpenApiStatus,
  KrxOpenApiUpdateRequest,
} from '../types/krx-open-api'

// apiClient baseURL = '/api' — BASE 에서 /api prefix 제거 (kis-quote-accounts 패턴 답습)
const BASE = '/integrations/krx-open-api'

export async function getKrxOpenApi(): Promise<KrxOpenApiStatus> {
  const response = await apiClient.get<ApiResponse<KrxOpenApiStatus>>(BASE)
  return response.data.data
}

export async function updateKrxOpenApi(
  body: KrxOpenApiUpdateRequest
): Promise<KrxOpenApiStatus> {
  const response = await apiClient.put<ApiResponse<KrxOpenApiStatus>>(BASE, body)
  return response.data.data
}
