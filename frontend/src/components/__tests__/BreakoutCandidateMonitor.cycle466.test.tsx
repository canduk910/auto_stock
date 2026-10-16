/**
 * cycle466 — 돌파 후보 화면의 「미구독」 과 「구독 중 시세 없음」 분리.
 *
 * 배경: 배너가 구독 안 된 종목을 「시세 미수신」 이라 불렀고, 구독은 됐는데 시세가 한 번도
 * 오지 않은 종목은 배너에 잡히지 않았다(09-11 wt280 검토에서 발견). 두 경우 모두 매수 신호
 * 평가가 일어나지 않으므로 둘 다 경고로 보여야 한다.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import BreakoutCandidateMonitor from '../BreakoutCandidateMonitor'
import type { BreakoutDiagTarget, StrategyInfo, TickerPrice } from '../../types/trading'

function makeStrategy(tickers: string[]): Record<string, StrategyInfo> {
  const targets: Record<string, BreakoutDiagTarget> = {}
  for (const t of tickers) {
    targets[t] = {
      prev_close: 0, atr14: 0, stop_line: 0, volume_threshold: 0,
      bought_today: false, in_cooldown: false, target_price: 10000,
    }
  }
  return {
    bull_flag_breakout: {
      name: '눌림목 돌파', enabled: true, weight: 0.1, positions: 0, pending_buys: 0,
      position_tickers: [], total_investment: 1_000_000, daily_realized_pnl: 0,
      buy_disabled: false, buy_signals: [], positions_detail: {}, pending_buy_tickers: [],
      scanned_count: tickers.length, scanned_tickers: tickers, targets, scan_stats: {}, params: {},
    },
  }
}

function price(p: number): TickerPrice {
  return { current_price: p, open_price: p, change_rate: 0, prdy_ctrt: 0 }
}

describe('cycle466 — 구독 커버리지 배너', () => {
  it('미구독은 「미구독」 으로 센다 — 「시세 미수신」 이라 부르지 않는다', () => {
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={makeStrategy(['005930', '000660'])}
        subscribedTickers={['005930']}
        tickerPrices={{ '005930': price(10100) }}
      />,
    )
    const banner = screen.getByTestId('breakout-subscription-coverage')
    expect(banner.textContent).toContain('후보 2종목 중 1종목 구독 · 1종목 미구독')
    expect(banner.textContent).not.toContain('시세 미수신')
    expect(banner.className).toMatch(/amber/)
  })

  it('구독 중인데 시세가 없는 종목을 따로 세고 경고한다', () => {
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={makeStrategy(['005930', '000660'])}
        subscribedTickers={['005930', '000660']}
        tickerPrices={{ '005930': price(10100) }}
      />,
    )
    const banner = screen.getByTestId('breakout-subscription-coverage')
    expect(banner.textContent).toContain('후보 2종목 중 2종목 구독 · 0종목 미구독 · 1종목 구독 중 시세 없음')
    expect(banner.className).toMatch(/amber/)
    expect(screen.getByTestId('breakout-status-000660').textContent).toContain('시세 없음')
    expect(screen.getByTestId('breakout-status-005930').textContent).not.toContain('시세 없음')
  })

  it('현재가 0 도 시세 없음이다', () => {
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={makeStrategy(['005930'])}
        subscribedTickers={['005930']}
        tickerPrices={{ '005930': price(0) }}
      />,
    )
    expect(screen.getByTestId('breakout-subscription-coverage').textContent).toContain('1종목 구독 중 시세 없음')
  })

  it('전부 구독 + 전부 시세 있음 = 정상 톤, 시세 없음 문구 없음', () => {
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={makeStrategy(['005930'])}
        subscribedTickers={['005930']}
        tickerPrices={{ '005930': price(10100) }}
      />,
    )
    const banner = screen.getByTestId('breakout-subscription-coverage')
    expect(banner.className).toMatch(/emerald/)
    expect(banner.textContent).not.toContain('시세 없음')
  })

  it('미구독 종목 배지는 여전히 미구독이다(시세 없음보다 먼저)', () => {
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={makeStrategy(['000660'])}
        subscribedTickers={[]}
      />,
    )
    const badge = screen.getByTestId('breakout-status-000660').textContent
    expect(badge).toContain('미구독')
    expect(badge).not.toContain('시세 없음')
  })
})
