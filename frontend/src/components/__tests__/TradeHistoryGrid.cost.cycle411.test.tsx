/**
 * cycle411 Red — 체결 내역 SELL 행 순손익 (사용자 결정 10-08 Q3).
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` — `/api/history` SELL 행
 * `fee`·`tax`·`net_profit_loss`, BUY 행 `fee`, 행마다 `cost_status`.
 *
 * 계약
 *  - TH1: 머리 칸 `순손익` 이 있고 기존 `매매손익`(세전) 칸도 그대로다.
 *  - TH2: SELL 행 순손익 = `net_profit_loss`(`+18,465원`), `cost_status="estimated"` 면 같은 칸에 `추정`.
 *  - TH3: BUY 행 순손익 칸은 `-` (매수 행은 실현손익이 없다).
 */

import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { makeTrade, wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import TradeHistoryGrid from '../TradeHistoryGrid'

function setup(trades: unknown[]) {
  server.use(
    http.get('/api/history', () =>
      HttpResponse.json(wrap({ trades, page: 1, size: 20, total: trades.length, total_pages: 1 })),
    ),
  )
  return render(
    <TestProviders>
      <TradeHistoryGrid />
    </TestProviders>,
  )
}

describe('cycle411 — TradeHistoryGrid SELL 행 순손익', () => {
  it('TH1·TH2·TH3', async () => {
    setup([
      makeTrade({
        id: 2,
        trade_type: 'SELL',
        price: 72000,
        profit_loss: 20000,
        order_no: 'O2',
        fee: 102,
        tax: 1433,
        net_profit_loss: 18465,
        cost_status: 'settled',
      } as never),
      makeTrade({
        id: 7,
        ticker: '069500',
        ticker_name: 'KODEX 200',
        trade_type: 'SELL',
        price: 30300,
        profit_loss: 3000,
        order_no: 'O7',
        fee: 43,
        tax: 0,
        net_profit_loss: 2957,
        cost_status: 'estimated',
      } as never),
      makeTrade({ id: 1, trade_type: 'BUY', order_no: 'O1', fee: 99, cost_status: 'settled' } as never),
    ])
    await screen.findByTestId('trade-row-0')
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim())
    expect(headers).toContain('매매손익')
    expect(headers).toContain('순손익')

    const sell = screen.getByTestId('trade-row-0')
    expect(sell.textContent).toContain('+20,000원')
    expect(sell.textContent).toContain('+18,465원')
    expect(within(sell).queryByText('추정')).toBeNull()

    const etf = screen.getByTestId('trade-row-1')
    expect(etf.textContent).toContain('+2,957원')
    expect(within(etf).getByText('추정')).toBeInTheDocument()

    const buy = screen.getByTestId('trade-row-2')
    expect(buy.textContent).not.toContain('NaN')
    expect(buy.textContent).not.toMatch(/[+-]\d[\d,]*원.*[+-]\d[\d,]*원/) // BUY 행엔 손익 금액이 둘 찍히지 않는다
  })
})
