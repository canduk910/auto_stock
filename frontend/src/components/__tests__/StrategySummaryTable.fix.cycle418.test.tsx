/**
 * cycle418-M Red — suites N6: 엔진 정지이고 funnel 이 없으면 요약 「후보」가 0(모름이어야 한다).
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
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  prices?: (p: Record<string, TickerPrice>) => void
  running?: boolean | null
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
      now={KST_0912}
      running={o.running}
      onSelect={() => {}}
    />,
  )
}

describe('N6(suites) — 엔진 정지 + funnel 없음 → 요약 「후보」는 모름(0 아님)', () => {
  it('running=false ∧ targets 도 비면 후보 칸이 모름', () => {
    renderTable({
      running: false,
      strategies: (s) => { s.donchian_swing.targets = {} },
      monitor: (m) => { m.donchian_swing.funnel = [] },
    })
    const cell = screen.getByTestId('strategy-summary-candidates-donchian_swing')
    expect(cell.textContent).toMatch(/모름/)
  })

  it('running=true(평소) + targets 0 + funnel 0 → 숫자 0 그대로(회귀 없음)', () => {
    renderTable({
      running: true,
      strategies: (s) => { s.donchian_swing.targets = {} },
      monitor: (m) => { m.donchian_swing.funnel = [] },
    })
    const cell = screen.getByTestId('strategy-summary-candidates-donchian_swing')
    expect(cell.textContent).not.toMatch(/모름/)
    expect(cell.textContent).toMatch(/^0/)
  })
})
