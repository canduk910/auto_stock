/**
 * cycle411 Red — 주문처리 현황에 「오늘 실현 순손익(추정)」 (사용자 결정 10-08 Q1·Q3).
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` — 새 `GET /api/costs/today?strategy=`
 * (당일 체결 × 추정 요율, scheduler 무접촉 경로).
 *
 * 계약
 *  - OM1: 전체 탭 = `/api/costs/today`(strategy 없음)의 `total.net_pnl` 을 testid `order-monitor-net-pnl` 에 보인다.
 *  - OM2: `cost_status` 가 `estimated`·`mixed` 면 같은 자리에 `추정` 배지.
 *  - OM3: 전략 탭 = `strategy=<id>` 로 조회하고 그 값을 보인다.
 *  - OM4: 비용 조회 실패여도 기존 「실현 손익」(세전, `daily_realized_pnl`)은 그대로 보인다.
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
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
    weight: 0.5,
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

function today(total: Record<string, number>, strategies: Array<Record<string, unknown>>, status = 'estimated') {
  return {
    date: '2026-10-08',
    fee_rate: 0.00142,
    tax_rate: 0.00199,
    rate_source: 'default',
    cost_status: status,
    strategies,
    total,
  }
}

function setup(selectedStrategy: string, costs: (url: URL) => Response) {
  server.use(
    http.get('/api/trading/status', () =>
      HttpResponse.json(
        wrap({
          is_running: true,
          env: 'vts',
          board: 'main',
          strategies: { momentum: strat(1000), volatility_breakout: strat(-500) },
        }),
      ),
    ),
    http.get('/api/costs/today', ({ request }) => costs(new URL(request.url))),
  )
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <OrderMonitor selectedStrategy={selectedStrategy} />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

describe('cycle411 — OrderMonitor 오늘 실현 순손익(추정)', () => {
  it('OM1·OM2: 전체 탭 = total.net_pnl + 추정 배지', async () => {
    setup('all', () =>
      HttpResponse.json(
        wrap(
          today({ gross_pnl: 500, fee: 427, tax: 400, net_pnl: -327 }, [
            { strategy: 'momentum', gross_pnl: 1000, fee: 285, tax: 201, net_pnl: 514 },
            { strategy: 'volatility_breakout', gross_pnl: -500, fee: 142, tax: 199, net_pnl: -841 },
          ]),
        ),
      ) as unknown as Response,
    )
    const cell = await screen.findByTestId('order-monitor-net-pnl')
    await waitFor(() => expect(cell.textContent).toContain('-327'))
    expect(within(cell).getByText('추정')).toBeInTheDocument()
  })

  it('OM3: 전략 탭은 strategy= 로 조회한다', async () => {
    const seen: string[] = []
    setup('momentum', (url) => {
      seen.push(url.searchParams.get('strategy') ?? '')
      return HttpResponse.json(
        wrap(
          today({ gross_pnl: 1000, fee: 285, tax: 201, net_pnl: 514 }, [
            { strategy: 'momentum', gross_pnl: 1000, fee: 285, tax: 201, net_pnl: 514 },
          ]),
        ),
      ) as unknown as Response
    })
    const cell = await screen.findByTestId('order-monitor-net-pnl')
    await waitFor(() => expect(cell.textContent).toContain('514'))
    expect(seen).toContain('momentum')
  })

  it('OM4: 비용 조회 실패여도 기존 실현 손익(세전)은 그대로', async () => {
    setup('all', () => new HttpResponse(null, { status: 500 }) as unknown as Response)
    await waitFor(() => expect(screen.getByText(/실현 손익/).textContent).toContain('500'))
  })
})
