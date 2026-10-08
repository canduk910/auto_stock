/**
 * cycle411 보완 Red — 주문처리 현황 오늘 순손익 (메인 세션 결정 10-08 「보완 결정」 M6·L1).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」.
 *
 *  - OMB1 (M6): 오늘 순손익(`/api/costs/today`)은 세전 실현손익(`/api/trading/status`, 5초 폴링)과
 *               **같은 주기**로 갱신된다 — 한 번 읽고 멈추면 세전 숫자만 움직이고 순손익은 낡는다.
 *  - OMB2 (L1): 원 단위 표시는 정수 원(반올림) + 「원」 — 소수 꼬리 금지.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import OrderMonitor from '../OrderMonitor'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function strat(daily: number) {
  return {
    name: 'x',
    enabled: true,
    weight: 1,
    total_investment: 5_000_000,
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    pending_buy_tickers: [],
    positions_detail: {},
    buy_disabled: false,
    daily_realized_pnl: daily,
  }
}

function today(net: number) {
  return {
    date: '2026-10-07',
    fee_rate: 0.00142,
    tax_rate: 0.00199,
    rate_source: 'default',
    cost_status: 'estimated',
    strategies: [{ strategy: 'momentum', gross_pnl: 0, fee: 0, tax: 0, net_pnl: net }],
    total: { gross_pnl: 0, fee: 0, tax: 0, net_pnl: net },
  }
}

function setup(pnls: number[], nets: number[]) {
  let s = 0
  let c = 0
  const calls = { status: 0, costs: 0 }
  server.use(
    http.get('/api/trading/status', () => {
      calls.status += 1
      const v = pnls[Math.min(s++, pnls.length - 1)]
      return HttpResponse.json(
        wrap({ is_running: true, env: 'vts', board: 'main', strategies: { momentum: strat(v) } }),
      )
    }),
    http.get('/api/costs/today', () => {
      calls.costs += 1
      const v = nets[Math.min(c++, nets.length - 1)]
      return HttpResponse.json(wrap(today(v)))
    }),
  )
  render(
    <TestProviders>
      <TradingStatusProvider>
        <OrderMonitor selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
  return calls
}

afterEach(() => {
  vi.useRealTimers()
})

describe('cycle411b — OrderMonitor 오늘 순손익', () => {
  it('OMB1: 세전 실현손익 폴링 주기(5초)에 순손익도 다시 읽는다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const calls = setup([500, 1500], [-327, 673])
    await waitFor(() => expect(screen.getByTestId('order-monitor-net-pnl').textContent).toContain('-327'))
    await vi.advanceTimersByTimeAsync(5_500)
    await waitFor(() => expect(screen.getByText(/실현 손익/).textContent).toContain('1,500'))
    await waitFor(() => expect(screen.getByTestId('order-monitor-net-pnl').textContent).toContain('673'))
    expect(calls.costs).toBeGreaterThanOrEqual(2)
  })

  it('OMB2: 소수 원은 반올림 정수 + 원', async () => {
    setup([500], [-327.46])
    const cell = await screen.findByTestId('order-monitor-net-pnl')
    await waitFor(() => expect(cell.textContent).toContain('-327원'))
    expect(cell.textContent).not.toContain('.46')
  })
})
