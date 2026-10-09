/**
 * cycle416 Red — 매크로 6번째 섹션 「시장 등락 통계」 컴포넌트 (S1~S12).
 *
 * 명세: `_workspace/red/cycle416/breadth_spec.md` §6 · §7.5
 * 계약: `_workspace/red/cycle416/breadth_contract.md` 「4. 프론트」
 *
 * 봉인하는 계약
 *  - `src/macro/components/MarketBreadthSection.tsx` default export,
 *    props `{ data: MarketBreadthData | null; loading: boolean; error: string | null; days?: number }`(days 기본 20).
 *  - 섹션 래퍼 `data-testid="macro-section-market-breadth"` 는 로딩·실패·정상 **모든 상태**에 있고 제목 「시장 등락 통계」를 단다.
 *  - 시장 토글 `breadth-market-{kospi|kosdaq|total}`(aria-pressed) · 기본 = 합계.
 *  - 요약 칩 `breadth-chip-{adr|up|down|limit-up|limit-down|up-ratio}`.
 *  - 차트 래퍼 `breadth-chart`(`data-market` = 선택 시장) — jsdom 은 SVG 를 그리지 않아 계산은
 *    `marketBreadthChart.ts` 순수 함수로 따로 잰다(`marketBreadthChart.test.ts`).
 *  - 각주 `breadth-footnote` — 기준선 숫자는 응답 `adr_reference` 에서 읽는다.
 *  - 표 `breadth-table` · 행 `breadth-row-{YYYY-MM-DD}` + `breadth-row-total` ·
 *    칸 `breadth-cell-{date|up|down|flat|limit_up|limit_down|no_trade|up_ratio}`.
 *    표는 `overflow-x-auto` 상자 안, 표 자체는 `min-w-[560px]`(400px 폭에서 가로로 민다).
 *  - 상태 줄 `breadth-missing`(노란 상자) · `breadth-short`(창 부족) · `breadth-pending`(아직 없음).
 *  - 날짜 `MM-DD` 는 문자열 자르기, `asof` 는 `utils/kst.ts::formatKstDateTime`.
 *  - 색: 상승·상한가 = 빨강(`text-red-*` 또는 `text-pnl-profit`) · 하락·하한가 = 파랑(`text-blue-*` 또는 `text-pnl-loss`).
 *
 * RED: 컴포넌트 부재 → import 실패로 전 케이스 FAIL.
 */
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

import MarketBreadthSection from '../components/MarketBreadthSection'
import { MARKET_BREADTH_FIXTURE } from '../../test/fixtures/marketBreadth.fixture'
import type { MarketBreadthData } from '../../types/market-breadth'

const RED = /\btext-(red-\d{3}|pnl-profit)\b/
const BLUE = /\btext-(blue-\d{3}|pnl-loss)\b/

function fixture(overrides: Partial<MarketBreadthData> = {}): MarketBreadthData {
  return { ...structuredClone(MARKET_BREADTH_FIXTURE), ...overrides }
}

function renderData(data: MarketBreadthData = fixture()) {
  return render(<MarketBreadthSection data={data} loading={false} error={null} />)
}

const text = (testId: string) => screen.getByTestId(testId).textContent ?? ''
const cell = (row: string, col: string) =>
  within(screen.getByTestId(`breadth-row-${row}`)).getByTestId(`breadth-cell-${col}`)

