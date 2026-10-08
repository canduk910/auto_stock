/**
 * cycle411 Red — 잔고 표에 「예상 매도비용(추정)」·「순 평가손익」 (사용자 결정 10-08 Q1).
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` — `/api/balance` 보유 종목마다
 * `sell_cost_rate`(수수료율 + 세율, ETF 는 수수료율만)·`cost_status="estimated"` 를 백엔드가 싣고,
 * 화면이 (실시간 현재가로 덮인) 평가금액에 곱한다.
 *
 * 계약
 *  - BL1: 머리 칸 `예상 매도비용`·`순 평가손익` 이 있다.
 *  - BL2: 예상 매도비용 = round(평가금액 × sell_cost_rate), 순 평가손익 = 평가손익 − 예상 매도비용.
 *         testid `sell-cost-<ticker>`·`net-pl-<ticker>`. 예상 매도비용 칸에 `추정` 표시.
 *  - BL3: `sell_cost_rate` 가 없으면(구 응답) 두 칸 모두 `—` (숫자를 지어내지 않는다).
 *  - BL4: 기존 평가손익 칸은 그대로(세전).
 */

import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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
            stock_eval_amount: 1_023_000,
            total_eval_amount: 1_023_000,
            net_asset: 1_023_000,
            purchase_total: 1_000_000,
            eval_total: 1_023_000,
            profit_loss_total: 23_000,
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

describe('cycle411 — BalanceTable 예상 매도비용·순 평가손익', () => {
  it('BL1·BL2·BL4: 비율 × 평가금액 · 평가손익 − 비용', async () => {
    setup([
      makeHolding({ sell_cost_rate: 0.00341, cost_status: 'estimated' }),
      makeHolding({
        ticker: '069500',
        name: 'KODEX 200',
        purchase_amount: 300000,
        current_price: 30300,
        eval_amount: 303000,
        eval_profit_loss: 3000,
        eval_profit_rate: 1.0,
        sell_cost_rate: 0.00142,
        cost_status: 'estimated',
      }),
    ])
    await screen.findByTestId('balance-row-005930')
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim())
    expect(headers).toContain('예상 매도비용')
    expect(headers).toContain('순 평가손익')

    expect(screen.getByTestId('sell-cost-005930').textContent).toContain('2,455') // 720,000 × 0.341%
    expect(within(screen.getByTestId('sell-cost-005930')).getByText('추정')).toBeInTheDocument()
    expect(screen.getByTestId('net-pl-005930').textContent).toContain('17,545')
    expect(screen.getByTestId('sell-cost-069500').textContent).toContain('430') // 303,000 × 0.142%
    expect(screen.getByTestId('net-pl-069500').textContent).toContain('2,570')
    // 기존 평가손익(세전)
    expect(screen.getByTestId('balance-row-005930').textContent).toContain('20,000원')
  })

  it('BL3: sell_cost_rate 가 없으면 두 칸 모두 —', async () => {
    setup([makeHolding()])
    await screen.findByTestId('balance-row-005930')
    expect(screen.getByTestId('sell-cost-005930').textContent?.trim()).toBe('—')
    expect(screen.getByTestId('net-pl-005930').textContent?.trim()).toBe('—')
  })
})
