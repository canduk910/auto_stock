/**
 * cycle446 D-6 — 잔고 표의 「AI 판단」 컬럼. 청산 AI 섀도 기록(`llm_worker`,
 * `exit_ai_evaluations`)의 최근 평가를 보인다. 「없음」(대상 전략 아님)과 「모름」(대상인데
 * 아직 평가 없음)을 가른다 — 빈칸·0 으로 접지 않는다.
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

function setup(holdings: Holding[]) {
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
  )
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

describe('cycle446 — BalanceTable AI 판단 컬럼', () => {
  it('ai_verdict 가 없으면(구 서버) — 를 보인다', async () => {
    setup([makeHolding()])
    const cell = await screen.findByTestId('ai-verdict-005930')
    expect(cell).toHaveTextContent('—')
  })

  it('not_applicable 이면 「대상 아님」을 보인다', async () => {
    setup([makeHolding({ ai_verdict: { status: 'not_applicable' } })])
    const cell = await screen.findByTestId('ai-verdict-005930')
    expect(cell).toHaveTextContent('대상 아님')
  })

  it('no_evaluation 이면 「평가 없음」을 보인다(0 이나 빈칸이 아니다)', async () => {
    setup([makeHolding({ ai_verdict: { status: 'no_evaluation' } })])
    const cell = await screen.findByTestId('ai-verdict-005930')
    expect(cell).toHaveTextContent('평가 없음')
  })

  it('available 이면 action·점수를 보인다', async () => {
    setup([makeHolding({
      ai_verdict: {
        status: 'available', action: 'hold', exit_score: 35,
        bar_date: '2026-10-13', evaluated_at: '2026-10-14T08:16:00.000000+09:00',
      },
    })])
    const cell = await screen.findByTestId('ai-verdict-005930')
    expect(cell).toHaveTextContent('보유')
    expect(cell).toHaveTextContent('35점')
    expect(cell.title).toContain('2026-10-13')
  })
})
