/**
 * cycle411 Red — ProfitChart 세후 기본 + 세전 토글 (사용자 결정 10-08 Q3).
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md`.
 *
 * 계약
 *  - PC1: 차트 머리에 지금 기준이 보인다 — 기본 「세후」(제목에 `세후` 포함), 토글 `세전` 을 누르면 `세전`.
 *  - PC2: 세후일 때 막대·선은 `net_daily_profit_rate`·`net_cumulative_return_rate` 를, 세전일 때
 *         `daily_profit_rate`·`cumulative_return_rate` 를 그린다 — jsdom 에서는 SVG 가 그려지지 않으므로
 *         차트 컨테이너의 `data-series` 속성(그리는 dataKey 를 `,` 로 이은 문자열)으로 확인한다.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    daily_fee: 285,
    daily_tax: 2448,
    daily_net_pnl: 27_267,
    net_daily_profit_rate: 0.27267,
    net_cumulative_return_rate: 0.27166,
    cost_status: 'settled',
  },
]

function renderChart() {
  server.use(http.get('/api/performance/daily', () => HttpResponse.json(wrap(ROWS))))
  return render(
    <TestProviders>
      <ProfitChart selectedStrategy="all" />
    </TestProviders>,
  )
}


/**
 * 결정론적 in-memory localStorage — Node 25 실험 localStorage 글로벌이 jsdom Storage 를 가려
 * `setItem`/`clear` 가 없는 환경 대응(`src/__tests__/ContentWidthSlider.test.tsx` 와 같은 방식).
 */
function installStorage(throwing = false): Storage {
  let store: Record<string, string> = {}
  const boom = () => {
    throw new Error('blocked')
  }
  const mock = {
    getItem: (k: string) => (throwing ? boom() : k in store ? store[k] : null),
    setItem: (k: string, v: string) => (throwing ? boom() : void (store[k] = String(v))),
    removeItem: (k: string) => void delete store[k],
    clear: () => void (store = {}),
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  } as unknown as Storage
  Object.defineProperty(window, 'localStorage', { value: mock, configurable: true, writable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: mock, configurable: true, writable: true })
  return mock
}

beforeEach(() => {
  installStorage()
})

describe('cycle411 — ProfitChart 세후/세전', () => {
  it('PC1·PC2: 기본은 세후 — 제목과 그리는 시리즈', async () => {
    renderChart()
    await waitFor(() => expect(screen.getByTestId('profit-chart-daily')).toBeInTheDocument())
    expect(screen.getByText(/당일 수익률/).textContent).toContain('세후')
    expect(screen.getByText(/누적 수익률/).textContent).toContain('세후')
    expect(screen.getByTestId('profit-chart-daily').getAttribute('data-series')).toBe('net_daily_profit_rate')
    expect(screen.getByTestId('profit-chart-cumulative').getAttribute('data-series')).toBe(
      'net_cumulative_return_rate',
    )
  })

  it('PC1·PC2: 세전을 누르면 기존 시리즈', async () => {
    renderChart()
    await waitFor(() => expect(screen.getByTestId('profit-chart-daily')).toBeInTheDocument())
    await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByRole('button', { name: '세전' }))
    await waitFor(() =>
      expect(screen.getByTestId('profit-chart-daily').getAttribute('data-series')).toBe('daily_profit_rate'),
    )
    expect(screen.getByTestId('profit-chart-cumulative').getAttribute('data-series')).toBe(
      'cumulative_return_rate',
    )
    expect(screen.getByText(/당일 수익률/).textContent).toContain('세전')
  })
})
