/**
 * cycle414 보완 1차 Red — 대시보드 「전체」 탭 전략 요약표(`src/components/StrategySummaryTable.tsx`).
 *
 * 판정 원문 = 1차 검수 verdict. 명세 = `_workspace/red/cycle414/monitor_spec.md` §5.
 *
 * | 결함 | 이 파일의 단언 |
 * |---|---|
 * | H3 | 라우트 `running=false`(정산 뒤·부팅 전·휴일) → 「왜 안 사나」 = 「장 마감/엔진 정지」 · 「예산 0」 단정 0 |
 * | M1 | 터틀 enforce + 오늘 스냅샷 없음 = 엔진 m=1 → 「시장 유닛 …」 사유 0 |
 * | M3 | ETF 「청산 예정」 = `breakout_fail.active` ∧ 돌파선 있음 ∧ 현재가 < 돌파선 일 때만 |
 * | M6 | 손절 여유 근접 = 색 클래스(빨강 `rose` · 주황 `amber`) |
 * | M7 | 최종 단계 = 전략별 최종 `step_no`(donchian·VCP·BFB·kojiro = 9) |
 * | M11 | §5.1 막대·선 — 보유 칸 막대(n칸 중 채움) · 예산 가로 막대 · 14일 선(svg) |
 * | M12 | 표 최소 폭 · 요약표는 높이 상한 상자(220px 에 1행만 보이던 것)에 가두지 않는다 |
 * | L5 | 전략 이름 = `strategyLabel(id)`(API `name` 이 「상한가 모멘텀」 이어도 「모멘텀」) |
 *
 * 새 prop 계약(Green 이 만들 것): `funnelTrends?: Record<string, Array<{ date: string; count: number }>> | null` —
 * 전략별 14일 최종 후보 수(`/api/strategy-funnel/recent`). 칸 = `strategy-summary-trend-<sid>`(svg 선).
 * 보유 칸 막대는 `[data-filled]` 칸 `max_positions` 개(채운 칸 = 보유 수) 또는 svg, 예산 막대는 `width: n%` 막대 또는 svg.
 */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import StrategySummaryTable from '../StrategySummaryTable'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  ETF_HELD, KST_0912, clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  now?: Date
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  monitorRoot?: (root: Dict) => void
  prices?: (p: Record<string, TickerPrice>) => void
  funnelTrends?: Record<string, Array<{ date: string; count: number }>> | null
}

function renderTable(o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  o.prices?.(prices)
  let monitor: Dict | null = clone(makeMonitor()) as Dict
  if (o.monitor === null) monitor = null
  else {
    o.monitor?.(monitor.strategies)
    o.monitorRoot?.(monitor)
  }
  const extra = { funnelTrends: o.funnelTrends ?? null } as Record<string, unknown>
  return render(
    <StrategySummaryTable
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      now={o.now ?? KST_0912}
      onSelect={() => {}}
      {...extra}
    />,
  )
}

const why = (sid: string) => screen.getByTestId(`strategy-summary-why-${sid}`).textContent ?? ''
const RED = /\btext-(rose|red)-[5-9]00\b/
const ORANGE = /\btext-(amber|orange)-[5-9]00\b/

function engineFunnel(names: string[], counts: number[]) {
  return names.map((step_name, i) => ({
    step_no: i + 1, step_name, step_conditions: null, survived_count: counts[i], excluded_count: 0,
  }))
}

