/**
 * cycle414 Red — 대시보드 「전체」 탭 전략 요약표(`src/components/StrategySummaryTable.tsx`).
 *
 * 명세 = `_workspace/red/cycle414/monitor_spec.md` §5(요약표 칸 · 「왜 안 사나」 12단계 우선순위) · §8.1 F2.
 *
 * 계약(Green 이 만들 것):
 *
 * ```tsx
 * <StrategySummaryTable
 *   strategies={status.strategies} monitor={monitorData | null} exitLines={items | null}
 *   tickerPrices={scan.ticker_prices} now={Date} onSelect={(sid) => …}
 * />
 * ```
 *
 * 테스트 id: `strategy-summary-table` · 행 `strategy-summary-row-<sid>`(누르면 `onSelect(sid)`) · 주 배지
 * `strategy-summary-badge-<sid>` · 왜 안 사나 `strategy-summary-why-<sid>` · 보유 `strategy-summary-holdings-<sid>` ·
 * 예산 `strategy-summary-budget-<sid>` · 손절 여유 `strategy-summary-stopmargin-<sid>`(`data-tone` normal|orange|red) ·
 * 청산 예정 `strategy-summary-exitdue-<sid>` · 오늘 신호 `strategy-summary-signals-<sid>`.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

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
  prices?: (p: Record<string, TickerPrice>) => void
  onSelect?: (sid: string) => void
}

function renderTable(o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  o.prices?.(prices)
  let monitor: Dict | null = clone(makeMonitor()) as Dict
  if (o.monitor === null) monitor = null
  else o.monitor?.(monitor.strategies)
  return render(
    <StrategySummaryTable
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      now={o.now ?? KST_0912}
      onSelect={o.onSelect ?? (() => {})}
    />,
  )
}

const why = (sid: string) => screen.getByTestId(`strategy-summary-why-${sid}`).textContent ?? ''
const at = (hhmm: string) => new Date(`2026-10-12T${hhmm}:00+09:00`)

describe('요약표 — 행 · 순서 · 배지', () => {
  it('등록 전략마다 한 행 · 순서 = 실매매 → 멈춤 → 섀도 → 꺼짐, 같은 묶음은 비중 내림차순', () => {
    renderTable({ strategies: (s) => { s.bull_flag_breakout.weight = 0.15 } })
    const rows = within(screen.getByTestId('strategy-summary-table')).getAllByTestId(/^strategy-summary-row-/)
    expect(rows.map((r) => r.getAttribute('data-testid')!.replace('strategy-summary-row-', ''))).toEqual([
      'bull_flag_breakout', 'vcp_breakout', 'momentum',
      'kojiro', 'donchian_swing', 'etf_trend',
      'volatility_breakout',
      'long_tail_volatility',
    ])
  })

  it('주 배지 + 빨강 보조 칩만 — 꺼짐 + 보유 → 「손절 정지」 (F2)', () => {
    renderTable({
      strategies: (s) => {
        s.long_tail_volatility.positions = 1
        s.long_tail_volatility.positions_detail = {
          '457370': { name: 'A', buy_price: 1000, quantity: 1, high_since_buy: 1000, buy_date: '2026-10-06', is_next_day: true },
        }
      },
    })
    expect(screen.getByTestId('strategy-summary-badge-long_tail_volatility').textContent).toMatch(/꺼짐/)
    expect(screen.getByTestId('strategy-summary-row-long_tail_volatility').textContent).toMatch(/손절 정지/)
    expect(screen.getByTestId('strategy-summary-badge-etf_trend').textContent).toMatch(/멈춤/)
    expect(screen.getByTestId('strategy-summary-badge-volatility_breakout').textContent).toMatch(/섀도/)
    expect(screen.getByTestId('strategy-summary-badge-momentum').textContent).toMatch(/실매매/)
  })

  it('행을 누르면 그 전략 탭으로(onSelect)', () => {
    const onSelect = vi.fn()
    renderTable({ onSelect })
    fireEvent.click(screen.getByTestId('strategy-summary-row-etf_trend'))
    expect(onSelect).toHaveBeenCalledWith('etf_trend')
  })

  it('400px — 표는 가로 스크롤 래퍼 안', () => {
    renderTable()
    const table = within(screen.getByTestId('strategy-summary-table')).getByRole('table')
    let el: HTMLElement | null = table.parentElement
    let ok = false
    while (el && !ok) {
      ok = /overflow-x-auto|overflow-auto/.test(el.className) || el.style.overflowX === 'auto'
      el = el.parentElement
    }
    expect(ok).toBe(true)
  })
})

describe('「왜 안 사나」 한 줄 — 12단계 우선순위(처음 맞는 하나) · 명세 §5.2', () => {
  it('1 꺼짐 + 보유 → 「꺼짐 — 보유 1 손절 정지!」', () => {
    renderTable({
      strategies: (s) => {
        s.long_tail_volatility.positions = 1
        s.long_tail_volatility.positions_detail = {
          '457370': { name: 'A', buy_price: 1000, quantity: 1, high_since_buy: 1000, buy_date: '2026-10-06', is_next_day: true },
        }
      },
    })
    expect(why('long_tail_volatility')).toMatch(/꺼짐.*보유 1.*손절 정지/)
  })

  it('2 멈춤이 최종 후보 0 보다 먼저 — kojiro 는 「신규 매수 멈춤(운영자 설정)」', () => {
    renderTable()
    expect(why('kojiro')).toMatch(/신규 매수 멈춤/)
    expect(why('kojiro')).not.toMatch(/후보 0/)
  })

  it('3 준비 실패 → 「후보 준비 실패 07:46」', () => {
    renderTable({
      strategies: (s) => { s.etf_trend.params.buy_paused = false },
      monitor: (m) => { m.etf_trend.prepare.ok = false },
    })
    expect(why('etf_trend')).toMatch(/후보 준비 실패 07:46/)
  })

  it('4 최종 후보 0 → 「후보 0 — 병목: (처음 0 인 단계 이름)」 · 매수 중단보다 먼저', () => {
    renderTable({ strategies: (s) => { s.kojiro.params.buy_paused = false; s.kojiro.buy_disabled = true } })
    expect(why('kojiro')).toMatch(/후보 0.*병목.*6→1 전환 인접/)
  })

  it('5 매수 중단 → 「매수 중단(일일 손실 한도 또는 19:50 이후)」', () => {
    renderTable({ strategies: (s) => { s.vcp_breakout.buy_disabled = true } })
    expect(why('vcp_breakout')).toMatch(/매수 중단/)
  })

  it('6 보유 한도 → 「보유 한도 5/5」', () => {
    renderTable({ strategies: (s) => { s.bull_flag_breakout.positions = 5 } })
    expect(why('bull_flag_breakout')).toMatch(/보유 한도 5\s*\/\s*5/)
  })

  it('7 진입창 밖 → 「진입창 밖 — 다음 09:05」', () => {
    renderTable({ now: at('15:00') })
    expect(why('vcp_breakout')).toMatch(/진입창 밖.*09:05/)
  })

  it('8 시장 유닛 차단(etf shadow m=0) → 「시장 유닛 0배」', () => {
    renderTable({
      strategies: (s) => { s.etf_trend.params.buy_paused = false },
      monitor: (m) => { m.etf_trend.market_unit = { mode: 'shadow', ok: true, m: 0, state: 'down_falling', bar_date: '2026-10-08' } },
    })
    expect(why('etf_trend')).toMatch(/시장 유닛 0배/)
  })

  it('9 켜짐 + 비중 0 + 섀도 아님 → 「예산 0」', () => {
    renderTable({ strategies: (s) => { s.vcp_breakout.weight = 0; s.vcp_breakout.total_investment = 0 } })
    expect(why('vcp_breakout')).toMatch(/예산 0/)
  })

  it('10 오늘 거르기 사유 최다 → 「오늘 주 사유: 거래량 미관측(3종목)」', () => {
    renderTable({
      monitor: (m) => {
        m.vcp_breakout.skips = { known: true, day: '2026-10-12', counts: { no_data: 3, reject_ext: 1 }, by_ticker: {} }
      },
    })
    expect(why('vcp_breakout')).toMatch(/오늘 주 사유.*거래량 미관측.*3종목/)
  })

  it('11 섀도 → 「섀도 기록 2」', () => {
    renderTable()
    expect(why('volatility_breakout')).toMatch(/섀도 기록 2/)
  })

  it('12 그 밖 → 「대기 중 — 후보 8 …」', () => {
    renderTable()
    expect(why('vcp_breakout')).toMatch(/대기 중.*후보 8/)
  })
})

describe('요약표 칸 — 보유 · 예산 · 손절 여유 · 청산 예정 · 신호', () => {
  it('보유 = positions / max_positions', () => {
    renderTable()
    expect(screen.getByTestId('strategy-summary-holdings-etf_trend').textContent).toMatch(/1\s*\/\s*4/)
    expect(screen.getByTestId('strategy-summary-holdings-donchian_swing').textContent).toMatch(/1\s*\/\s*6/)
  })

  it('예산 사용률 = invested_amount / total_investment', () => {
    renderTable()
    expect(screen.getByTestId('strategy-summary-budget-etf_trend').textContent).toMatch(/50%/)
  })

  it('손절 여유 = 보유 중 가장 가까운 실효 손절선(exit-lines)까지 % · 3% 미만 주황 · 1% 미만 빨강', () => {
    const r1 = renderTable()
    const m = screen.getByTestId('strategy-summary-stopmargin-etf_trend')
    expect(m.textContent).toMatch(/4\.3%/)  // (10700−10240)/10700
    expect(m.getAttribute('data-tone')).toBe('normal')
    r1.unmount()
    renderTable({ prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: 10_300 } } })
    expect(screen.getByTestId('strategy-summary-stopmargin-etf_trend').getAttribute('data-tone')).toBe('red')
  })

  it('청산 예정 = 오늘 15:20 판정 대상 수(etf 돌파 실패 · donchian 시간청산 due≤0)', () => {
    const r1 = renderTable({ prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: 9_850 } } }) // 돌파선 9,900 아래
    expect(screen.getByTestId('strategy-summary-exitdue-etf_trend').textContent).toMatch(/1/)
    r1.unmount()
    renderTable({ monitor: (m) => { m.donchian_swing.holdings['000660'].days_held = 19 } })
    expect(screen.getByTestId('strategy-summary-exitdue-donchian_swing').textContent).toMatch(/1/)
  })

  it('오늘 신호 — 섀도 전략은 「섀도 n」', () => {
    renderTable()
    expect(screen.getByTestId('strategy-summary-signals-volatility_breakout').textContent).toMatch(/섀도 2/)
  })

  it('라우트 실패(monitor=null)에도 표는 그린다 — 라우트 값 칸만 「—」', () => {
    renderTable({ monitor: null })
    expect(screen.getByTestId('strategy-summary-row-etf_trend')).toBeTruthy()
    expect(why('etf_trend')).toMatch(/신규 매수 멈춤/)
  })
})
