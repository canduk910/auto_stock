/**
 * cycle414 보완 2차 Red — 재검증 N5(screens) 고지로 탭 잔여(H3 원칙).
 *
 * `StrategyMonitor`·`ScanMonitor` 둘 다 `KojiroMonitor` 를 그리면서 `running` 을 넘기지 않아,
 * 엔진 정지 중에도 「보유 종목 없음」·「매수 신호 없음」을 확정으로 그렸다.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import KojiroMonitor from '../KojiroMonitor'
import type { StrategyInfo } from '../../types/trading'

function makeKojiro(over: Partial<StrategyInfo> = {}): Record<string, StrategyInfo> {
  const base: StrategyInfo = {
    name: '고지로 대순환', enabled: true, weight: 0.3, positions: 0, pending_buys: 0,
    position_tickers: [], total_investment: 0, daily_realized_pnl: 0, buy_disabled: false,
    buy_signals: [], positions_detail: {}, pending_buy_tickers: [], scanned_count: 0,
    scanned_tickers: [], targets: {}, scan_stats: null,
    params: { stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0 },
    ...over,
  }
  return { kojiro: base }
}

describe('N5 — running=false 면 고지로 탭도 「엔진 정지」를 밝히고 보유·신호를 「모름」으로', () => {
  it('보유 0 + running=false → 「보유 종목 없음」이 아니라 「엔진 정지 — 보유 정보 모름」', () => {
    render(<KojiroMonitor strategies={makeKojiro()} running={false} />)
    expect(screen.getByTestId('kojiro-defense-panel').textContent).toMatch(/엔진 정지/)
    expect(screen.getByTestId('kojiro-defense-panel').textContent).not.toMatch(/^.*보유 종목 없음$/)
  })

  it('매수 신호 0 + running=false → 「매수 신호 없음」이 아니라 「엔진 정지 — 매수 신호 모름」', () => {
    render(<KojiroMonitor strategies={makeKojiro()} running={false} />)
    expect(screen.getByTestId('kojiro-entry-feed').textContent).toMatch(/엔진 정지/)
  })

  it('배너에 엔진 정지 표시가 뜬다', () => {
    render(<KojiroMonitor strategies={makeKojiro()} running={false} />)
    expect(screen.getByTestId('kojiro-engine-stopped')).toBeTruthy()
  })

  it('running=true(기본) 이면 평소대로 「보유 종목 없음」·「매수 신호 없음」', () => {
    render(<KojiroMonitor strategies={makeKojiro()} running={true} />)
    expect(screen.getByTestId('kojiro-defense-panel').textContent).toMatch(/보유 종목 없음/)
    expect(screen.getByTestId('kojiro-entry-feed').textContent).toMatch(/매수 신호 없음/)
    expect(screen.queryByTestId('kojiro-engine-stopped')).toBeNull()
  })

  it('running 생략(기본 undefined) — 기존 동작 그대로(회귀 없음)', () => {
    render(<KojiroMonitor strategies={makeKojiro()} />)
    expect(screen.getByTestId('kojiro-defense-panel').textContent).toMatch(/보유 종목 없음/)
    expect(screen.queryByTestId('kojiro-engine-stopped')).toBeNull()
  })
})