// ─────────────────────────────────────────────────────────────────────────────
describe('H3 — 엔진 정지(running=false)면 「왜 안 사나」 = 장 마감/엔진 정지', () => {
  const stopped = () => renderTable({
    strategies: (s) => {
      for (const sid of Object.keys(s)) {
        Object.assign(s[sid], { positions: 0, positions_detail: {}, position_tickers: [], total_investment: 0, invested_amount: 0 })
      }
      s.etf_trend.params.buy_paused = false
    },
    monitorRoot: (root) => { root.running = false },
  })

  it('실매매 전략(모멘텀) → 「장 마감/엔진 정지」', () => {
    stopped()
    expect(why('momentum')).toMatch(/엔진 정지|장 마감/)
  })

  it('ETF(멈춤 해제·정산으로 예산 0) → 「예산 0」 단정 0 · 「장 마감/엔진 정지」', () => {
    stopped()
    expect(why('etf_trend')).not.toMatch(/예산 0/)
    expect(why('etf_trend')).toMatch(/엔진 정지|장 마감/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M1 — 터틀 enforce + 오늘 스냅샷 없음 = 엔진 m=1(차단 아님)', () => {
  it('돈키언(멈춤 해제) enforce·결손 → 「시장 유닛」 사유가 아니다', () => {
    renderTable({
      strategies: (s) => { s.donchian_swing.params.buy_paused = false; s.donchian_swing.params.market_unit_mode = 'enforce' },
      monitor: (m) => { m.donchian_swing.market_unit = { mode: 'enforce', ok: false, reason: 'not_computed' } },
    })
    expect(why('donchian_swing')).not.toMatch(/시장 유닛/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M3 — ETF 청산 예정은 가격이 돌파선 아래일 때만', () => {
  it('현재가 10,700 > 돌파선 9,900 · 판정 대상 → 청산 예정 0', () => {
    renderTable()
    expect(screen.getByTestId('strategy-summary-exitdue-etf_trend').textContent?.trim()).toBe('0')
  })

  it('돌파선 없음(line=null) → 청산 예정 0(엔진은 missing_line 으로 판정 안 함)', () => {
    renderTable({
      prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: 9_850 } },
      monitor: (m) => { m.etf_trend.holdings[ETF_HELD].breakout_fail.line = null },
    })
    expect(screen.getByTestId('strategy-summary-exitdue-etf_trend').textContent?.trim()).toBe('0')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M6 — 손절 여유 근접은 색 클래스로', () => {
  it.each([
    [10_300, 'red'],
    [10_500, 'orange'],
  ])('ETF 현재가 %s → %s 색', (cur, tone) => {
    renderTable({ prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: cur } } })
    const el = screen.getByTestId('strategy-summary-stopmargin-etf_trend')
    expect(el.getAttribute('data-tone')).toBe(tone)
    expect(el.className).toMatch(tone === 'red' ? RED : ORANGE)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M7 — 최종 단계 = 전략별 최종 step_no', () => {
  it('돈키언 최종(9) 0 → 「후보 0 — 병목: 신고가 돌파」', () => {
    renderTable({
      strategies: (s) => { s.donchian_swing.params.buy_paused = false },
      monitor: (m) => {
        m.donchian_swing.funnel = engineFunnel(
          ['합집합', '시총+거래대금', '진입 차단 13건', '일봉 fetch', '신고가 돌파', 'EMA 우상향', '거래대금', 'ATR', '최종 후보'],
          [400, 380, 300, 290, 0, 0, 0, 0, 0],
        )
      },
    })
    expect(why('donchian_swing')).toMatch(/후보 0.*병목.*신고가 돌파/)
  })

  it('VCP 최종(9) 8 → 「대기 중 — 후보 8」(후보표 종목 수 1 이 아니라 엔진 최종 수)', () => {
    renderTable({
      monitor: (m) => {
        m.vcp_breakout.funnel = engineFunnel(
          ['전체', '시총', '유니버스', '일봉', 'EMA 정렬', '베이스', 'Pullback', '거래량 수축', '최종 prepared'],
          [2000, 900, 850, 800, 40, 9, 8, 8, 8],
        )
      },
    })
    expect(why('vcp_breakout')).toMatch(/대기 중.*후보 8/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M11 — §5.1 요약표 막대·선', () => {
  it('보유 칸 = n칸 중 채움 막대(ETF 1/4)', () => {
    renderTable()
    const cell = screen.getByTestId('strategy-summary-holdings-etf_trend')
    const cells = cell.querySelectorAll('[data-filled]')
    const filled = cell.querySelectorAll('[data-filled="true"]')
    const svg = cell.querySelector('svg')
    expect(svg !== null || (cells.length === 4 && filled.length === 1), '보유 칸 막대(4칸 중 1칸)').toBe(true)
    expect(cell.textContent).toMatch(/1\s*\/\s*4/)
  })

  it('예산 칸 = 0~100% 가로 막대(ETF 50%)', () => {
    renderTable()
    const cell = screen.getByTestId('strategy-summary-budget-etf_trend')
    const bar = Array.from(cell.querySelectorAll<HTMLElement>('*')).find((n) => n.style?.width === '50%')
    expect(bar !== undefined || cell.querySelector('svg') !== null, '예산 막대').toBe(true)
    expect(cell.textContent).toMatch(/50%/)
  })

  it('14일 칸 = 최종 후보 선(svg) — funnelTrends 로 받은 전략마다', () => {
    renderTable({
      funnelTrends: {
        etf_trend: [{ date: '2026-10-08', count: 2 }, { date: '2026-10-11', count: 0 }, { date: '2026-10-12', count: 1 }],
        donchian_swing: [{ date: '2026-10-08', count: 3 }, { date: '2026-10-12', count: 3 }],
      },
    })
    for (const sid of ['etf_trend', 'donchian_swing']) {
      const cell = screen.getByTestId(`strategy-summary-trend-${sid}`)
      expect(cell.querySelector('svg'), sid).not.toBeNull()
    }
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M12 — 400px: 표 최소 폭 · 요약표를 높이 상한 상자에 가두지 않는다', () => {
  it('표에 최소 폭(min-w-* 또는 style.minWidth) + 가로 스크롤 래퍼', () => {
    renderTable()
    const box = screen.getByTestId('strategy-summary-table')
    const table = within(box).getByRole('table')
    expect(/\bmin-w-/.test(table.className) || table.style.minWidth !== '').toBe(true)
  })

  it('요약표 래퍼 어디에도 인라인 max-height 가 없다(220px 상자에 1행만 보이던 것)', () => {
    renderTable()
    const box = screen.getByTestId('strategy-summary-table')
    const table = within(box).getByRole('table')
    const capped: string[] = []
    for (let n: HTMLElement | null = table; n && n !== box.parentElement; n = n.parentElement) {
      if (n.style.maxHeight) capped.push(`${n.getAttribute('data-testid') ?? n.tagName}: ${n.style.maxHeight}`)
    }
    expect(capped, capped.join('\n')).toEqual([])
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L5 — 전략 이름 = strategyLabel(id)', () => {
  it('API name 「상한가 모멘텀」 → 「모멘텀」', () => {
    renderTable({ strategies: (s) => { s.momentum.name = '상한가 모멘텀' } })
    const first = screen.getByTestId('strategy-summary-row-momentum').querySelector('td') as HTMLElement
    expect(first.textContent).toMatch(/모멘텀/)
    expect(first.textContent).not.toMatch(/상한가/)
  })
})
