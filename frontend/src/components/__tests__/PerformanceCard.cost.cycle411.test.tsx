/**
 * cycle411 Red — 실적 카드·차트 세후(net) 기본 + 세전(gross) 토글.
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q3).
 *
 * 계약
 *  - PN1: `/api/performance/summary` 에 `net_total_profit_rate`·`net_avg_daily_profit_rate` 가 있으면
 *         누적·일평균 수익률 카드는 기본으로 **세후** 값을 보인다.
 *  - PN2: 토글(testid `cost-basis-toggle` 안 버튼 `세후`/`세전`, `aria-pressed`)로 `세전` 을 누르면
 *         기존 `total_profit_rate`·`avg_daily_profit_rate` 를 보인다.
 *  - PN3: 선택은 localStorage `autostock.costBasis`(`net`|`gross`)에 기억한다 — 다시 열면 그 값으로 시작.
 *  - PN4: localStorage 가 예외를 던져도(사생활 모드·차단) 화면은 세후 기본으로 그린다.
 *  - PN5: net 칸이 없는 응답(구 서버)은 세전 값을 그대로 보인다(빈 칸·NaN 금지).
 *  - PN6: 실현 성과 행(`realized-pnl-*`)도 세후 기본 = `realized_net_sum_krw`, 세전 = `realized_sum_krw`.
 *  - PN7: 토글은 화면 공통 — 같은 화면의 ProfitChart 토글도 함께 바뀐다.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import PerformanceCard from '../PerformanceCard'
import ProfitChart from '../ProfitChart'
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
  n: 25,
  win: 10,
  loss: 15,
  even: 0,
  win_rate: 0.4,
  avg_win_pct: 2.0,
  avg_loss_pct: -1.2,
  te_pct: -0.1,
  te_krw_avg: -500,
  realized_sum_krw: 120_000,
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
  realized_net_sum_krw: -12_500,
  fee_sum: 80_000,
  tax_sum: 52_500,
}

function mockApis(summary: Record<string, unknown> = SUMMARY) {
  server.use(
    http.get('/api/performance/summary', () => HttpResponse.json(wrap(summary))),
    http.get('/api/strategies/te', () => HttpResponse.json(wrap([TE_ROW]))),
    http.get('/api/performance/daily', () => HttpResponse.json(wrap([]))),
  )
}

function renderCard() {
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <PerformanceCard selectedStrategy="all" />
      </TradingStatusProvider>
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

describe('cycle411 — PerformanceCard 세후 기본 + 세전 토글', () => {
  it('PN1: net 칸이 있으면 누적·일평균 카드는 세후 값을 보인다', async () => {
    mockApis()
    renderCard()
    await waitFor(() =>
      expect(screen.getByTestId('performance-metric-total-return').textContent).toContain('0.29%'),
    )
    expect(screen.getByTestId('performance-metric-avg-daily-return').textContent).toContain('0.07%')
    const toggle = screen.getByTestId('cost-basis-toggle')
    expect(within(toggle).getByRole('button', { name: '세후' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('PN2·PN3: 세전을 누르면 기존 값을 보이고 localStorage costBasis=gross 로 기억한다', async () => {
    mockApis()
    renderCard()
    await screen.findByTestId('cost-basis-toggle')
    await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByRole('button', { name: '세전' }))
    await waitFor(() =>
      expect(screen.getByTestId('performance-metric-total-return').textContent).toContain('0.33%'),
    )
    expect(screen.getByTestId('performance-metric-avg-daily-return').textContent).toContain('0.08%')
    expect(window.localStorage.getItem('autostock.costBasis')).toBe('gross')
  })

  it('PN3: localStorage 에 gross 가 있으면 세전으로 시작한다', async () => {
    window.localStorage.setItem('autostock.costBasis', 'gross')
    mockApis()
    renderCard()
    await waitFor(() =>
      expect(screen.getByTestId('performance-metric-total-return').textContent).toContain('0.33%'),
    )
  })

  it('PN4: localStorage 가 예외를 던져도 세후 기본으로 그린다', async () => {
    installStorage(true)
    mockApis()
    renderCard()
    await waitFor(() =>
      expect(screen.getByTestId('performance-metric-total-return').textContent).toContain('0.29%'),
    )
    await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByRole('button', { name: '세전' }))
    await waitFor(() =>
      expect(screen.getByTestId('performance-metric-total-return').textContent).toContain('0.33%'),
    )
  })

  it('PN5: net 칸이 없는 응답은 세전 값을 그대로 보인다', async () => {
    mockApis({ total_days: 4, total_profit_rate: 0.33, avg_daily_profit_rate: 0.08, latest_asset: 1 })
    renderCard()
    await waitFor(() =>
      expect(screen.getByTestId('performance-metric-total-return').textContent).toContain('0.33%'),
    )
    expect(screen.getByTestId('performance-metric-total-return').textContent).not.toContain('NaN')
  })

  it('PN6: 실현 성과 행은 세후 기본 = realized_net_sum_krw, 세전 = realized_sum_krw', async () => {
    mockApis()
    renderCard()
    await waitFor(() =>
      expect(screen.getByTestId('realized-pnl-momentum').textContent).toContain('-12,500'),
    )
    await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByRole('button', { name: '세전' }))
    await waitFor(() =>
      expect(screen.getByTestId('realized-pnl-momentum').textContent).toContain('+120,000'),
    )
  })

  it('PN7: 토글은 화면 공통 — 카드에서 세전을 누르면 차트 토글도 세전이 된다', async () => {
    mockApis()
    render(
      <TestProviders>
        <TradingStatusProvider>
          <PerformanceCard selectedStrategy="all" />
          <ProfitChart selectedStrategy="all" />
        </TradingStatusProvider>
      </TestProviders>,
    )
    await waitFor(() => expect(screen.getAllByTestId('cost-basis-toggle').length).toBe(2))
    const [cardToggle, chartToggle] = screen.getAllByTestId('cost-basis-toggle')
    await userEvent.click(within(cardToggle).getByRole('button', { name: '세전' }))
    await waitFor(() =>
      expect(within(chartToggle).getByRole('button', { name: '세전' })).toHaveAttribute('aria-pressed', 'true'),
    )
  })
})
