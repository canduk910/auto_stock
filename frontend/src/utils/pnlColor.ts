// 손익(P/L) 색상 단일 진실원 (frontend/CLAUDE.md "시각적 컨벤션" 정본)
// 이익=빨강 / 손실=파랑 / 보합=회색. 종전 8곳 재구현을 이 모듈로 위임.
// DK Stock 디자인시스템 v2 (가을 팔레트): red-500 / blue-500 / gray-700
// ⚠️ text-red-600/text-blue-600 shade 계열(TradePnLGrid/BreakoutCandidateMonitor)은
//    별개 shade 라 여기 포함하지 않는다(픽셀 변경 방지).

export const PROFIT_HEX = '#c34a36' // 이익(양) — red-500
export const LOSS_HEX = '#3d73b7' // 손실(음) — blue-500
export const NEUTRAL_HEX = '#41403b' // 보합 — gray-700

/** Tailwind class 반환 (@theme 에 pnl-* 시맨틱 컬러 정의됨). */
export function pnlColorClass(value: number): string {
  if (value > 0) return 'text-pnl-profit'
  if (value < 0) return 'text-pnl-loss'
  return 'text-pnl-flat'
}

/** style color 용 hex 문자열 반환. undefined/null/NaN → 보합(NEUTRAL). */
export function pnlColorHex(value: number | undefined | null): string {
  if (!value || !Number.isFinite(value)) return NEUTRAL_HEX
  if (value > 0) return PROFIT_HEX
  if (value < 0) return LOSS_HEX
  return NEUTRAL_HEX
}
