/**
 * cycle423 리팩토링 카드 #6(④ N-e) — Red.
 *
 * 정본 = `_workspace/refactor/2026-10-09_review.md` 「카드 #6」. 라우트 `GET /api/strategies/monitor`
 * 응답(`routeEntry`)의 `bought_today`(엔진 `_bought_today`)·`sold_today`(`state.sold_today`)를
 * 후보·보유 표의 종목명 옆에 「오늘 매수함」·「오늘 매도함(당일 재매수 막힘)」 배지로 보인다.
 * 지금은 두 값을 읽지 않는다(백엔드만 cycle423 카드 #6 으로 먼저 노출했다).
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrategyMonitor from '../StrategyMonitor'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  DC_CAND, DC_HELD, ETF_A, ETF_HELD, KST_0912,
  clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  monitor?: ((m: Dict) => void) | null
}

function renderPanel(sid: string, o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  const monitor = clone(makeMonitor()) as Dict
  o.monitor?.(monitor.strategies)
  return render(
    <StrategyMonitor
      strategyId={sid}
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      tickerNames={status.scan.ticker_names}
      subscribedTickers={status.scan.subscribed_tickers}
      funnelTrend={null}
      now={KST_0912}
    />,
  )
}

describe('카드 #6(N-e) — bought_today/sold_today 배지', () => {
  it('후보 표 — bought_today 에 든 종목에 「오늘 매수함」 배지', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => { m.donchian_swing.bought_today = [DC_CAND]; m.donchian_swing.sold_today = [] },
    })
    expect(screen.getByTestId(`donchian_swing-monitor-bought-today-${DC_CAND}`)).toHaveTextContent('오늘 매수함')
  })

  it('후보 표 — bought_today 에 없는 종목은 배지가 없다', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => { m.donchian_swing.bought_today = []; m.donchian_swing.sold_today = [] },
    })
    expect(screen.queryByTestId(`donchian_swing-monitor-bought-today-${DC_CAND}`)).toBeNull()
  })

  it('보유 표 — bought_today 에 보유 종목이 들어 있으면(오늘 매수) 배지', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => { m.donchian_swing.bought_today = [DC_HELD]; m.donchian_swing.sold_today = [] },
    })
    expect(screen.getByTestId(`donchian_swing-monitor-bought-today-${DC_HELD}`)).toHaveTextContent('오늘 매수함')
  })

  it('etf 후보 표 — sold_today 에 든 종목에 「오늘 매도함」 배지 + 당일 재매수 막힘 안내', () => {
    renderPanel('etf_trend', {
      monitor: (m) => { m.etf_trend.bought_today = []; m.etf_trend.sold_today = [ETF_A] },
    })
    const badge = screen.getByTestId(`etf_trend-monitor-sold-today-${ETF_A}`)
    expect(badge).toHaveTextContent('오늘 매도함')
    expect(badge.getAttribute('title')).toMatch(/당일 재매수 막힘/)
  })

  it('bought_today 가 null(라우트 결측)이면 배지를 내지 않는다(예외 없이)', () => {
    expect(() => renderPanel('etf_trend', {
      monitor: (m) => { m.etf_trend.bought_today = null; m.etf_trend.sold_today = null },
    })).not.toThrow()
    expect(screen.queryByTestId(`etf_trend-monitor-bought-today-${ETF_HELD}`)).toBeNull()
  })
})
