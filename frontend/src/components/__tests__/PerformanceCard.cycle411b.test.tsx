/**
 * cycle411 보완 Red M5 — 세전 모드의 승률·승/패는 세전 값 (메인 세션 결정 10-08 「보완 결정」).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 M5.
 *
 *  - PB1: 세후(기본) = `win_rate`·`win`·`loss`(판정 = 세후).
 *  - PB2: 세전 = `win_rate_gross`·`win_gross`·`loss_gross` — 세전 손익 옆에 세후 승/패를 붙이지 않는다.
 *  - PB3: `*_gross` 가 없는 구 응답은 세전 모드에서도 기존 값을 보인다(NaN·undefined 금지).
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import PerformanceCard from '../PerformanceCard'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const SUMMARY = {
  total_days: 4,
  total_profit_rate: 0.33,
  avg_daily_profit_rate: 0.08,
  latest_asset: 10_033_000,
  strategy: 'total',
  net_total_profit_rate: 0.29,
  net_avg_daily_profit_rate: 0.07,
}

// 세전으로는 15승 5패(75%), 세후로는 0승 20패
const TE_ROW = {
  strategy_id: 'momentum',
  n: 20,
  win: 0,
  loss: 20,
  even: 0,
  win_rate: 0,
  avg_win_pct: 0,
  avg_loss_pct: -0.6,
  te_pct: -0.6,
  te_krw_avg: -4600,
  realized_sum_krw: -24_500,
  rr: null,
  required_rr: 1.5,
  rr_margin: null,
  rr_available: false,
  sample_tier: 'low',
  verdict: 'inferior',
  structure_tag: 'robust',
  single_trade_dominant: false,
  te_pct_gross: -0.175,
  te_krw_avg_gross: -1225,
  win_rate_gross: 0.75,
  win_gross: 15,
  loss_gross: 5,
  realized_net_sum_krw: -92_000,
  fee_sum: 39_200,
  tax_sum: 28_000,
}

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

function setup(te: Record<string, unknown>) {
  server.use(
    http.get('/api/performance/summary', () => HttpResponse.json(wrap(SUMMARY))),
    http.get('/api/strategies/te', () => HttpResponse.json(wrap([te]))),
  )
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <PerformanceCard selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

async function toGross() {
  await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByRole('button', { name: '세전' }))
}

describe('cycle411b — PerformanceCard 세전 승률·승/패', () => {
  it('PB1: 세후(기본) = 세후 승률·승/패', async () => {
    setup(TE_ROW)
    const cell = await screen.findByTestId('realized-winrate-momentum')
    expect(cell.textContent).toContain('승률 0%')
    expect(cell.textContent).toContain('승0/패20')
  })

  it('PB2: 세전 = win_rate_gross·win_gross·loss_gross', async () => {
    setup(TE_ROW)
    await screen.findByTestId('realized-winrate-momentum')
    await toGross()
    await waitFor(() =>
      expect(screen.getByTestId('realized-winrate-momentum').textContent).toContain('승률 75%'),
    )
    expect(screen.getByTestId('realized-winrate-momentum').textContent).toContain('승15/패5')
  })

  it('PB3: *_gross 없는 구 응답은 세전에서도 기존 값', async () => {
    const legacy: Record<string, unknown> = { ...TE_ROW }
    delete legacy.win_rate_gross
    delete legacy.win_gross
    delete legacy.loss_gross
    setup(legacy)
    await screen.findByTestId('realized-winrate-momentum')
    await toGross()
    const text = screen.getByTestId('realized-winrate-momentum').textContent ?? ''
    expect(text).toContain('승0/패20')
    expect(text).not.toContain('NaN')
    expect(text).not.toContain('undefined')
  })
})
