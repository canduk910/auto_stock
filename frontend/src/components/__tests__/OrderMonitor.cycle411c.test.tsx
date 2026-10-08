/**
 * cycle411 2차 보완 Red — 주문처리 현황 오늘 순손익: 실패 표시 · 재시도 · 라벨 (F7 · F10).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」.
 *
 *  - OC1 (F7): `/api/costs/today` 가 실패하면 순손익 자리(`order-monitor-net-pnl`)에 「—」 +
 *              오류 표시(`order-monitor-net-pnl-error`, 문구 「조회 실패」 — 「실현 손익」 을 담지 않는다:
 *              OM4 의 `getByText(/실현 손익/)` 와 겹치면 안 된다).
 *  - OC2 (F7): 한 번 성공한 뒤 실패하면 **마지막 성공값을 남기지 않는다** — 「—」 로 바뀐다.
 *  - OC3 (F7): 실패는 다시 시도하지 않는다(`retry: 0`) — 5초 폴링이 다음 시도다
 *              (재시도 1회 × 5초 = 분당 24건 WARNING 이 쌓이던 결함).
 *  - OC4 (F10): 머리줄에 「추정」 은 한 번만(라벨 「(추정)」 + 배지 「추정」 중복 금지) ·
 *              제목 「주문처리 현황」 은 `whitespace-nowrap`(400px 에서 두 줄로 꺾이던 결함).
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

function today(net: number, status = 'estimated') {
  return {
    date: '2026-10-07',
    fee_rate: 0.00142,
    tax_rate: 0.00199,
    rate_source: 'default',
    cost_status: status,
    strategies: [{ strategy: 'momentum', gross_pnl: 0, fee: 0, tax: 0, net_pnl: net }],
    total: { gross_pnl: 0, fee: 0, tax: 0, net_pnl: net },
  }
}

/** `costs` 가 n 번째(0부터) 호출의 응답을 정한다 — 숫자 = 그 순손익으로 성공, null = 500. */
function setup(costs: (n: number) => number | null) {
  const calls = { costs: 0 }
  server.use(
    http.get('/api/trading/status', () =>
      HttpResponse.json(
        wrap({ is_running: true, env: 'vts', board: 'main', strategies: { momentum: strat(500) } }),
      ),
    ),
    http.get('/api/costs/today', () => {
      const v = costs(calls.costs)
      calls.costs += 1
      return v === null
        ? (new HttpResponse(null, { status: 500 }) as unknown as Response)
        : HttpResponse.json(wrap(today(v)))
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

describe('cycle411c — OrderMonitor 오늘 순손익', () => {
  it('OC1 (F7): 조회 실패 → 「—」 + 오류 표시', async () => {
    setup(() => null)
    const err = await screen.findByTestId('order-monitor-net-pnl-error', {}, { timeout: 2000 })
    expect(err.textContent).toContain('조회 실패')
    expect(err.textContent).not.toMatch(/실현 손익/)
    expect(screen.getByTestId('order-monitor-net-pnl').textContent).toContain('—')
  })

  it('OC2 (F7): 성공 뒤 실패하면 마지막 성공값을 남기지 않는다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setup((n) => (n === 0 ? -1234 : null))
    await waitFor(() =>
      expect(screen.getByTestId('order-monitor-net-pnl').textContent).toContain('-1,234'),
    )
    await vi.advanceTimersByTimeAsync(5_500)
    await waitFor(() =>
      expect(screen.getByTestId('order-monitor-net-pnl').textContent).toContain('—'),
    )
    expect(screen.getByTestId('order-monitor-net-pnl').textContent).not.toContain('1,234')
    expect(screen.getByTestId('order-monitor-net-pnl-error')).toBeInTheDocument()
  })

  it('OC3 (F7): 실패는 재시도하지 않는다 — 다음 시도는 5초 폴링', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const calls = setup(() => null)
    await waitFor(() => expect(calls.costs).toBe(1))
    await vi.advanceTimersByTimeAsync(2_500)
    expect(calls.costs).toBe(1)
  })

  it('OC4 (F10): 「추정」 한 번 · 제목 nowrap', async () => {
    setup(() => -327)
    await waitFor(() =>
      expect(screen.getByTestId('order-monitor-net-pnl').textContent).toContain('-327'),
    )
    const title = screen.getByText('주문처리 현황')
    expect(title.className).toContain('whitespace-nowrap')
    const header = title.parentElement as HTMLElement
    const count = (header.textContent ?? '').split('추정').length - 1
    expect(count).toBe(1)
  })
})
