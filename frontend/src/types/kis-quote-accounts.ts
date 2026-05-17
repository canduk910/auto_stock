/**
 * 사이클 7-D (2026-05-18): 보조 KIS 시세 수신 계좌 타입.
 *
 * 백엔드 ``src/models/kis_quote_account.py`` 와 1:1.
 * **app_secret 평문 필드는 응답에 없음** — `from_row()` 가 항상 마스킹.
 */

export type KisEnv = 'real' | 'vts'

export interface KisQuoteAccount {
  id: string
  label: string
  app_key: string
  /** "****1234" 형식. 백엔드가 항상 마스킹 — 평문 절대 노출 안 함. */
  app_secret_masked: string
  kis_env: KisEnv
  active: boolean
  created_at: string
  updated_at?: string | null
}

export interface KisQuoteAccountCreateInput {
  label: string
  app_key: string
  /** 사용자 입력 평문 — 백엔드 전송 직후 폼 state 클리어. */
  app_secret: string
  kis_env: KisEnv
}

export interface KisQuoteAccountUpdateInput {
  active?: boolean
  label?: string
}

export interface KisQuoteAccountsListResponse {
  accounts: KisQuoteAccount[]
}
