/**
 * cycle418-M Red — KojiroMonitor L11.
 *
 * 1. 보유 방어선 표의 "2ATR 하드"·"2.5ATR 트레일" 머리글이 고정 글자다 — 운영 params(`stop_atr`·
 *    `trail_atr`)가 다른 값이어도 화면은 늘 "2ATR"·"2.5ATR" 로 보인다.
 * 2. 본전 승격(`breakeven_promote_atr`, 운영값 1.5)이 어디에도 안 보인다.
 * 3. params 가 비어 있으면(`{}`) 화면이 기본값(2.0·2.5·-8.0)으로 채워 실제 설정처럼 보인다 —
 *    「모름」을 숫자로 둔갑시키지 않는다(루트 CLAUDE.md 원칙).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import KojiroMonitor from '../KojiroMonitor'
import type { StrategyInfo } from '../../types/trading'

function makeKojiro(params: Record<string, unknown>): Record<string, StrategyInfo> {
  const base: StrategyInfo = {
    name: '고지로 대순환', enabled: true, weight: 0.3, positions: 0, pending_buys: 0,
    position_tickers: [], total_investment: 0, daily_realized_pnl: 0, buy_disabled: false,
    buy_signals: [], positions_detail: {}, pending_buy_tickers: [], scanned_count: 0,
    scanned_tickers: [], targets: {}, scan_stats: null,
    params,
  }
  return { kojiro: base }
}

describe('KojiroMonitor L11 — ATR 배수·본전 승격·params 결측', () => {
  it('운영값이 3.0/4.0 이면 머리글도 3ATR·4ATR(고정 "2ATR"·"2.5ATR" 금지)', () => {
    render(<KojiroMonitor strategies={makeKojiro({ stop_atr: 3.0, trail_atr: 4.0, hard_stop_pct: -8.0 })} />)
    const panel = screen.getByTestId('kojiro-defense-panel')
    expect(panel.textContent).toMatch(/3ATR/)
    expect(panel.textContent).toMatch(/4ATR/)
    expect(panel.textContent).not.toMatch(/2ATR 하드/)
    expect(panel.textContent).not.toMatch(/2\.5ATR 트레일/)
  })

  it('breakeven_promote_atr > 0 이면 본전 승격 조건을 subtitle 에 밝힌다', () => {
    render(<KojiroMonitor strategies={makeKojiro({ stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0, breakeven_promote_atr: 1.5 })} />)
    const panel = screen.getByTestId('kojiro-defense-panel')
    expect(panel.textContent).toMatch(/본전/)
    expect(panel.textContent).toMatch(/1\.5/)
  })

  it('breakeven_promote_atr 가 0(비활성)이면 본전 승격 문구를 달지 않는다', () => {
    render(<KojiroMonitor strategies={makeKojiro({ stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0, breakeven_promote_atr: 0 })} />)
    expect(screen.getByTestId('kojiro-defense-panel').textContent).not.toMatch(/본전/)
  })

  it('params 가 비어 있으면(결측) 기본값(2.0·2.5·-8.0)으로 채우지 않고 「—」', () => {
    render(<KojiroMonitor strategies={makeKojiro({})} />)
    const panel = screen.getByTestId('kojiro-defense-panel')
    expect(panel.textContent).not.toMatch(/2ATR 하드/)
    expect(panel.textContent).not.toMatch(/2\.5ATR 트레일/)
    expect(panel.textContent).toMatch(/—ATR/)
  })
})
