/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 타입.
 * 사이클 8 (2026-05-18) 확장: 매수 가드 4 모드 + 4 임계값.
 *
 * 백엔드 `src/models/system_integrations.py` 와 1:1.
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
 * IntegrationToggleCard 가 노출하는 4 토글 키.
 * 사이클 23 (2026-05-20): 'auto-apply' 추가 — AI 자문 자동 적용 토글.
 */
export type IntegrationKey = 'dkstock-regime' | 'kis-mcp' | 'auto-regime-adjust' | 'auto-apply'

/** 사이클 23 — AI 자문 자동 적용 토글 상태 */
export interface AutoApplyStatus {
  enabled: boolean
}

// ---------------------------------------------------------------------------
// 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값
// ---------------------------------------------------------------------------
export type BuyBlockMode = 'OFF' | 'WARN' | 'SOFT' | 'HARD'

export interface BuyBlockThresholds {
  vix_threshold: number
  fg_high_threshold: number
  fg_low_threshold: number
  defensive_enabled: boolean
}

export interface BuyBlockState {
  mode: BuyBlockMode
  thresholds: BuyBlockThresholds
  blocked: boolean
  reasons: string[]
  soft_multiplier: number
}

export interface BuyBlockUpdateRequest {
  mode?: BuyBlockMode
  vix_threshold?: number
  fg_high_threshold?: number
  fg_low_threshold?: number
  defensive_enabled?: boolean
}
