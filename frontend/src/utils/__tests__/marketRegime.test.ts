/**
 * cycle315 후속(적대 검토) — `utils/marketRegime.ts` 순수 함수 직접 가드.
 *
 * 왜 따로 파는가: 카드 렌더 테스트(`MarketRegimeCard.test.tsx` · `marketRegimeMocks.cycle315`)
 * 는 **정상 픽스처 하나**만 통과시키므로 포매터의 안전장치가 통째로 사라져도 침묵한다.
 * 실제로 뮤테이션 2건이 전 스위트 초록을 뚫었다 —
 *   (a) `BUFFETT_RATIO_MAX` 상한 분기 삭제
 *   (b) 결측 폴백 `'—'` → `'BROKEN'`
 * 하필 (a) 는 이 파일이 「값 크기로 단위를 추측해 조용히 나누지 않는다」를 지키려고 둔
 * 장치다 — 그 장치가 소리 없이 없어지면 단위가 어긋난 값이 그럴듯한 퍼센트로 위장된다.
 */
import { describe, expect, it } from 'vitest'

// ⚠️ 단일 행 import 로 유지한다 — `tools/test_impact/build_index_frontend.mjs` 의 import
// 정규식(`IMPORT_RE`)이 `.` (개행 미매칭)이라 여러 줄에 걸친 `import {...} from '...'` 는
// 소스↔테스트 그래프에서 통째로 누락된다(cycle315 후속 실측: 애초 여러 줄로 썼더니
// 인덱스 재생성 후 `frontend/src/utils/marketRegime.ts` 의 `direct_tests` 에 이 파일이
// 안 잡혔다). `components/MarketRegimeCard.test.tsx` 가 같은 유틸을 단일 행으로 import
// 해서 정상 반영되는 것과 대조된다.
import { BUFFETT_RATIO_MAX, CYCLE_LABEL, REGIME_CASH_LADDER, REGIME_STYLE, formatBuffettRatio, usagePctFromCashMin } from '../marketRegime'

describe('utils/marketRegime — 버핏지수 포매터', () => {
  it('U1: 비율 계약 — 2.626 → 263% (반올림)', () => {
    expect(formatBuffettRatio(2.626)).toBe('263%')
  })

  it('U2: 결측·비유한값은 전부 대시 한 글자다', () => {
    expect(formatBuffettRatio(null)).toBe('—')
    expect(formatBuffettRatio(undefined)).toBe('—')
    expect(formatBuffettRatio(Number.NaN)).toBe('—')
    expect(formatBuffettRatio(Number.POSITIVE_INFINITY)).toBe('—')
  })

  it('U3: 상한 초과 값은 경고를 달고 원값 그대로 — 조용한 ÷100 부활 금지', () => {
    const out = formatBuffettRatio(12.5)
    expect(out).toContain('⚠')
    // 퍼센트 기호가 붙는 순간 "단위를 추측해 변환했다" 는 뜻이다
    expect(out).not.toContain('%')
    expect(out).toContain('12.5')
  })

  it('U4: 상한 경계 — 상한 자체는 정상 변환, 초과부터 경고', () => {
    expect(formatBuffettRatio(BUFFETT_RATIO_MAX)).toBe('1000%')
    expect(formatBuffettRatio(BUFFETT_RATIO_MAX + 0.1)).toContain('⚠')
  })

  it('U5: 상한 상수는 10 이다 (시총이 GDP 의 10배가 되는 세계는 없다)', () => {
    expect(BUFFETT_RATIO_MAX).toBe(10)
  })
})

describe('utils/marketRegime — 자금 사용률', () => {
  it('U6: 사다리 4단 — cash_min 25/35/50/75 → 사용률 75/65/50/25', () => {
    expect(usagePctFromCashMin(25)).toBe(75)
    expect(usagePctFromCashMin(35)).toBe(65)
    expect(usagePctFromCashMin(50)).toBe(50)
    expect(usagePctFromCashMin(75)).toBe(25)
  })

  it('U7: 경계 클램프 — 음수는 100, 100 초과는 0 으로 접힌다', () => {
    expect(usagePctFromCashMin(-5)).toBe(100)
    expect(usagePctFromCashMin(120)).toBe(0)
    expect(usagePctFromCashMin(0)).toBe(100)
    expect(usagePctFromCashMin(100)).toBe(0)
  })

  it('U8: 사다리 상수와 포매터가 같은 식을 쓴다 (표와 모달의 숫자가 갈라지지 않는다)', () => {
    expect(REGIME_CASH_LADDER.map((r) => r.regime)).toEqual([
      'accumulation',
      'selective',
      'cautious',
      'defensive',
    ])
    for (const { regime, cashMin } of REGIME_CASH_LADDER) {
      expect(REGIME_STYLE).toHaveProperty(regime)
      expect(usagePctFromCashMin(cashMin)).toBe(100 - cashMin)
    }
  })

  it('U9: 4국면 라벨 키가 macro_lite `cycle.py` 와 같다', () => {
    expect(Object.keys(CYCLE_LABEL).sort()).toEqual([
      'contraction',
      'expansion',
      'overheating',
      'recovery',
    ])
  })
})
