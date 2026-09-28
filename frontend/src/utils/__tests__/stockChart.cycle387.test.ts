/**
 * cycle387 Red — 종목 차트 순수 함수 (`utils/stockChart.ts`) U1~U4.
 *
 * 명세: `_workspace/red/cycle387_stock_chart_spec.md` §2.1 · §2.2 · §2.4 · §3.2(U1~U4)
 *
 * 봉인하는 계약(이름·형태가 다르면 FAIL):
 *  - `isChartableTicker(v: unknown): boolean` — KRX 6자리 **숫자**만 참(백엔드 422 규칙과 같다)
 *  - `isInteractiveTarget(t: EventTarget | null): boolean` — button·a·input·select·textarea·label
 *    **또는 그 자손**이면 참. 행 더블클릭이 「매도」·「AI 자문」 두 번 누름을 차트로 오인하지 않게 한다
 *  - `toKLineData(bars)` — `{timestamp, open, high, low, close, volume, turnover}` 배열.
 *    timestamp = **KST 자정 epoch ms**(`kstDateToEpochMs`), turnover = amount, 숫자 방어 변환,
 *    날짜·OHLC 변환 실패 봉 제거, 오름차순 보장
 *  - `PERIOD_TO_KLINE` = `{D:'day', W:'week', M:'month'}` · `PERIOD_LABEL` = `{D:'일봉', W:'주봉', M:'월봉'}`
 *
 * TZ 고정 — `utils/stockChart.ts` 가 `utils/kst.ts`(모듈 레벨 `Intl` 포맷터)를 import 하므로
 * `beforeAll` 에서 TZ 를 UTC 로 고정한 **뒤** 동적 import 한다(가드 설계 금기 — cycle256 F2).
 *
 * RED: `utils/stockChart.ts` 부재 → 동적 import 실패로 전 케이스 FAIL.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

type StockChartUtils = typeof import('../stockChart')
type BarsArg = Parameters<StockChartUtils['toKLineData']>[0]

const ORIG_TZ = process.env.TZ
let sc: StockChartUtils
beforeAll(async () => {
  process.env.TZ = 'UTC'
  sc = await import('../stockChart')
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})

/** KST 자정(= 전날 15:00 UTC)의 epoch ms. */
const kstMidnight = (y: number, m: number, d: number) => Date.UTC(y, m - 1, d - 1, 15)

describe('U1: isChartableTicker — 6자리 숫자만', () => {
  it.each(['005930', '000660', '900110'])('U1-a: %s → true', (t) => {
    expect(sc.isChartableTicker(t)).toBe(true)
  })

  it.each([
    ['영숫자 신주인수권', '0080G0'],
    ['영문 접두', 'Q12345'],
    ['빈 문자열', ''],
    ['하이픈(셀 결측 표기)', '-'],
    ['5자리', '12345'],
    ['7자리 ETN', '0059300'],
    ['null', null],
    ['undefined', undefined],
    ['숫자형', 5930],
  ])('U1-b: %s → false', (_label, t) => {
    expect(sc.isChartableTicker(t as unknown as string)).toBe(false)
  })
})

describe('U2: isInteractiveTarget — 버튼류와 그 자손은 더블클릭 대상이 아니다', () => {
  function el(html: string, pick: string): Element {
    const host = document.createElement('div')
    host.innerHTML = html
    const found = host.querySelector(pick)
    if (!found) throw new Error(`fixture: ${pick} 없음`)
    return found
  }

  it.each([
    ['button', '<button>매도</button>', 'button'],
    ['button 안 span', '<button><span>AI 자문</span></button>', 'span'],
    ['a', '<a href="#">링크</a>', 'a'],
    ['input', '<input type="checkbox" />', 'input'],
    ['select', '<select><option>1</option></select>', 'select'],
    ['textarea', '<textarea></textarea>', 'textarea'],
    ['label', '<label>이름</label>', 'label'],
    ['label 안 span', '<label><span>x</span></label>', 'span'],
  ])('U2-a: %s → true', (_label, html, pick) => {
    expect(sc.isInteractiveTarget(el(html, pick))).toBe(true)
  })

  it.each([
    ['td', '<table><tbody><tr><td>삼성전자</td></tr></tbody></table>', 'td'],
    ['td 안 span(배지)', '<table><tbody><tr><td><span>KRX</span></td></tr></tbody></table>', 'span'],
    ['tr', '<table><tbody><tr><td>x</td></tr></tbody></table>', 'tr'],
  ])('U2-b: %s → false', (_label, html, pick) => {
    expect(sc.isInteractiveTarget(el(html, pick))).toBe(false)
  })

  it('U2-c: null → false', () => {
    expect(sc.isInteractiveTarget(null)).toBe(false)
  })
})

