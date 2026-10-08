/**
 * cycle411 2차 보완 Red — 잔고 순 평가손익 「모름」 · 칸 줄바꿈 (F3 · F10).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」.
 *
 *  - BC1 (F3): `buy_fee_paid: null`(서버가 비용을 모른다고 명시) → 순 평가손익 「—」. `?? 0` 으로 0 원 취급 금지.
 *              (칸 자체가 없는 구 서버 응답은 기존 식 — `BalanceTable.cycle411b` BB2 그대로)
 *  - BC2 (F10): 「예상 매도비용」·「순 평가손익」 머리칸과 두 값 칸은 `whitespace-nowrap`
 *              (1280px 에서 한 자씩 줄바꿈되어 행 높이가 51→85px 로 늘던 결함).
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
    buy_fee_paid: 98.6,
    buy_fee_status: 'settled',
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

describe('cycle411c — BalanceTable', () => {
  it('BC1 (F3): buy_fee_paid null → 순 평가손익 「—」', async () => {
    setup([makeHolding({ buy_fee_paid: null, buy_fee_status: null })])
    await screen.findByTestId('balance-row-005930')
    const net = screen.getByTestId('net-pl-005930').textContent ?? ''
    expect(net).toContain('—')
    // 매수 수수료를 0 으로 친 값(20,000 − 2,455 = 17,545)을 그리지 않는다
    expect(net).not.toContain('17,545')
    // 예상 매도비용은 요율로 계산되므로 그대로
    expect(screen.getByTestId('sell-cost-005930').textContent).toContain('2,455')
  })

  it('BC2 (F10): 비용 두 칸은 줄바꿈하지 않는다', async () => {
    setup([makeHolding()])
    await screen.findByTestId('balance-row-005930')
    for (const name of ['예상 매도비용', '순 평가손익']) {
      expect(screen.getByRole('columnheader', { name }).className).toContain('whitespace-nowrap')
    }
    expect(screen.getByTestId('sell-cost-005930').className).toContain('whitespace-nowrap')
    expect(screen.getByTestId('net-pl-005930').className).toContain('whitespace-nowrap')
  })
})
