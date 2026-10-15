/**
 * RS·재무 관찰 — 칸 값 → 표시 문자열(`utils/rsObserve.ts`).
 * 🔴 「모름」 = `—` (0 으로 채우지 않는다). 0 은 0 으로 보인다.
 */
import { describe, expect, it } from 'vitest'
import { fmtBool, fmtInt, fmtPercent, fmtQuarter, fmtRatioPct, fmtSector, sortRows, toNum } from '../rsObserve'

describe('rsObserve 표시', () => {
  it('O1 — 모름(null·undefined·NaN·빈 문자열·글자)은 전부 —', () => {
    for (const v of [null, undefined, Number.NaN, Infinity, '', '  ', 'abc', {}]) {
      expect(fmtRatioPct(v)).toBe('—')
      expect(fmtPercent(v)).toBe('—')
      expect(fmtInt(v)).toBe('—')
    }
    expect(fmtBool(null)).toBe('—')
    expect(fmtBool(undefined)).toBe('—')
    expect(fmtQuarter(null)).toBe('—')
  })

  it('O2 — 0 은 0 이다(모름과 다르다)', () => {
    expect(fmtRatioPct(0)).toBe('0.0%')
    expect(fmtInt(0)).toBe('0')
    expect(fmtPercent(0)).toBe('0.0%')
    expect(fmtBool(false)).toBe('아니오')
  })

  it('O3 — 비율은 ×100 + 부호, 백분율은 그대로', () => {
    expect(fmtRatioPct(0.1234)).toBe('+12.3%')
    expect(fmtRatioPct(-0.051)).toBe('-5.1%')
    expect(fmtRatioPct('0.5', 0)).toBe('+50%') // 숫자 문자열도 읽는다
    expect(fmtPercent(26.4)).toBe('26.4%')
    expect(fmtInt(87.6)).toBe('88')
    expect(toNum('12')).toBe(12)
  })

  it('O4 — 결산월 YYYYMM → 연·월', () => {
    expect(fmtQuarter('202606')).toBe('2026년 6월')
    expect(fmtQuarter('2026Q2')).toBe('2026Q2')
  })

  it('O5 — 정렬: 보유 먼저 → RS 백분위 높은 순(모름은 뒤) → 종목코드, 입력은 그대로', () => {
    const rows = [
      { ticker: 'C', role: 'candidate', rs_pct: null },
      { ticker: 'B', role: 'candidate', rs_pct: 50 },
      { ticker: 'A', role: 'candidate', rs_pct: 90 },
      { ticker: 'H', role: 'held', rs_pct: 10 },
      { ticker: 'D', role: 'candidate', rs_pct: 50 },
    ]
    const before = rows.map((r) => r.ticker)
    expect(sortRows(rows).map((r) => r.ticker)).toEqual(['H', 'A', 'B', 'D', 'C'])
    expect(rows.map((r) => r.ticker)).toEqual(before)
  })
})

describe('fmtSector — 섹터 칸 (2026-10-15 사용자 지적: 코드·종목코드가 그대로 보였다)', () => {
  it('S1 — 업종명은 그대로, 「미분류-종목코드」 는 「미분류」, 모름은 —', () => {
    expect(fmtSector('전기·전자')).toBe('전기·전자')
    expect(fmtSector('미분류-052460')).toBe('미분류')
    for (const v of [null, undefined, '', '  ', 3]) expect(fmtSector(v)).toBe('—')
  })
  it('S2 — 10-16 전 기록의 업종 코드는 「옛 기준」 으로 표시한다(이름을 지어내지 않는다)', () => {
    expect(fmtSector('업종-0027')).toBe('대분류 0027 (옛 기준)')
    expect(fmtSector('중분류-1027')).toBe('중분류 1027 (옛 기준)')
  })
})
