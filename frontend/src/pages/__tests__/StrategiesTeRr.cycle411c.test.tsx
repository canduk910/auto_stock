/**
 * cycle411 2차 보완 Red — 전략 카드 「3개월 실현」 의 세후/세전 라벨 (F9 · B4).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」.
 *
 *  - SC1 (F9): 세후 값(`realized_net_sum_krw`)을 보일 때 같은 칸에 「세후」.
 *  - SC2 (B4): 비용 조회 실패로 `realized_net_sum_krw: null` 이면 세전(`realized_sum_krw`)을 보이고 「세전」 —
 *              라벨 없이 세전 숫자를 세후처럼 그리던 결함(momentum 「-10,706원·열위」 → 「+41,600원·우위」).
 */

import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import Strategies from '../Strategies'
import { server } from '../../test/server'

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const STRATEGIES = {
  strategies: [
    {
      key: 'momentum',
      name: '상한가 모멘텀',
      weight: 0.5,
      enabled: true,
      total_investment: 10_000_000,
      params: { stop_loss_rate: -7.5, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.25 },
    },
    {
      key: 'volatility_breakout',
      name: '변동성 돌파',
      weight: 0.5,
      enabled: true,
      total_investment: 10_000_000,
      params: { stop_loss_rate: -3.0, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.25 },
    },
  ],
}

const BASE = {
  n: 25,
  win: 10,
  loss: 15,
  even: 0,
  win_rate: 0.4,
  avg_win_pct: 2.0,
  avg_loss_pct: -1.2,
  te_pct: -0.1,
  te_krw_avg: -500,
  rr: 1.6,
  required_rr: 1.5,
  rr_margin: 0.1,
  rr_available: true,
  sample_tier: 'low',
  verdict: 'inferior',
  structure_tag: 'robust',
  single_trade_dominant: false,
  te_pct_gross: 0.3,
  te_krw_avg_gross: 4800,
  win_rate_gross: 0.5,
}

function setup(te: unknown[]) {
  server.use(
    http.get('*/api/strategies', () => HttpResponse.json({ success: true, data: STRATEGIES, message: 'OK' })),
    http.get('*/api/strategies/te', () => HttpResponse.json({ success: true, data: te, message: 'OK' })),
  )
  render(withProviders(<Strategies />))
}

describe('cycle411c — Strategies 3개월 실현 라벨', () => {
  it('SC1 (F9): 세후 값에는 「세후」', async () => {
    setup([
      { ...BASE, strategy_id: 'momentum', realized_sum_krw: 120_000, realized_net_sum_krw: -12_500, fee_sum: 80_000, tax_sum: 52_500 },
      { ...BASE, strategy_id: 'volatility_breakout', realized_sum_krw: 77_000, realized_net_sum_krw: 70_000, fee_sum: 4_000, tax_sum: 3_000 },
    ])
    await waitFor(() => expect(screen.getByTestId('te-realized-momentum')).toBeInTheDocument())
    const cell = screen.getByTestId('te-realized-momentum').textContent ?? ''
    expect(cell).toContain('-12,500원')
    expect(cell).toContain('세후')
    expect(cell).not.toContain('세전')
  })

  it('SC2 (B4): realized_net_sum_krw null → 세전 값 + 「세전」', async () => {
    setup([
      { ...BASE, strategy_id: 'momentum', realized_sum_krw: 41_600, realized_net_sum_krw: null, fee_sum: null, tax_sum: null },
      { ...BASE, strategy_id: 'volatility_breakout', realized_sum_krw: 77_000, realized_net_sum_krw: 70_000, fee_sum: 4_000, tax_sum: 3_000 },
    ])
    await waitFor(() => expect(screen.getByTestId('te-realized-momentum')).toBeInTheDocument())
    const cell = screen.getByTestId('te-realized-momentum').textContent ?? ''
    expect(cell).toContain('+41,600원')
    expect(cell).toContain('세전')
    expect(cell).not.toContain('세후')
  })
})
