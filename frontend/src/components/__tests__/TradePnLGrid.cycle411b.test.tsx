/**
 * cycle411 보완 Red — 매매손익 표 표기 (메인 세션 결정 10-08 「보완 결정」 L1·M4).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」.
 *
 *  - PGB1 (L1): 수수료·세금·슬리피지·요약 비용 = 정수 원(반올림) + 「원」. 비용률 = 소수 1자리 bp.
 *  - PGB2 (M4): 요약의 순손익 합·수수료·세금이 null(비용 조회 실패 = 모름)이면 `—` — `0원` 으로 그리지 않는다.
 *  - PGB3 (M4): 페어 `slippage_won` null 이면 `—`.
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { makeTradePair, wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import TradePnLGrid from '../TradePnLGrid'

const PAIR = makeTradePair({
  ticker: '000660',
  ticker_name: 'SK하이닉스',
  strategy: 'volatility_breakout',
  pair_key: 'volatility_breakout:000660:O3',
  buy_order_nos: ['O3'],
  sell_order_nos: ['O5'],
  profit_loss: 10000,
  profit_rate: 2.0,
  fee: 141.37,
  tax: 1015.4,
  net_profit_loss: 8843.23,
  net_profit_rate: 1.7686,
  cost_bp: 22.8467,
  slippage_won: 1999.6,
  cost_status: 'settled',
  allocated: true,
} as never)

const SUMMARY = {
  realized_total_krw: 10000,
  realized_rate_pct: 2.0,
  win_count: 1,
  loss_count: 0,
  even_count: 0,
  win_rate_pct: 100,
  closed_count: 1,
  fee_sum: 427.4,
  tax_sum: 2448.3,
  realized_net_total_krw: 8843.23,
  realized_net_rate_pct: 1.77,
  slippage_n: 1,
}

function setup(pairs: unknown[], summary: Record<string, unknown> = SUMMARY) {
  server.use(
    http.get('/api/history/pnl', () =>
      HttpResponse.json(wrap({ pairs, summary, page: 1, size: 30, total: pairs.length, total_pages: 1 })),
    ),
  )
  return render(
    <TestProviders>
      <TradePnLGrid />
    </TestProviders>,
  )
}

describe('cycle411b — TradePnLGrid 표기', () => {
  it('PGB1: 정수 원 + 원 · bp 소수 1자리', async () => {
    setup([PAIR])
    const row = await screen.findByTestId('pnl-row-0')
    const text = row.textContent ?? ''
    expect(text).toContain('141원')
    expect(text).not.toContain('141.37')
    expect(text).toContain('1,015원')
    expect(text).not.toContain('1,015.4')
    expect(text).toContain('2,000원') // 슬리피지 1,999.6 → 2,000
    expect(text).not.toContain('1,999.6')
    expect(text).toContain('22.8bp')
    expect(text).not.toContain('22.85')
    expect(text).toContain('+8,843원')
    await waitFor(() => expect(screen.getByTestId('pnl-summary-cost')).toBeInTheDocument())
    expect(screen.getByTestId('pnl-summary-cost').textContent).toContain('2,876원') // 427.4 + 2,448.3
    expect(screen.getByTestId('pnl-summary-cost').textContent).not.toContain('2,875.7')
  })

  it('PGB2·PGB3: 모름(null)은 — — 0원 금지', async () => {
    setup(
      [{ ...PAIR, slippage_won: null }],
      { ...SUMMARY, fee_sum: null, tax_sum: null, realized_net_total_krw: null, realized_net_rate_pct: null },
    )
    const row = await screen.findByTestId('pnl-row-0')
    expect(row.textContent).toContain('—')
    await waitFor(() => expect(screen.getByTestId('pnl-summary-cost')).toBeInTheDocument())
    expect(screen.getByTestId('pnl-summary-cost').textContent?.trim()).toBe('—')
    expect(screen.getByTestId('pnl-summary-net').textContent?.trim()).toBe('—')
  })
})
