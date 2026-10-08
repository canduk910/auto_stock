/**
 * cycle411 보완 Red M1 — 잔고 순 평가손익 = 평가손익 − 예상 매도비용 − 이미 낸 매수 수수료.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 M1 (메인 세션 결정 §3 의 화면 쪽).
 * 백엔드는 보유 종목마다 `buy_fee_paid`(정산 실측 있으면 실측, 없으면 추정)·`buy_fee_status` 를 싣는다.
 *
 *  - BB1: 순 평가손익 = round(평가손익 − round(평가금액 × sell_cost_rate) − buy_fee_paid), 정수 원.
 *  - BB2: `buy_fee_paid` 가 없는(구 서버) 응답은 기존 식(평가손익 − 예상 매도비용) 그대로.
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

function makeHolding(overrides: Record<string, unknown> = {}): Holding {
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
    sell_cost_rate: 0.00341,
    cost_status: 'estimated',
    ...overrides,
  } as Holding
}

function setup(holdings: Holding[]) {
  server.use(
    http.get('/api/balance', () =>
      HttpResponse.json(
        wrap({
          holdings,
          summary: {
            deposit: 0,
            stock_eval_amount: 720_000,
            total_eval_amount: 720_000,
            net_asset: 720_000,
            purchase_total: 700_000,
            eval_total: 720_000,
            profit_loss_total: 20_000,
          },
        }),
      ),
    ),
  )
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

describe('cycle411b — BalanceTable 매수 수수료 차감', () => {
  it('BB1: 이미 낸 매수 수수료까지 뺀다 (정수 원)', async () => {
    setup([makeHolding({ buy_fee_paid: 98.6, buy_fee_status: 'settled' })])
    await screen.findByTestId('balance-row-005930')
    // 20,000 − 2,455 − 98.6 = 17,446.4 → 17,446
    const net = screen.getByTestId('net-pl-005930').textContent ?? ''
    expect(net).toContain('17,446')
    expect(net).not.toContain('17,446.')
    expect(net).not.toContain('17,545')
  })

  it('BB2: buy_fee_paid 없는 구 응답은 기존 식', async () => {
    setup([makeHolding()])
    await screen.findByTestId('balance-row-005930')
    expect(screen.getByTestId('net-pl-005930').textContent).toContain('17,545')
  })
})