describe('MarketBreadthSection — 시장 등락 통계 (cycle416)', () => {
  it('S1 로딩 — 섹션·제목은 그대로 두고 스피너에 KRX 안내 문장(요청 일수)을 띄운다', () => {
    render(<MarketBreadthSection data={null} loading error={null} />)
    const section = screen.getByTestId('macro-section-market-breadth')
    expect(section.textContent).toContain('시장 등락 통계')
    expect(section.textContent).toContain('최근 20영업일 전 종목 시세를 받는 중')
    expect(screen.queryByTestId('breadth-table')).toBeNull()
  })

  it('S1b 로딩 문장은 days 를 따른다', () => {
    render(<MarketBreadthSection data={null} loading error={null} days={60} />)
    expect(text('macro-section-market-breadth')).toContain('최근 60영업일')
  })

  it('S2 실패 — 서버 문장을 그대로 ErrorAlert 로', () => {
    const msg = 'KRX 공개 API 가 꺼져 있어 시장 등락 통계를 만들 수 없습니다 — 설정 화면의 외부 연동에서 켤 수 있습니다'
    render(<MarketBreadthSection data={null} loading={false} error={msg} />)
    const section = screen.getByTestId('macro-section-market-breadth')
    expect(section.textContent).toContain('오류:')
    expect(section.textContent).toContain(msg)
    expect(screen.queryByTestId('breadth-table')).toBeNull()
  })

  it('S3 머리줄 — 기간 · 영업일 수 · KRX · 기준 시각(KST 로 환산)', () => {
    // UTC 로 와도 KST 로 보여야 kst.ts 를 거친 것이다(02:00:03Z = 11:00:03 KST).
    renderData(fixture({ asof_kst: '2026-10-09T02:00:03Z' }))
    const head = text('macro-section-market-breadth')
    expect(head).toContain('2026-10-06~2026-10-08')
    expect(head).toContain('3영업일')
    expect(head).toContain('KRX')
    expect(head).toContain('2026-10-09 11:00:03')
  })

  it('S4 시장 토글 — 기본 합계, 셋 다 있다', () => {
    renderData()
    for (const m of ['kospi', 'kosdaq', 'total']) {
      expect(screen.getByTestId(`breadth-market-${m}`)).toBeTruthy()
    }
    expect(screen.getByTestId('breadth-market-total').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('breadth-market-kospi').getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByTestId('breadth-market-total').textContent).toContain('합계')
    expect(screen.getByTestId('breadth-market-kospi').textContent).toContain('코스피')
    expect(screen.getByTestId('breadth-market-kosdaq').textContent).toContain('코스닥')
    expect(screen.getByTestId('breadth-chart').getAttribute('data-market')).toBe('total')
  })

  it('S5 요약 칩(합계) — ADR · 상승/하락 · 상·하한가 · 상승 비율', () => {
    renderData()
    expect(text('breadth-chip-adr')).toContain('ADR')
    expect(text('breadth-chip-adr')).toContain('74.9')
    expect(text('breadth-chip-adr')).not.toMatch(/\(\d+일\)/) // n_days == requested 면 일수를 붙이지 않는다
    expect(text('breadth-chip-up')).toContain('3,270')
    expect(text('breadth-chip-down')).toContain('4,366')
    expect(text('breadth-chip-limit-up')).toContain('상한가')
    expect(text('breadth-chip-limit-up')).toContain('27')
    expect(text('breadth-chip-limit-down')).toContain('하한가')
    expect(text('breadth-chip-limit-down')).toContain('4')
    expect(text('breadth-chip-up-ratio')).toContain('40.8%')
    expect(screen.getByTestId('breadth-chip-up').className).toMatch(RED)
    expect(screen.getByTestId('breadth-chip-down').className).toMatch(BLUE)
    // ADR 숫자에는 판정 문구를 붙이지 않는다(§4.2)
    expect(text('breadth-chip-adr')).not.toMatch(/과열|침체|바닥|위험/)
  })

  it('S6 코스닥으로 바꾸면 칩·표·차트가 모두 따라간다', () => {
    renderData()
    expect(cell('2026-10-08', 'up').textContent).toBe('870')

    fireEvent.click(screen.getByTestId('breadth-market-kosdaq'))

    expect(screen.getByTestId('breadth-market-kosdaq').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('breadth-market-total').getAttribute('aria-pressed')).toBe('false')
    expect(text('breadth-chip-adr')).toContain('80.3')
    expect(text('breadth-chip-up')).toContain('2,218')
    expect(text('breadth-chip-down')).toContain('2,761')
    expect(text('breadth-chip-limit-up')).toContain('23')
    expect(text('breadth-chip-up-ratio')).toContain('42.3%')
    expect(cell('2026-10-08', 'up').textContent).toBe('618')
    expect(cell('2026-10-08', 'down').textContent).toBe('1,031')
    expect(cell('total', 'up').textContent).toBe('2,218')
    expect(screen.getByTestId('breadth-chart').getAttribute('data-market')).toBe('kosdaq')

    fireEvent.click(screen.getByTestId('breadth-market-kospi'))
    expect(text('breadth-chip-adr')).toContain('65.5')
    expect(cell('2026-10-08', 'up').textContent).toBe('252')
  })

  it('S7 날짜별 표 — 행 = days 수 + 합계 1줄, 최신 먼저, 칸 값·서식', () => {
    renderData()
    const rows = screen.getAllByTestId(/^breadth-row-/)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'breadth-row-2026-10-08',
      'breadth-row-2026-10-07',
      'breadth-row-2026-10-06',
      'breadth-row-total',
    ])
    for (const r of rows) expect(screen.getByTestId('breadth-table').contains(r)).toBe(true)

    expect(cell('2026-10-08', 'date').textContent).toBe('10-08')
    expect(cell('2026-10-08', 'up').textContent).toBe('870')
    expect(cell('2026-10-08', 'down').textContent).toBe('1,656')
    expect(cell('2026-10-08', 'flat').textContent).toBe('149')
    expect(cell('2026-10-08', 'limit_up').textContent).toBe('16')
    expect(cell('2026-10-08', 'limit_down').textContent).toBe('1')
    expect(cell('2026-10-08', 'no_trade').textContent).toBe('90')
    expect(cell('2026-10-08', 'up_ratio').textContent).toBe('32.5%')

    expect(cell('total', 'date').textContent).toContain('3일 합계')
    expect(cell('total', 'up').textContent).toBe('3,270')
    expect(cell('total', 'down').textContent).toBe('4,366')
    expect(cell('total', 'no_trade').textContent).toBe('270')
    expect(cell('total', 'up_ratio').textContent).toBe('40.8%')

    const thead = screen.getByTestId('breadth-table').querySelector('thead')
    expect(thead, '머리줄은 <thead> 안').not.toBeNull()
    const header = within(thead as HTMLElement).getAllByRole('columnheader').map((h) => h.textContent)
    expect(header).toEqual(['날짜', '상승', '하락', '보합', '상한가', '하한가', '거래 없음', '상승 비율'])
  })

  it('S8 색 — 상승·상한가 빨강, 하락·하한가 파랑(한국 관례)', () => {
    renderData()
    for (const row of ['2026-10-08', 'total']) {
      for (const col of ['up', 'limit_up']) {
        expect(cell(row, col).className).toMatch(RED)
        expect(cell(row, col).className).not.toMatch(BLUE)
      }
      for (const col of ['down', 'limit_down']) {
        expect(cell(row, col).className).toMatch(BLUE)
        expect(cell(row, col).className).not.toMatch(RED)
      }
    }
  })

  it('S9 400px 폭 — 표는 가로 스크롤 상자(overflow-x-auto) 안, 표 최소 폭 560px', () => {
    renderData()
    const table = screen.getByTestId('breadth-table')
    expect(table.className).toContain('min-w-[560px]')
    let box: HTMLElement | null = table.parentElement
    while (box && !box.className.includes('overflow-x-auto')) box = box.parentElement
    expect(box, '표를 감싼 overflow-x-auto 상자가 없다').not.toBeNull()
    expect(screen.getByTestId('macro-section-market-breadth').contains(box)).toBe(true)
  })

  it('S10 일부 빠짐 — 노란 상자에 일수와 MM-DD 목록, ADR 에 일수 표시', () => {
    renderData(
      fixture({
        missing_dates: ['2026-10-02', '2026-09-30'],
        window: { ...MARKET_BREADTH_FIXTURE.window, requested: 5, complete: false },
      }),
    )
    const box = text('breadth-missing')
    expect(box).toContain('2일 자료를 받지 못했습니다')
    expect(box).toContain('10-02')
    expect(box).toContain('09-30')
    expect(text('breadth-chip-adr')).toContain('ADR(3일)')
    expect(screen.queryByTestId('breadth-short')).toBeNull()
  })

  it('S11 창 부족 — complete=false 이고 빠진 날이 없으면 회색 한 줄', () => {
    renderData(fixture({ window: { ...MARKET_BREADTH_FIXTURE.window, requested: 20, complete: false } }))
    expect(text('breadth-short')).toContain('3일뿐')
    expect(screen.queryByTestId('breadth-missing')).toBeNull()
  })

  it('S12 아직 없음 · 빈 날 — pending_date 는 안내 줄, empty_dates 는 표시하지 않는다', () => {
    renderData(fixture({ pending_date: '2026-10-09', empty_dates: ['2026-10-05'] }))
    expect(text('breadth-pending')).toContain('10-09 자료는 아직 KRX 에 올라오지 않았습니다')
    expect(text('macro-section-market-breadth')).not.toContain('10-05')
  })

  it('S12b 정상 상태에는 상태 줄이 하나도 없다', () => {
    renderData()
    for (const id of ['breadth-missing', 'breadth-short', 'breadth-pending']) {
      expect(screen.queryByTestId(id)).toBeNull()
    }
  })

  it('S13 ADR null(Σ하락 0) 은 「—」', () => {
    const d = fixture()
    d.summary.total = { ...d.summary.total, adr: null }
    renderData(d)
    expect(text('breadth-chip-adr')).toContain('—')
    expect(text('breadth-chip-adr')).not.toMatch(/\d/)
  })

  it('S14 각주 — 기준선 숫자는 응답 adr_reference 에서, 판정 문구 없이', () => {
    renderData(fixture({ adr_reference: { oversold: 70, overheated: 130 } }))
    const foot = text('breadth-footnote')
    expect(foot).toContain('70')
    expect(foot).toContain('130')
    expect(foot).toContain('ADR')
  })
})
