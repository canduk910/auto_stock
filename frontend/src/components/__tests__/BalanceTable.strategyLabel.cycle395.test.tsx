/**
 * cycle395 — BalanceTable "전체" 탭 전략 배지가 중앙 정본 한글 표시명을 쓰는지 회귀 가드.
 *
 * 배경: BalanceTable 의 로컬 `STRATEGY_NAMES` 사본은 7 전략 중 4개만 들어 있었다
 * (momentum/volatility_breakout/long_tail_volatility/donchian_swing). bull_flag_breakout·
 * vcp_breakout·kojiro 보유 종목은 배지에 영어 id 원문("bull_flag_breakout" 등)이 그대로
 * 찍혔다. utils/strategyMeta.ts 중앙 정본(`strategyLabel`)으로 교체 후 7 전략 전부
 * 한글 표시명이 나와야 한다.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import BalanceTable from '../BalanceTable'
import type { Holding } from '../../types/balance'

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
    nxt_tradable: null,
    krx_halted: null,
    excg_dvsn_cd: null,
    ...overrides,
  }
}

function emptyStrategyInfo(positionTickers: string[]) {
  return {
    name: 'unused-api-name',
    enabled: true,
    weight: 0.1,
    positions: positionTickers.length,
    pending_buys: 0,
    position_tickers: positionTickers,
    total_investment: 1_000_000,
    daily_realized_pnl: 0,
    buy_disabled: false,
    buy_signals: [],
    positions_detail: {},
    pending_buy_tickers: [],
  }
}

function setup() {
  server.use(
    http.get('/api/balance', () =>
      HttpResponse.json(
        wrap({
          holdings: [
            makeHolding({ ticker: '005930', name: '삼성전자' }),
            makeHolding({ ticker: '000660', name: 'SK하이닉스' }),
            makeHolding({ ticker: '035720', name: '카카오' }),
          ],
          summary: {
            deposit: 10_000_000,
            stock_eval_amount: 2_160_000,
            total_eval_amount: 12_160_000,
            net_asset: 12_160_000,
            purchase_total: 2_100_000,
            eval_total: 2_160_000,
            profit_loss_total: 60_000,
          },
        }),
      ),
    ),
    http.get('/api/trading/status', () =>
      HttpResponse.json(
        wrap({
          running: true,
          env: 'vts',
          positions: 3,
          pending_buys: 0,
          position_tickers: ['005930', '000660', '035720'],
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
          orders: {
            pending_buy_tickers: [],
            pending_buy_orders: {},
            fills: {},
            pending_cancels: [],
          },
          strategy: { buy_disabled: false, daily_realized_pnl: 0, total_investment: 0, buy_signals: [] },
          strategies: {
            // bull_flag_breakout / vcp_breakout / kojiro — 구 로컬 STRATEGY_NAMES 에 없던 3종.
            bull_flag_breakout: emptyStrategyInfo(['005930']),
            vcp_breakout: emptyStrategyInfo(['000660']),
            kojiro: emptyStrategyInfo(['035720']),
          },
        }),
      ),
    ),
  )
}

async function renderTable() {
  render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
  await screen.findByRole('table')
}

describe('BalanceTable — 전략 배지 한글 표시명 (cycle395)', () => {
  it('bull_flag_breakout/vcp_breakout/kojiro 보유 종목도 영어 id 아닌 한글 표시명이 나온다', async () => {
    setup()
    await renderTable()

    await screen.findByText('삼성전자')

    // 한글 표시명이 각각 노출된다.
    expect(screen.getByText('추세 눌림목 돌파')).toBeInTheDocument()
    expect(screen.getByText('VCP 변동성 수축')).toBeInTheDocument()
    expect(screen.getByText('고지로 대순환')).toBeInTheDocument()

    // 영어 id 원문은 화면 어디에도 노출되지 않는다.
    expect(screen.queryByText('bull_flag_breakout')).not.toBeInTheDocument()
    expect(screen.queryByText('vcp_breakout')).not.toBeInTheDocument()
    expect(screen.queryByText('kojiro')).not.toBeInTheDocument()
    // 백엔드 API 가 준 이름이 아니라 중앙 정본 이름이 이긴다.
    expect(screen.queryByText('unused-api-name')).not.toBeInTheDocument()
  })
})
