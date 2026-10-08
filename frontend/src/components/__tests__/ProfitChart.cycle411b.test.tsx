/**
 * cycle411 보완 Red M4 — 「모름」 ≠ 0: net 칸이 null 이면 세전으로 폴백하고 「세후」 라벨을 달지 않는다.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 M4.
 * 백엔드는 비용 조회가 실패하면 `/api/performance/daily` 의 net 칸을 **null** 로 싣는다(키는 있다).
 *
 *  - PCB1: net 칸이 null 이면 세후 모드여도 `daily_profit_rate`·`cumulative_return_rate` 를 그린다.
 *  - PCB2: 그때 제목은 실제로 그린 기준(`세전`)을 말한다 — `세후` 라벨 금지.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import ProfitChart from '../ProfitChart'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const ROWS = [
  {
    date: '2026-10-07',
    total_asset: 10_030_000,
    daily_profit_rate: 0.3,
    cumulative_return_rate: 0.3,
    daily_realized_pnl: 30_000,
    net_external_cashflow: 0,
    deposit: 0,
    daily_fee: null,
    daily_tax: null,
    daily_net_pnl: null,
    net_daily_profit_rate: null,
    net_cumulative_return_rate: null,
    cost_status: null,
  },
]

function installStorage(): void {
  let store: Record<string, string> = {}
  const mock = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => void (store[k] = String(v)),
    removeItem: (k: string) => void delete store[k],
    clear: () => void (store = {}),
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  } as unknown as Storage
  Object.defineProperty(window, 'localStorage', { value: mock, configurable: true, writable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: mock, configurable: true, writable: true })
}

beforeEach(() => installStorage())

describe('cycle411b — ProfitChart net null 폴백', () => {
  it('PCB1·PCB2: 세후 모드 + net null → 세전 시리즈 · 세전 라벨', async () => {
    server.use(http.get('/api/performance/daily', () => HttpResponse.json(wrap(ROWS))))
    render(
      <TestProviders>
        <ProfitChart selectedStrategy="all" />
      </TestProviders>,
    )
    await waitFor(() => expect(screen.getByTestId('profit-chart-daily')).toBeInTheDocument())
    expect(screen.getByTestId('profit-chart-daily').getAttribute('data-series')).toBe('daily_profit_rate')
    expect(screen.getByTestId('profit-chart-cumulative').getAttribute('data-series')).toBe(
      'cumulative_return_rate',
    )
    const dailyTitle = screen.getByText(/당일 수익률/).textContent ?? ''
    const cumTitle = screen.getByText(/누적 수익률/).textContent ?? ''
    expect(dailyTitle).not.toContain('세후')
    expect(cumTitle).not.toContain('세후')
    expect(dailyTitle).toContain('세전')
    expect(cumTitle).toContain('세전')
  })
})
