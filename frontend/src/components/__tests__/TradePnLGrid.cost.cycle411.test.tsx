/**
 * cycle411 Red — 매매손익 표에 실비용 칸 + 「추정」/「배분」 배지 + 요약 바 (사용자 결정 10-08 Q1·Q4).
 *
 * 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md`.
 *
 * 계약
 *  - G1: 머리 칸 `수수료`·`세금`·`순손익`·`순손익율`·`비용률`·`슬리피지` 가 있다. 기존 `매매손익`·`손익율` 칸은 그대로(세전).
 *  - G2: 행 값 — 순손익 `+18,366원`, 순손익율 `+2.62%`, 비용률 `23.01bp`, 슬리피지 `2,000원`.
 *  - G3: `cost_status="estimated"` 행은 `추정` 배지, `allocated=true` 행은 `배분` 배지(행 testid `cost-badge-*`).
 *        정산·단독 행에는 둘 다 없다.
 *  - G4: 요약 바 — `pnl-summary-net`(순손익 합 `realized_net_total_krw`) · `pnl-summary-cost`(수수료+세금)
 *        · `pnl-summary-slippage`(덮인 건수 `slippage_n` 을 `N건` 으로).
 *  - G5: 새 칸이 없는 페어(구 응답)는 `—` 로 그린다(예외·NaN 금지).
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { makeTradePair, wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import TradePnLGrid from '../TradePnLGrid'

const SETTLED = makeTradePair({
  buy_date: '2026-10-06',
  sell_date: '2026-10-07',
  buy_price: 70000,
  buy_qty: 10,
  sell_price: 72000,
  sell_qty: 10,
  profit_loss: 20000,
  profit_rate: 2.8571,
  strategy: 'momentum',
  pair_key: 'momentum:005930:O1',
  buy_order_nos: ['O1'],
  sell_order_nos: ['O2'],
  fee: 201,
  tax: 1433,
  net_profit_loss: 18366,
  net_profit_rate: 2.6237,
  cost_bp: 23.01,
  slippage_won: 2000,
  cost_status: 'settled',
  allocated: false,
} as never)

const ALLOCATED = makeTradePair({
  ticker: '000660',
  ticker_name: 'SK하이닉스',
  strategy: 'volatility_breakout',
  pair_key: 'volatility_breakout:000660:O3',
  buy_order_nos: ['O3'],
  sell_order_nos: ['O5'],
  profit_loss: 10000,
  profit_rate: 2.0,
  fee: 141,
  tax: 1015,
  net_profit_loss: 8844,
  net_profit_rate: 1.77,
  cost_bp: 22.84,
  slippage_won: null,
  cost_status: 'settled',
  allocated: true,
} as never)

const ESTIMATED = makeTradePair({
  ticker: '069500',
  ticker_name: 'KODEX 200',
  strategy: 'etf_trend',
  pair_key: 'etf_trend:069500:O6',
  buy_order_nos: ['O6'],
  sell_order_nos: ['O7'],
  profit_loss: 3000,
  profit_rate: 1.0,
  fee: 85,
  tax: 0,
  net_profit_loss: 2915,
  net_profit_rate: 0.97,
  cost_bp: 2.82,
  slippage_won: null,
  cost_status: 'estimated',
  allocated: false,
} as never)

const SUMMARY = {
  realized_total_krw: 33000,
  realized_rate_pct: 2.2,
  win_count: 3,
  loss_count: 0,
  even_count: 0,
  win_rate_pct: 100,
  closed_count: 3,
  fee_sum: 427,
  tax_sum: 2448,
  realized_net_total_krw: 30125,
  realized_net_rate_pct: 2.01,
  slippage_n: 2,
}

function setup(pairs: unknown[], summary: Record<string, unknown> = SUMMARY) {
  server.use(
    http.get('/api/history/pnl', () =>
      HttpResponse.json(
        wrap({ pairs, summary, page: 1, size: 30, total: pairs.length, total_pages: 1 }),
      ),
    ),
  )
  return render(
    <TestProviders>
      <TradePnLGrid />
    </TestProviders>,
  )
}

function rowOf(pairKey: string): HTMLElement {
  const rows = screen.getAllByTestId(/^pnl-row-/)
  const found = rows.find((r) => r.textContent?.includes(pairKey.split(':')[1]))
  if (!found) throw new Error(`row for ${pairKey} not found`)
  return found
}

describe('cycle411 — TradePnLGrid 실비용 칸', () => {
  it('G1: 새 머리 칸 6개 + 기존 매매손익·손익율 칸 유지', async () => {
    setup([SETTLED])
    await screen.findByTestId('pnl-row-0')
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim())
    for (const h of ['매매손익', '손익율', '수수료', '세금', '순손익', '순손익율', '비용률', '슬리피지']) {
      expect(headers).toContain(h)
    }
  })

  it('G2: 행 값 — 순손익·순손익율·비용률·슬리피지 (기존 매매손익 = 세전 그대로)', async () => {
    setup([SETTLED])
    const row = await screen.findByTestId('pnl-row-0')
    const text = row.textContent ?? ''
    expect(text).toContain('+20,000원') // 기존 매매손익(세전)
    expect(text).toContain('+18,366원')
    expect(text).toContain('+2.62%')
    expect(text).toContain('23.01bp')
    expect(text).toContain('2,000원')
    expect(text).toContain('1,433')
  })

  it('G3: 추정·배분 배지', async () => {
    setup([SETTLED, ALLOCATED, ESTIMATED])
    await screen.findByTestId('pnl-row-2')
    const settled = rowOf('momentum:005930:O1')
    const allocated = rowOf('volatility_breakout:000660:O3')
    const estimated = rowOf('etf_trend:069500:O6')
    expect(within(estimated).getByText('추정')).toBeInTheDocument()
    expect(within(allocated).getByText('배분')).toBeInTheDocument()
    expect(within(settled).queryByText('추정')).toBeNull()
    expect(within(settled).queryByText('배분')).toBeNull()
    expect(within(estimated).queryByText('배분')).toBeNull()
  })

  it('G4: 요약 바 — 순손익 합·비용 합·슬리피지 건수', async () => {
    setup([SETTLED])
    await waitFor(() => expect(screen.getByTestId('pnl-summary-net')).toBeInTheDocument())
    expect(screen.getByTestId('pnl-summary-net').textContent).toContain('30,125')
    expect(screen.getByTestId('pnl-summary-cost').textContent).toContain('2,875')
    expect(screen.getByTestId('pnl-summary-slippage').textContent).toContain('2건')
    // 기존 실현 합계(세전) 그대로
    expect(screen.getByTestId('pnl-summary-realized').textContent).toContain('33,000')
  })

  it('G5: 새 칸이 없는 구 응답은 — 로 그린다', async () => {
    const legacy = makeTradePair()
    setup([legacy], {
      realized_total_krw: 2100,
      realized_rate_pct: 0.97,
      win_count: 1,
      loss_count: 0,
      even_count: 0,
      win_rate_pct: 100,
      closed_count: 1,
    })
    const row = await screen.findByTestId('pnl-row-0')
    expect(row.textContent).not.toContain('NaN')
    expect(row.textContent).not.toContain('undefined')
    expect(within(row).queryByText('추정')).toBeNull()
  })
})
