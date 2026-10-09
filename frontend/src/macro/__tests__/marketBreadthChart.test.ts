/**
 * cycle416 Red — 시장 등락 차트 계산 순수 함수 `src/macro/marketBreadthChart.ts` (C1~C5).
 *
 * jsdom 은 recharts SVG 를 그리지 않으므로(폭 0) 차트에 들어가는 값은 이 순수 함수로 잰다.
 * 명세 §6.2(4) — x축 = 오래된 것 → 최신, 하락 막대는 음수, 축은 대칭 [-M, M], 상승 비율 선은 0~100%.
 *
 * 봉인하는 계약
 *  - `buildBreadthChartRows(days: BreadthDay[], market: BreadthMarketKey): BreadthChartRow[]`
 *    행 = `{ date, label, up, down, flat, no_trade, limit_up, limit_down, up_ratio_pct }`
 *    (`label` = `MM-DD` 문자열 자르기 · `down` 은 **음수** · `up_ratio_pct` = up_ratio×100, null 은 null)
 *  - `breadthAxisMax(rows): number` — M ≥ 창 안 max(up, |down|), 언제나 > 0 (빈 창도)
 *  - `mmdd('YYYY-MM-DD')` → `'MM-DD'` (new Date 금지 — 서버가 준 KST 날짜 문자열 그대로)
 *  - `formatUpRatio(r)` → `'32.5%'`(소수 1자리) · null → `'—'`
 *
 * RED: 모듈 부재 → import 실패.
 */
import { describe, expect, it } from 'vitest'

import { breadthAxisMax, buildBreadthChartRows, formatUpRatio, mmdd } from '../marketBreadthChart'
import { MARKET_BREADTH_FIXTURE } from '../../test/fixtures/marketBreadth.fixture'

describe('marketBreadthChart — 차트 행 계산 (cycle416)', () => {
  it('C1 x축은 오래된 날 → 최신 (응답 days[] 는 최신 먼저라 뒤집는다)', () => {
    const rows = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'total')
    expect(rows.map((r) => r.date)).toEqual(['2026-10-06', '2026-10-07', '2026-10-08'])
    expect(rows.map((r) => r.label)).toEqual(['10-06', '10-07', '10-08'])
    // 입력 배열을 제자리에서 뒤집지 않는다(표는 같은 배열을 최신 먼저로 쓴다)
    expect(MARKET_BREADTH_FIXTURE.days[0].date).toBe('2026-10-08')
  })

  it('C2 상승은 양수, 하락은 음수 막대 · 상·하한가 · 보합 · 거래 없음 · 상승 비율(%)', () => {
    const last = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'total').at(-1)!
    expect(last.up).toBe(870)
    expect(last.down).toBe(-1656)
    expect(last.limit_up).toBe(16)
    expect(last.limit_down).toBe(1)
    expect(last.flat).toBe(149)
    expect(last.no_trade).toBe(90)
    expect(last.up_ratio_pct).toBeCloseTo(32.52, 2)
  })

  it('C3 시장 선택을 따른다', () => {
    const kq = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'kosdaq').at(-1)!
    expect(kq.up).toBe(618)
    expect(kq.down).toBe(-1031)
    const kp = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'kospi').at(-1)!
    expect(kp.up).toBe(252)
    expect(kp.down).toBe(-625)
  })

  it('C4 대칭 축 — M 은 창 안 max(상승, 하락) 이상, 위아래 길이를 그대로 비교할 수 있다', () => {
    const rows = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'total')
    const m = breadthAxisMax(rows)
    expect(m).toBeGreaterThanOrEqual(1656)
    expect(m).toBeLessThan(1656 * 2) // 「보기 좋은 수로 올림」이지 두 배로 부풀리기가 아니다
    expect(breadthAxisMax([])).toBeGreaterThan(0)
    const flatOnly = buildBreadthChartRows(
      [{ ...MARKET_BREADTH_FIXTURE.days[0], total: { ...MARKET_BREADTH_FIXTURE.days[0].total, up: 0, down: 0 } }],
      'total',
    )
    expect(breadthAxisMax(flatOnly)).toBeGreaterThan(0)
  })

  it('C5 up_ratio null 은 선을 끊는다(null) · 표시 서식', () => {
    const d = structuredClone(MARKET_BREADTH_FIXTURE.days[0])
    d.total.up_ratio = null
    expect(buildBreadthChartRows([d], 'total')[0].up_ratio_pct).toBeNull()
    expect(formatUpRatio(0.3252)).toBe('32.5%')
    expect(formatUpRatio(0.5)).toBe('50.0%')
    expect(formatUpRatio(null)).toBe('—')
    expect(mmdd('2026-10-08')).toBe('10-08')
    expect(mmdd('2026-01-02')).toBe('01-02')
  })
})
