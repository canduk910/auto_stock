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
 * IntegrationToggleCard 가 노출하는 토글 키.
 * 사이클 23 (2026-05-20): 'auto-apply' 추가 — AI 자문 자동 적용 토글.
 * 사이클 I (2026-08-03): 'etf-regime' 추가 — 지수ETF 레짐(관찰) 계산 토글.
 */
export type IntegrationKey =
  | 'dkstock-regime'
  | 'kis-mcp'
  | 'auto-regime-adjust'
  | 'auto-apply'
  | 'etf-regime'

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

/**
 * 사이클 D (2026-07-31): `data_available` — 실제 매크로 데이터 보유 여부.
 * `guard_inert` — mode!=='OFF' && !data_available (가드 설정됐으나 데이터 미유입으로 무력).
 * 백엔드 `BuyBlockStatusResponse` 와 1:1.
 */
export interface BuyBlockState {
  mode: BuyBlockMode
  thresholds: BuyBlockThresholds
  blocked: boolean
  reasons: string[]
  soft_multiplier: number
  data_available: boolean
  guard_inert: boolean
}

export interface BuyBlockUpdateRequest {
  mode?: BuyBlockMode
  vix_threshold?: number
  fg_high_threshold?: number
  fg_low_threshold?: number
  defensive_enabled?: boolean
}
