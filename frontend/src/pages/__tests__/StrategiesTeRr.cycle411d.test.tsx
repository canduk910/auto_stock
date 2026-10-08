/**
 * cycle411 3차 검증 후 LOW 결함 — 판정 배지·TE·승률이 세전 기준일 때 배지 옆 「세전」 표시.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md`.
 *
 * cycle411c(F9·B4) 가 「3개월 실현」 칸에만 세후/세전 라벨을 달았다. 그러나 비용 조회
 * 실패(`realized_net_sum_krw: null`)면 `te_pct`·`win`·`loss`·`verdict` 판정 자체도
 * `te_pct_gross`·`win_gross`·`loss_gross`·`verdict_gross` 와 같은 세전 값으로 **자동
 * 폴백**된다(`compute_te_rr` — net 칸이 없는 페어는 세전으로 떨어진다, 계약 B4). 그런데
 * 판정 배지(`te-verdict-<id>`)·TE 값(`te-value-<id>`) 옆에는 그 사실이 보이지 않아
 * 「우위/열위」 가 세후 기준이라고 오인할 수 있었다.
 *
 *  - SD1: `realized_net_sum_krw: null`(비용 조회 실패) → 배지 옆 `te-pretax-<id>` = 「세전」.
 *  - SD2: `realized_net_sum_krw` 가 숫자(세후 가용) → `te-pretax-<id>` 자체가 없다
 *         (PC3 와 같은 규약 — 세후 값이 있으면 세전 라벨을 달지 않는다).
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
  ],
}

const BASE = {
  strategy_id: 'momentum',
  n: 25,
  win: 10,
  loss: 15,
  even: 0,
  win_rate: 0.4,
  avg_win_pct: 2.0,
  avg_loss_pct: -1.2,
  te_pct: -0.1,
  te_krw_avg: -500,
  realized_sum_krw: 41_600,
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
  win_gross: 12,
  loss_gross: 13,
}

function setup(te: unknown[]) {
  server.use(
    http.get('*/api/strategies', () => HttpResponse.json({ success: true, data: STRATEGIES, message: 'OK' })),
    http.get('*/api/strategies/te', () => HttpResponse.json({ success: true, data: te, message: 'OK' })),
  )
  render(withProviders(<Strategies />))
}

describe('cycle411d — Strategies 판정 배지 옆 세전 표시', () => {
  it('SD1: realized_net_sum_krw null(비용 조회 실패) → te-pretax-momentum = 세전', async () => {
    setup([{ ...BASE, realized_net_sum_krw: null, fee_sum: null, tax_sum: null }])
    await waitFor(() => expect(screen.getByTestId('te-verdict-momentum')).toBeInTheDocument())
    const tag = await screen.findByTestId('te-pretax-momentum')
    expect(tag.textContent).toContain('세전')
  })

  it('SD2: realized_net_sum_krw 가 숫자(세후 가용) → te-pretax-momentum 없음', async () => {
    setup([{ ...BASE, realized_net_sum_krw: -12_500, fee_sum: 80_000, tax_sum: 52_500 }])
    await waitFor(() => expect(screen.getByTestId('te-verdict-momentum')).toBeInTheDocument())
    expect(screen.queryByTestId('te-pretax-momentum')).toBeNull()
  })
})
