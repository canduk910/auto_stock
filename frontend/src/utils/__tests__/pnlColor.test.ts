import { describe, it, expect } from 'vitest'
import { PROFIT_HEX, LOSS_HEX, NEUTRAL_HEX, pnlColorClass, pnlColorHex } from '../pnlColor'

// refactor-review C1 (2026-08-09) — P/L 색상 단일 진실원 회귀 가드.
describe('pnlColor', () => {
  it('정본 hex 상수 (frontend/CLAUDE.md 컨벤션)', () => {
    expect(PROFIT_HEX).toBe('#FF3333')
    expect(LOSS_HEX).toBe('#3366FF')
    expect(NEUTRAL_HEX).toBe('#333333')
  })

  it('pnlColorClass 3분기 (이익/손실/보합)', () => {
    expect(pnlColorClass(1)).toBe('text-[#FF3333]')
    expect(pnlColorClass(-1)).toBe('text-[#3366FF]')
    expect(pnlColorClass(0)).toBe('text-[#333333]')
  })

  it('pnlColorHex 3분기 + null/undefined/NaN → 보합', () => {
    expect(pnlColorHex(1)).toBe('#FF3333')
    expect(pnlColorHex(-1)).toBe('#3366FF')
    expect(pnlColorHex(0)).toBe('#333333')
    expect(pnlColorHex(undefined)).toBe('#333333')
    expect(pnlColorHex(null)).toBe('#333333')
    expect(pnlColorHex(NaN)).toBe('#333333')
  })
})
