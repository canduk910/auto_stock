/**
 * cycle387 Red — 세 그리드의 행 더블클릭 → 종목 차트 모달 (O1~O7).
 *
 * 명세: `_workspace/red/cycle387_stock_chart_spec.md` §2.2 · §3.2(O1~O7)
 * 사용자 요청(2026-09-28): 「잔고내역과 거래내역(주문체결내역, 매매손익)에서 종목을 더블클릭하면
 * KLineChart 를 사용한 주식차트조회를 최근 5년치에 대해 일봉/주봉/월봉으로 제공」.
 *
 * ## 봉인하는 계약
 * - 행 testid — 잔고 `balance-row-{ticker}` · 체결 `trade-row-{row.index}` · 손익 `pnl-row-{row.index}`,
 *   세 행 모두 `title="더블클릭 — 종목 차트"`.
 * - 행 `onDoubleClick` 이 그 행의 종목코드·이름으로 모달을 연다(모달은 `React.lazy` 분리 청크 —
 *   `findBy*` 로 기다린다). 요청은 `ticker=<행 코드>&period=D&years=5`.
 * - **버튼·링크·입력 안에서 난 더블클릭은 무시**한다 — 잔고 「매도」 두 번 누름이 매도 확인창과
 *   차트 모달을 겹쳐 띄우면 안 된다. 기존 동작(매도 확인창·AI 자문 팝업)은 그대로다.
 * - 6자리 숫자가 아닌 코드(영숫자 `0080G0`·결측)는 모달을 열되 `stock-chart-unsupported` · 요청 0.
 * - 한 번 클릭은 아무것도 열지 않는다.
 *
 * `klinecharts` 는 jsdom 에서 돌릴 수 없어 `test/fakeKlinecharts.ts` 로 대체한다(lazy 청크의 동적
 * import 에도 `vi.mock` 이 적용된다).
 *
 * RED: 행 testid·더블클릭 핸들러·모달이 없다 → 전 케이스 FAIL(O2·O4·O7 은 행 testid 부재로 FAIL).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import {
  makeLlmEvaluationSummary,
  makeTrade,
  makeTradePair,
  wrap,
} from '../../test/factories'
import { TestProviders } from '../../test/providers'
import { STOCK_CHART_RESPONSES, type StockChartPeriodKey } from '../../test/fixtures/stockChart.fixture'
import { resetFakeKline } from '../../test/fakeKlinecharts'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import BalanceTable from '../BalanceTable'
import TradeHistoryGrid from '../TradeHistoryGrid'
import TradePnLGrid from '../TradePnLGrid'
import type { Holding } from '../../types/balance'

vi.mock('klinecharts', async () => (await import('../../test/fakeKlinecharts')).klinechartsModule)

const ROW_TITLE = '더블클릭 — 종목 차트'

beforeEach(() => {
  resetFakeKline()
})

function installChart() {
  const requests: URL[] = []
  server.use(
    http.get('/api/stock-chart/candles', ({ request }) => {
      const url = new URL(request.url)
      requests.push(url)
      const period = (url.searchParams.get('period') ?? 'D') as StockChartPeriodKey
      return HttpResponse.json(STOCK_CHART_RESPONSES[period])
    }),
  )
  return requests
}

async function expectModalFor(requests: URL[], ticker: string, name: string) {
  const modal = await screen.findByTestId('stock-chart-modal', {}, { timeout: 5000 })
  expect(modal).toBeInTheDocument()
  const title = await screen.findByTestId('stock-chart-title')
  expect(title.textContent).toContain(name)
  expect(title.textContent).toContain(ticker)
  await waitFor(() => expect(requests.length).toBeGreaterThan(0), { timeout: 5000 })
  const q = requests[0].searchParams
  expect([q.get('ticker'), q.get('period'), q.get('years')]).toEqual([ticker, 'D', '5'])
}

/** 차트가 열리지 않았음을 확인한다 — lazy 청크·요청이 뒤늦게 올 틈을 준다. */
async function expectNoChart(requests: URL[]) {
  await new Promise((r) => setTimeout(r, 80))
  expect(screen.queryByTestId('stock-chart-modal')).toBeNull()
  expect(screen.queryByTestId('stock-chart-chunk-loading')).toBeNull()
  expect(requests).toHaveLength(0)
}

