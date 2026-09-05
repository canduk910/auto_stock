import { describe, it, expect } from 'vitest'
import { PROFIT_HEX, LOSS_HEX, NEUTRAL_HEX, pnlColorClass, pnlColorHex } from '../pnlColor'

// refactor-review C1 (2026-08-09) — P/L 색상 단일 진실원 회귀 가드.
// cycle261 (2026-09-05) — DK Stock 디자인시스템 v2(가을 팔레트) 계약으로 기대값 전환.
//   hex 3종은 index.css `@theme` 의 `--color-pnl-{profit,loss,flat}` 과 동일 값이어야 하고
//   (그 정합은 `src/__tests__/designSystem.v2.test.ts` (a) 가 별도로 봉인한다),
//   `pnlColorClass` 는 임의값 `text-[#…]` 대신 시맨틱 클래스를 반환한다.
describe('pnlColor', () => {
  it('정본 hex 상수 (DK Stock v2 가을 팔레트 — red-500 / blue-500 / gray-700)', () => {
    expect(PROFIT_HEX).toBe('#c34a36')
    expect(LOSS_HEX).toBe('#3d73b7')
    expect(NEUTRAL_HEX).toBe('#41403b')
  })

  it('pnlColorClass 3분기 (이익/손실/보합) — 시맨틱 클래스 text-pnl-*', () => {
    expect(pnlColorClass(1)).toBe('text-pnl-profit')
    expect(pnlColorClass(-1)).toBe('text-pnl-loss')
    expect(pnlColorClass(0)).toBe('text-pnl-flat')
  })

  it('pnlColorHex 3분기 + null/undefined/NaN → 보합', () => {
    expect(pnlColorHex(1)).toBe(PROFIT_HEX)
    expect(pnlColorHex(-1)).toBe(LOSS_HEX)
    expect(pnlColorHex(0)).toBe(NEUTRAL_HEX)
    expect(pnlColorHex(undefined)).toBe(NEUTRAL_HEX)
    expect(pnlColorHex(null)).toBe(NEUTRAL_HEX)
    expect(pnlColorHex(NaN)).toBe(NEUTRAL_HEX)
  })
})
