/**
 * cycle411 보완 Red L1 — 체결 내역 순손익은 정수 원(반올림) + 「원」.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 L1.
 * 백엔드 `/api/history` 의 `net_profit_loss` 는 배분 결과라 소수가 붙는다(예: 18,465.37).
 */

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { makeTrade, wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import TradeHistoryGrid from '../TradeHistoryGrid'

describe('cycle411b — TradeHistoryGrid 순손익 정수 원', () => {
  it('THB1: 18,465.37 → +18,465원', async () => {
    const trades = [
      makeTrade({
        id: 2,
        trade_type: 'SELL',
        price: 72000,
        profit_loss: 20000,
        order_no: 'O2',
        fee: 101.63,
        tax: 1433,
        net_profit_loss: 18465.37,
        cost_status: 'settled',
      } as never),
    ]
    server.use(
      http.get('/api/history', () =>
        HttpResponse.json(wrap({ trades, page: 1, size: 20, total: 1, total_pages: 1 })),
      ),
    )
    render(
      <TestProviders>
        <TradeHistoryGrid />
      </TestProviders>,
    )
    const row = await screen.findByTestId('trade-row-0')
    expect(row.textContent).toContain('+18,465원')
    expect(row.textContent).not.toContain('18,465.37')
  })
})
