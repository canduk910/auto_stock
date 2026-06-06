/**
 * 가격 필터 타입 정의 (사이클 64, 2026-06-06 — mode 필드 제거).
 *
 * 백엔드 PriceFilter Pydantic 모델 1:1 매핑.
 * 적용 위치: scanner 단계 WebSocket 구독 직전 (매도/손절/익일청산 무영향).
 *
 * 사이클 62 → 64 변경:
 * - PriceFilterMode 타입 폐기 (mode 필드 자체 제거)
 * - mode 필드 제거 (HARD/WARN/OFF 모드 폐기 — scanner 단순 필터링만)
 */

// export type PriceFilterMode = 'HARD' | 'WARN' | 'OFF'  // 사이클 64 폐기

export interface PriceFilter {
  min_price: number // 0 = 비활성
  max_price: number // 0 = 비활성 (무한대 의미)
  // mode 필드 제거 (사이클 64)
}

export interface PriceFilterUpdate {
  min_price?: number
  max_price?: number
  // mode 필드 제거 (사이클 64)
}
