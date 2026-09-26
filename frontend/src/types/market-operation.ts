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

/**
 * cycle370 — 종목별 detail 행 배지 판정 상수.
 *
 * 백엔드 `src/api/market_operation.py` 와 같은 집합·값으로 유지한다(그쪽이 정본).
 * 화면은 값을 지어내지 않고 이 상수만 참조한다.
 */

/** `_INACTIVE_VALUES` 와 같은 집합 — VI/시간외VI 칸이 이 값이면 비활성이다. */
export const VI_INACTIVE_CODES: ReadonlySet<string> = new Set(['', '0', 'N', 'n', '(null)'])

/** VI 코드가 활성인가 — 블랙리스트 판정(백엔드 `_is_code_active` 와 동일 규약). */
export function isViCodeActive(code: string | null | undefined): boolean {
  if (code == null) return false
  return !VI_INACTIVE_CODES.has(code)
}

/** `ISCD_STAT_BLOCKING` 과 같은 값 — 종목상태 거래정지 판정은 이 코드 하나뿐이다. */
export const ISCD_STAT_HALT_CODE = '58'

/**
 * 종목상태 표시 집합(2026-09-25 사용자 결정, cycle368/370) — 51 관리종목 · 52 투자위험 ·
 * 53 투자경고 · 54 투자주의 · 59 단기과열. `58`(거래정지)은 거래정지 배지가 담당하므로
 * 여기 없다. 55(신용가능)·57(증거금100%)·00·'' 은 표시하지 않는다.
 */
export const ISCD_STAT_DISPLAY_LABELS: Readonly<Record<string, string>> = {
  '51': '관리종목',
  '52': '투자위험',
  '53': '투자경고',
  '54': '투자주의',
  '59': '단기과열',
}

/** KIS null 토큰 — 정지 사유 칸이 정확히 이 값이면 그리지 않는다(정확일치만, N4). */
export const HALT_REASON_NULL_TOKEN = '(null)'
