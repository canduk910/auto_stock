/**
 * 사이클 186 (2026-06-29) — 장운영상태 타입 정의.
 *
 * GET /api/realtime/market-operation 응답 schema.
 * VI/거래정지/종목상태 이상 + 서킷브레이커 휴리스틱 계측.
 */

export interface CircuitBreakerState {
  suspected: boolean
  reasons: string[]
  halt_ratio: number
  halted: number
  observed: number
  representative_mkop_cls_code: string
  halt_reasons_sample: string[]
}

export interface MarketOpDetail {
  ticker: string
  vi_code: string
  ovtm_vi_code: string
  halt_yn: string
  halt_reason: string
  iscd_stat: string
  mkop_cls_code: string
  exch_code: string
  received_at: string | null
}

export interface MarketOperationStatus {
  vi_active_count: number
  halt_active_count: number
  last_event_count: number
  iscd_stat_active_count: number
  vi_active_sample: string[]
  halt_active_sample: string[]
  circuit_breaker: CircuitBreakerState
  details: MarketOpDetail[]
}
