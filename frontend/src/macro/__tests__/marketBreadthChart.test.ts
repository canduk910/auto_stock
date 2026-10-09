/**
 * cycle416 Red — 시장 등락 차트 계산 순수 함수 `src/macro/marketBreadthChart.ts` (C1~C5).
 * cycle418-B — 남은 결함 #2(C6~C8) — 호출 실패로 빠진 날이 x축에서 칸 없이 붙던 문제 시정.
 *
 * jsdom 은 recharts SVG 를 그리지 않으므로(폭 0) 차트에 들어가는 값은 이 순수 함수로 잰다.
 * 명세 §6.2(4) — x축 = 오래된 것 → 최신, 하락 막대는 음수, 축은 대칭 [-M, M], 상승 비율 선은 0~100%.
 *
 * 봉인하는 계약
 *  - `buildBreadthChartRows(days: BreadthDay[], market: BreadthMarketKey, missingDates?: string[]): BreadthChartRow[]`
 *    행 = `{ date, label, up, down, flat, no_trade, limit_up, limit_down, up_ratio_pct, missing }`
 *    (`label` = `MM-DD` 문자열 자르기 · `down` 은 **음수** · `up_ratio_pct` = up_ratio×100, null 은 null)
 *    `missingDates`(= 응답 `missing_dates`, 기본 `[]`) 는 그 자리에 0/null `missing=true` 칸을 끼워
 *    넣는다 — 영업일 달력을 새로 계산하지 않고 응답이 준 두 배열(`days`+`missing_dates`)만 날짜
 *    문자열로 정렬해 합친다(출처는 응답 하나).
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

  it('C6 missing_dates(남은 결함 #2) — 응답이 알려준 빠진 날짜를 x축 자리에 끼워 0/null 로 비우고 missing=true 로 표시한다', () => {
    const rows = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'total', ['2026-10-05'])
    // 날짜 순서는 영업일 달력을 다시 계산하지 않고 응답 두 배열(days + missing_dates)만 합쳐 정렬한다
    expect(rows.map((r) => r.date)).toEqual(['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'])
    expect(rows.map((r) => r.label)).toEqual(['10-05', '10-06', '10-07', '10-08'])

    const gap = rows.find((r) => r.date === '2026-10-05')!
    expect(gap.missing).toBe(true)
    expect(gap.up).toBe(0)
    expect(gap.down).toBe(0)
    expect(gap.flat).toBe(0)
    expect(gap.no_trade).toBe(0)
    expect(gap.limit_up).toBe(0)
    expect(gap.limit_down).toBe(0)
    expect(gap.up_ratio_pct).toBeNull()

    for (const r of rows) {
      if (r.date !== '2026-10-05') expect(r.missing).toBe(false)
    }
  })

  it('C7 missing_dates 기본값 — 생략하면(기존 호출부) 결과가 그대로다(하위호환)', () => {
    const rows = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'total')
    expect(rows.map((r) => r.date)).toEqual(['2026-10-06', '2026-10-07', '2026-10-08'])
    expect(rows.every((r) => r.missing === false)).toBe(true)
  })

  it('C8 missing_dates 가 응답 days[] 와 겹치면(이론상 있을 수 없는 입력) 중복 칸을 만들지 않는다', () => {
    const rows = buildBreadthChartRows(MARKET_BREADTH_FIXTURE.days, 'total', ['2026-10-08'])
    expect(rows.map((r) => r.date)).toEqual(['2026-10-06', '2026-10-07', '2026-10-08'])
    expect(rows.find((r) => r.date === '2026-10-08')!.missing).toBe(false)
  })
})
