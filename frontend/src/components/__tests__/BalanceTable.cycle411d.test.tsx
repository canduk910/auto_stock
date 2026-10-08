/**
 * cycle411 3차 검증 후 LOW 결함 — 잔고 표 전체 줄바꿈 금지 (F10 재확인).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md`.
 *
 * cycle411c 가 「예상 매도비용」·「순 평가손익」 두 칸에만 `whitespace-nowrap` 을 달았으나,
 * 3차 검증(화면 실측, 1280px)에서 다른 기존 칸(거래시장 「확인중」·매입일·보유수량·손절가·
 * 목표가 머리글 등)이 여전히 줄바꿈되어 행 높이가 비용 칸 추가 전(약 51px)으로 돌아오지
 * 않았다. `white-space` 는 상속되는 CSS 속성이므로 `<table>` 루트에 `whitespace-nowrap` 을
 * 달면 모든 자손 셀이 기본으로 물려받는다(각 셀에 개별로 달 필요가 없다) — ScrollPane 이
 * 이미 `overflow-auto` 라 넘치는 폭은 가로 스크롤로 받는다.
 *
 * jsdom 은 실제 레이아웃(줄바꿈·행 높이)을 재현하지 못하므로 — className 단언으로
 * 고정한다. 실제 화면 실측(1280px 행 높이)은 검증 단계에서 별도로 확인한다.
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
    // nxt_tradable/krx_halted 둘 다 null → 거래시장 칸 「확인중」(4자 — 좁은 칸에서
    // 「확인/중」 으로 줄바꿈되던 실측 재현 조건).
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

describe('cycle411d — BalanceTable 표 전체 줄바꿈 금지 (F10 재확인)', () => {
  it('BD1: <table> 루트에 whitespace-nowrap — 기존 칸(거래시장·매입일 등)도 상속으로 줄바꿈 금지', async () => {
    const { container } = setup([makeHolding()])
    await screen.findByTestId('balance-row-005930')
    const table = container.querySelector('table')
    expect(table, '<table> 요소를 찾을 수 없다').not.toBeNull()
    expect(table!.className).toContain('whitespace-nowrap')
  })

  it('BD2: 기존 비용 두 칸 nowrap 은 그대로(회귀 없음)', async () => {
    setup([makeHolding()])
    await screen.findByTestId('balance-row-005930')
    for (const name of ['예상 매도비용', '순 평가손익']) {
      expect(screen.getByRole('columnheader', { name }).className).toContain('whitespace-nowrap')
    }
  })
})