// ─────────────────────────────────────────────────────────────────────────────
// 잔고 (BalanceTable) — BalanceTable.test.tsx 의 설정을 따른다
// ─────────────────────────────────────────────────────────────────────────────

function makeHolding(overrides: Partial<Holding> = {}): Holding {
  return {
    ticker: '005930',
    name: '삼성전자',
    quantity: 10,
    sellable_quantity: 10,
    avg_price: 70000,
    purchase_amount: 700000,
    current_price: 72000,
    eval_amount: 720000,
    eval_profit_loss: 20000,
    eval_profit_rate: 2.86,
    nxt_tradable: true,
    krx_halted: false,
    excg_dvsn_cd: '02',
    ...overrides,
  }
}

function setupBalance(holdings: Holding[]) {
  server.use(
    http.get('/api/balance', () =>
      HttpResponse.json(
        wrap({
          holdings,
          summary: {
            deposit: 10_000_000,
            stock_eval_amount: 720_000,
            total_eval_amount: 10_720_000,
            net_asset: 10_720_000,
            purchase_total: 700_000,
            eval_total: 720_000,
            profit_loss_total: 20_000,
          },
        }),
      ),
    ),
    http.get('/api/trading/status', () =>
      HttpResponse.json(
        wrap({
          running: false,
          env: 'vts',
          positions: 0,
          pending_buys: 0,
          position_tickers: [],
          phase: 'main_trading',
          scan: {
            filtered_tickers: [],
            filtered_count: 0,
            subscribed_tickers: [],
            subscribed_count: 0,
            last_scan_time: null,
            ticker_names: {},
            ticker_prices: {},
            ticker_market_info: {},
          },
          positions_detail: {},
          orders: { pending_buy_tickers: [], pending_buy_orders: {}, fills: {}, pending_cancels: [] },
          strategy: { buy_disabled: false, daily_realized_pnl: 0, total_investment: 0, buy_signals: [] },
          strategies: {},
        }),
      ),
    ),
  )
}

async function renderBalance() {
  render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
  await screen.findByRole('table')
}

