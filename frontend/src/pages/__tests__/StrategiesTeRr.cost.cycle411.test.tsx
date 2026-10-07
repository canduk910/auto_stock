/**
 * cycle411 Red — 전략 카드 「3개월 실현」 을 순손익(세후)으로 (사용자 결정 10-08 Q2·Q3).
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` — `/api/strategies/te` 의
 * 판정 지표는 이미 net 기준이고, 금액은 `realized_net_sum_krw`(세후) · `realized_sum_krw`(세전).
 *
 * 계약
 *  - ST1: `te-realized-<id>` 는 `realized_net_sum_krw` 를 보인다(세후 기본).
 *  - ST2: `realized_net_sum_krw` 가 없는 응답(구 서버)은 `realized_sum_krw` 를 보인다.
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
}

function setup(te: unknown[]) {
  server.use(
    http.get('*/api/strategies', () => HttpResponse.json({ success: true, data: STRATEGIES, message: 'OK' })),
    http.get('*/api/strategies/te', () => HttpResponse.json({ success: true, data: te, message: 'OK' })),
  )
  render(withProviders(<Strategies />))
}

describe('cycle411 — Strategies 3개월 실현 = 세후', () => {
  it('ST1·ST2', async () => {
    setup([
      {
        ...BASE,
        strategy_id: 'momentum',
        realized_sum_krw: 120_000,
        realized_net_sum_krw: -12_500,
        te_pct_gross: 0.3,
        te_krw_avg_gross: 4800,
        win_rate_gross: 0.5,
        fee_sum: 80_000,
        tax_sum: 52_500,
      },
      { ...BASE, strategy_id: 'volatility_breakout', realized_sum_krw: 77_000 },
    ])
    await waitFor(() => expect(screen.getByTestId('te-realized-momentum')).toBeInTheDocument())
    expect(screen.getByTestId('te-realized-momentum').textContent).toContain('-12,500원')
    expect(screen.getByTestId('te-realized-momentum').textContent).not.toContain('120,000')
    expect(screen.getByTestId('te-realized-volatility_breakout').textContent).toContain('+77,000원')
  })
})
