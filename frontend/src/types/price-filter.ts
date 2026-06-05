/**
 * 가격 필터 타입 정의 (사이클 62, 2026-06-05).
 *
 * 백엔드 PriceFilter Pydantic 모델 1:1 매핑.
 * 적용 위치: risk.on_tick 매수 진입 전용 (매도/손절/익일청산 무영향).
 */

export type PriceFilterMode = 'HARD' | 'WARN' | 'OFF'

export interface PriceFilter {
  min_price: number // 0 = 비활성
  max_price: number // 0 = 비활성 (무한대 의미)
  mode: PriceFilterMode
}

export interface PriceFilterUpdate {
  min_price?: number
  max_price?: number
  mode?: PriceFilterMode
}
