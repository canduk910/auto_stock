/**
 * cycle411 2차 보완 Red B3 — 실적 카드가 세후 칸 `null`(비용 조회 실패)을 견딘다.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」 B3.
 * 백엔드는 비용 조회가 실패하면 세후 칸을 **`null`** 로 보낸다(B2·B4 — 세전 값을 세후 칸에 담지 않는다).
 * 화면은 `!== undefined` 가 아니라 `!= null` 로 거르고, 세전 값으로 폴백하되 그 자리에 「세전」 을 단다.
 *
 *  - PC1: summary `net_total_profit_rate`·`net_avg_daily_profit_rate` = null → 흰 화면 금지 ·
 *         세전 값(0.33% · 0.08%) + 그 카드에 「세전」.
 *  - PC2: TE `realized_net_sum_krw` = null → 실현 칸은 「0원」 이 아니라 세전 `realized_sum_krw` + 그 행에 「세전」.
 *  - PC3 (가드): 세후 칸이 있으면 카드·행에 「세전」 을 달지 않는다(항상 붙이는 구현 차단).
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
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

const TE_ROW = {
  strategy_id: 'momentum',
  n: 20,
  win: 15,
  loss: 5,
  even: 0,
  win_rate: 0.75,
  avg_win_pct: 0.1,
  avg_loss_pct: -1.0,
  te_pct: -0.175,
  te_krw_avg: -1225,
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

function setup(summary: Record<string, unknown>, te: Record<string, unknown>) {
  server.use(
    http.get('/api/performance/summary', () => HttpResponse.json(wrap(summary))),
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

describe('cycle411c — PerformanceCard 세후 칸 null', () => {
  it('PC1: summary net null → 세전 값 + 「세전」 (흰 화면 금지)', async () => {
    setup({ ...SUMMARY, net_total_profit_rate: null, net_avg_daily_profit_rate: null }, TE_ROW)
    const total = await screen.findByTestId('performance-metric-total-return')
    expect(total.textContent).toContain('0.33%')
    expect(total.parentElement?.textContent ?? '').toContain('세전')
    const avg = screen.getByTestId('performance-metric-avg-daily-return')
    expect(avg.textContent).toContain('0.08%')
    expect(avg.parentElement?.textContent ?? '').toContain('세전')
  })

  it('PC2: TE realized_net_sum_krw null → 세전 실현 + 「세전」 (「0원」 금지)', async () => {
    setup(SUMMARY, { ...TE_ROW, realized_net_sum_krw: null, fee_sum: null, tax_sum: null })
    const cell = await screen.findByTestId('realized-pnl-momentum')
    expect(cell.textContent).toContain('-24,500')
    expect(cell.textContent).not.toMatch(/^\+?0원$/)
    expect(screen.getByTestId('realized-row-momentum').textContent).toContain('세전')
  })

  it('PC3 (가드): 세후 칸이 있으면 「세전」 을 달지 않는다', async () => {
    setup(SUMMARY, TE_ROW)
    const total = await screen.findByTestId('performance-metric-total-return')
    expect(total.textContent).toContain('0.29%')
    expect(total.parentElement?.textContent ?? '').not.toContain('세전')
    const cell = await screen.findByTestId('realized-pnl-momentum')
    expect(cell.textContent).toContain('-92,000')
    expect(screen.getByTestId('realized-row-momentum').textContent).not.toContain('세전')
  })
})
