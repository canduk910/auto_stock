/**
 * 사이클 7-D (2026-05-18): 보조 KIS 시세 계좌 API 클라이언트.
 *
 * 백엔드: ``src/routes/kis_quote_accounts.py`` (사이클 7-A).
 * - GET    /api/integrations/quote-accounts
 * - POST   /api/integrations/quote-accounts
 * - PUT    /api/integrations/quote-accounts/{id}
 * - DELETE /api/integrations/quote-accounts/{id}
 *
 * 안전 원칙:
 * - 응답에 app_secret 평문 없음 (백엔드 마스킹 보증). UI 는 마스킹만 표시
 * - 422/409 등 검증 에러는 axios interceptor 가 throw — 호출자가 catch
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  KisQuoteAccount,
  KisQuoteAccountCreateInput,
  KisQuoteAccountUpdateInput,
  KisQuoteAccountsListResponse,
} from '../types/kis-quote-accounts'

const BASE = '/integrations/quote-accounts'

export async function listAccounts(activeOnly = false): Promise<KisQuoteAccount[]> {
  const { data } = await apiClient.get<ApiResponse<KisQuoteAccountsListResponse>>(
    BASE,
    { params: { active_only: activeOnly } },
  )
  return data.data?.accounts ?? []
}

export async function createAccount(
  payload: KisQuoteAccountCreateInput,
): Promise<KisQuoteAccount> {
  const { data } = await apiClient.post<ApiResponse<KisQuoteAccount>>(BASE, payload)
  return data.data
}

export async function updateAccount(
  id: string,
  payload: KisQuoteAccountUpdateInput,
): Promise<KisQuoteAccount> {
  const { data } = await apiClient.put<ApiResponse<KisQuoteAccount>>(
    `${BASE}/${id}`,
    payload,
  )
  return data.data
}

export async function deleteAccount(id: string): Promise<void> {
  await apiClient.delete<ApiResponse<{ deleted: boolean; id: string }>>(`${BASE}/${id}`)
}
