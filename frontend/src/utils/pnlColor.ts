// 손익(P/L) 색상 단일 진실원 (frontend/CLAUDE.md "시각적 컨벤션" 정본)
// 이익=빨강 / 손실=파랑 / 보합=회색. 종전 8곳 재구현을 이 모듈로 위임.
// ⚠️ text-red-600/text-blue-600 shade 계열(TradePnLGrid/BreakoutCandidateMonitor)은
//    별개 shade 라 여기 포함하지 않는다(픽셀 변경 방지).

export const PROFIT_HEX = '#FF3333' // 이익(양)
export const LOSS_HEX = '#3366FF' // 손실(음)
export const NEUTRAL_HEX = '#333333' // 보합

/** Tailwind 임의값 class 반환 (`text-[#FF3333]` 계열). */
export function pnlColorClass(value: number): string {
  if (value > 0) return 'text-[#FF3333]'
  if (value < 0) return 'text-[#3366FF]'
  return 'text-[#333333]'
}

/** style color 용 hex 문자열 반환. undefined/null/NaN → 보합(NEUTRAL). */
export function pnlColorHex(value: number | undefined | null): string {
  if (!value || !Number.isFinite(value)) return NEUTRAL_HEX
  if (value > 0) return PROFIT_HEX
  if (value < 0) return LOSS_HEX
  return NEUTRAL_HEX
}