describe('O1·O2·O6·O7 — 잔고 행', () => {
  it('O1: 행 더블클릭 → 그 종목의 차트 모달 · 요청 ticker 일치 · 행 title', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupBalance([makeHolding(), makeHolding({ ticker: '000660', name: 'SK하이닉스' })])
    await renderBalance()

    const row = await screen.findByTestId('balance-row-000660')
    expect(row).toHaveAttribute('title', ROW_TITLE)
    await user.dblClick(within(row).getByText('SK하이닉스'))

    await expectModalFor(requests, '000660', 'SK하이닉스')
  })

  it('O2: 「매도」 버튼 더블클릭 → 차트 모달 없음 · 매도 확인창은 그대로', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupBalance([makeHolding()])
    await renderBalance()

    const row = await screen.findByTestId('balance-row-005930')
    await user.dblClick(within(row).getByRole('button', { name: '매도' }))

    expect(await screen.findByText('수동 매도')).toBeInTheDocument()
    await expectNoChart(requests)
  })

  it('O6: 영숫자 코드(0080G0) 행 → stock-chart-unsupported · 요청 0', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupBalance([makeHolding({ ticker: '0080G0', name: '신주인수권' })])
    await renderBalance()

    const row = await screen.findByTestId('balance-row-0080G0')
    await user.dblClick(within(row).getByText('신주인수권'))

    const box = await screen.findByTestId('stock-chart-unsupported', {}, { timeout: 5000 })
    expect(box.textContent).toContain('0080G0')
    await new Promise((r) => setTimeout(r, 50))
    expect(requests).toHaveLength(0)
  })

  it('O7: 한 번 클릭은 아무것도 열지 않는다', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupBalance([makeHolding()])
    await renderBalance()

    const row = await screen.findByTestId('balance-row-005930')
    await user.click(within(row).getByText('삼성전자'))
    await expectNoChart(requests)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 주문체결내역 (TradeHistoryGrid)
// ─────────────────────────────────────────────────────────────────────────────

const BUY_WITH_EVAL = '0000123456'
/** 2026-09-11 23:05:47 UTC = 2026-09-12 08:05:47 KST. 요약 키의 날짜는 KST 사영이어야 버튼이 켜진다. */
const TS = '2026-09-11T23:05:47Z'
const KST_DATE = '2026-09-12'

function setupHistory(trades: ReturnType<typeof makeTrade>[]) {
  server.use(
    http.get('/api/history', () =>
      HttpResponse.json(wrap({ trades, page: 1, size: 20, total: trades.length, total_pages: 1 })),
    ),
    http.get('/api/llm-evaluations', () =>
      HttpResponse.json(
        wrap({
          [`${KST_DATE}|${BUY_WITH_EVAL}`]: makeLlmEvaluationSummary({
            order_no: BUY_WITH_EVAL,
            trade_date: KST_DATE,
            score: 62,
            min_score: 70,
            would_block: true,
          }),
        }),
      ),
    ),
  )
}

function renderHistory() {
  render(
    <TestProviders>
      <TradeHistoryGrid />
    </TestProviders>,
  )
}

describe('O3·O4·O6 — 주문체결내역 행', () => {
  it('O3: 행 더블클릭 → 그 행의 ticker·ticker_name 으로 연다', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupHistory([
      makeTrade({ id: 1, timestamp: TS, order_no: BUY_WITH_EVAL, ticker: '005930', ticker_name: '삼성전자' }),
      makeTrade({ id: 2, timestamp: TS, order_no: '0000222222', ticker: '000660', ticker_name: 'SK하이닉스' }),
    ])
    renderHistory()

    const row = await screen.findByTestId('trade-row-1', {}, { timeout: 5000 })
    expect(row).toHaveAttribute('title', ROW_TITLE)
    await user.dblClick(within(row).getByText('SK하이닉스'))

    await expectModalFor(requests, '000660', 'SK하이닉스')
  })

  it('O4: 「AI 자문」 버튼 더블클릭 → 차트 모달 없음 (AI 팝업은 그대로)', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupHistory([
      makeTrade({ id: 1, timestamp: TS, order_no: BUY_WITH_EVAL, ticker: '005930', ticker_name: '삼성전자' }),
    ])
    renderHistory()

    await screen.findByTestId('trade-row-0', {}, { timeout: 5000 })
    const btn = await screen.findByTestId(`llm-eval-btn-${BUY_WITH_EVAL}`, {}, { timeout: 5000 })
    await waitFor(() => expect(btn).toBeEnabled(), { timeout: 5000 })
    await user.dblClick(btn)

    expect(await screen.findByTestId('llm-eval-modal', {}, { timeout: 5000 })).toBeInTheDocument()
    await expectNoChart(requests)
  })

  it('O6: 종목코드 결측 행(셀 표기 -) → stock-chart-unsupported · 요청 0', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    setupHistory([
      makeTrade({
        id: 1,
        timestamp: TS,
        order_no: '0000999999',
        ticker: null as unknown as string,
        ticker_name: '코드없음',
      }),
    ])
    renderHistory()

    const row = await screen.findByTestId('trade-row-0', {}, { timeout: 5000 })
    await user.dblClick(within(row).getByText('코드없음'))

    expect(await screen.findByTestId('stock-chart-unsupported', {}, { timeout: 5000 })).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    expect(requests).toHaveLength(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 매매손익 (TradePnLGrid)
// ─────────────────────────────────────────────────────────────────────────────

describe('O5 — 매매손익 행', () => {
  it('O5: 행 더블클릭 → 그 페어의 ticker·ticker_name 으로 연다', async () => {
    const user = userEvent.setup()
    const requests = installChart()
    const pairs = [
      makeTradePair(),
      makeTradePair({
        ticker: '042700',
        ticker_name: '한미반도체',
        buy_order_nos: ['0000200001'],
        pair_key: 'volatility_breakout:042700:0000200001',
      }),
    ]
    server.use(
      http.get('/api/history/pnl', () =>
        HttpResponse.json(
          wrap({
            pairs,
            summary: {
              realized_total_krw: 0,
              realized_rate_pct: 0,
              win_count: 0,
              loss_count: 0,
              even_count: 0,
              win_rate_pct: 0,
              closed_count: 0,
            },
            page: 1,
            size: 30,
            total: pairs.length,
            total_pages: 1,
          }),
        ),
      ),
    )
    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    )

    const row = await screen.findByTestId('pnl-row-1', {}, { timeout: 5000 })
    expect(row).toHaveAttribute('title', ROW_TITLE)
    await user.dblClick(within(row).getByText('한미반도체'))

    await expectModalFor(requests, '042700', '한미반도체')
  })
})
