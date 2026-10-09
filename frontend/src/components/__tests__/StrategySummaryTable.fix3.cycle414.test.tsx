/**
 * cycle414 보완 3차 Red — 2차 재검증 verdict(verdict2.md) N-C.
 *
 * N-C | `MiniTrend`(§5 요약표 14일 추이 한 칸)에 `<title>`이 없고 `aria-label`에 날짜·값이 없다
 *       (정적 「14일 최종 후보 추이」 문구만) — 스크린리더가 값을 읽을 수 없다.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrategySummaryTable from '../StrategySummaryTable'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  KST_0912, clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  funnelTrends?: Record<string, Array<{ date: string; count: number }>> | null
}

function renderTable(o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  const monitor = clone(makeMonitor()) as Dict
  return render(
    <StrategySummaryTable
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      funnelTrends={o.funnelTrends ?? undefined}
      now={KST_0912}
      running
      onSelect={() => {}}
    />,
  )
}

describe('N-C — MiniTrend 에 title·aria-label 로 날짜·값이 담긴다', () => {
  it('<title> 에 날짜·값이 있다', () => {
    renderTable({
      funnelTrends: { donchian_swing: [{ date: '2026-10-08', count: 2 }, { date: '2026-10-09', count: 0 }] },
    })
    const cell = screen.getByTestId('strategy-summary-trend-donchian_swing')
    const svg = cell.querySelector('svg')!
    const title = svg.querySelector('title')
    expect(title).not.toBeNull()
    expect(title!.textContent).toMatch(/10-08/)
    expect(title!.textContent).toMatch(/2/)
    expect(title!.textContent).toMatch(/10-09/)
    expect(title!.textContent).toMatch(/0/)
  })

  it('aria-label 에도 날짜·값이 있다(정적 문구만 금지)', () => {
    renderTable({
      funnelTrends: { donchian_swing: [{ date: '2026-10-08', count: 2 }, { date: '2026-10-09', count: 0 }] },
    })
    const cell = screen.getByTestId('strategy-summary-trend-donchian_swing')
    const svg = cell.querySelector('svg')!
    const aria = svg.getAttribute('aria-label') ?? ''
    expect(aria).toMatch(/10-08/)
    expect(aria).toMatch(/10-09/)
  })
})
