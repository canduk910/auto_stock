/**
 * 거래대금 필터 타입 정의 (사이클 65, 2026-06-06).
 *
 * 백엔드 TradeAmountFilter Pydantic 모델 1:1 매핑.
 * 적용 위치: scanner 단계 WebSocket 구독 직전 (매도/손절/익일청산 무영향).
 *
 * Q1 자문 확정:
 * - 디폴트 0 (비활성)
 * - 0~100억 step 1억
 * - 권장값 마커: 1억 / 5억 / 10억
 */

export interface TradeAmountFilter {
  min_amount: number // 원 단위, 0 = 비활성
}

export interface TradeAmountFilterUpdate {
  min_amount?: number
}
