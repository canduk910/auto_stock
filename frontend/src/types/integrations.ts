/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 타입.
 *
 * 백엔드 `src/models/system_integrations.py::IntegrationToggleStatus` 와 1:1.
 */

export type ToggleSource = 'db' | 'env'

export interface IntegrationToggleStatus {
  enabled: boolean
  source: ToggleSource
  env_value: boolean
  db_value: boolean | null
}

export interface IntegrationToggleRequest {
  enabled: boolean
}

/**
 * IntegrationToggleCard 가 노출하는 3 토글 키.
 */
export type IntegrationKey = 'dkstock-regime' | 'kis-mcp' | 'auto-regime-adjust'