describe('U3: toKLineData — KST 자정 timestamp · 방어 변환 · 오름차순', () => {
  it('U3-a: 2026-09-25 → Date.UTC(2026,8,24,15) (TZ=UTC 에서도 KST 자정)', () => {
    const out = sc.toKLineData([
      { date: '2026-09-25', open: 71000, high: 72000, low: 70500, close: 71800, volume: 1234, amount: 88_000_000 },
    ] as BarsArg)
    expect(out).toEqual([
      {
        timestamp: Date.UTC(2026, 8, 24, 15),
        open: 71000,
        high: 72000,
        low: 70500,
        close: 71800,
        volume: 1234,
        turnover: 88_000_000,
      },
    ])
  })

  it('U3-b: 문자열 숫자를 변환하고, 순서가 섞여 와도 오름차순으로 돌려준다', () => {
    const out = sc.toKLineData([
      { date: '2026-09-28', open: '72000', high: '72500', low: '71500', close: '72100', volume: '11834522', amount: '853269036200' },
      { date: '2026-09-18', open: 71800, high: 72000, low: 70700, close: 70900, volume: 13200981, amount: 935949552900 },
      { date: '2026-09-23', open: '71200', high: '71900', low: '70800', close: '71600', volume: '9934120', amount: '711282992000' },
    ] as unknown as BarsArg)
    expect(out.map((b) => b.timestamp)).toEqual([
      kstMidnight(2026, 9, 18),
      kstMidnight(2026, 9, 23),
      kstMidnight(2026, 9, 28),
    ])
    const last = out[out.length - 1]
    expect(last).toEqual({
      timestamp: kstMidnight(2026, 9, 28),
      open: 72000,
      high: 72500,
      low: 71500,
      close: 72100,
      volume: 11834522,
      turnover: 853269036200,
    })
    for (const b of out) {
      for (const k of ['open', 'high', 'low', 'close', 'volume', 'turnover'] as const) {
        expect(typeof b[k], `${k} 는 number 여야 한다`).toBe('number')
        expect(Number.isFinite(b[k])).toBe(true)
      }
    }
  })

  it('U3-c: 날짜·OHLC 중 하나라도 변환 실패인 봉은 버린다', () => {
    const good = { date: '2026-09-22', open: 70500, high: 71400, low: 70300, close: 71200, volume: 10, amount: 712 }
    const out = sc.toKLineData([
      good,
      { ...good, date: '2026/09/21' },
      { ...good, date: '' },
      { ...good, date: null },
      { ...good, date: '2026-09-19', open: 'abc' },
      { ...good, date: '2026-09-17', close: null },
      { ...good, date: '2026-09-16', high: '' },
      { ...good, date: '2026-09-15', low: undefined },
    ] as unknown as BarsArg)
    expect(out).toHaveLength(1)
    expect(out[0].timestamp).toBe(kstMidnight(2026, 9, 22))
  })

  it('U3-d: 빈 배열·비배열 입력은 빈 배열', () => {
    expect(sc.toKLineData([] as BarsArg)).toEqual([])
    expect(sc.toKLineData(null as unknown as BarsArg)).toEqual([])
    expect(sc.toKLineData(undefined as unknown as BarsArg)).toEqual([])
  })
})

describe('U4: 기간 매핑', () => {
  it('U4-a: PERIOD_TO_KLINE = day/week/month (klinecharts v10 PeriodType)', () => {
    expect(sc.PERIOD_TO_KLINE).toEqual({ D: 'day', W: 'week', M: 'month' })
  })

  it('U4-b: PERIOD_LABEL = 일봉/주봉/월봉', () => {
    expect(sc.PERIOD_LABEL).toEqual({ D: '일봉', W: '주봉', M: '월봉' })
  })
})
