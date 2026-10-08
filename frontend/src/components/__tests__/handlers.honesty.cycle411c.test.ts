/**
 * cycle411 2차 보완 Red F13 — MSW 기본 목이 실제 응답과 **산수까지** 맞는다.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」 F13.
 * 목은 실제 응답을 담는다(cycle266 §C-3 · handlers.honesty cycle276·411). 키만 맞고 값이 불가능한 목
 * (세후 > 세전 · 누적/당일 불일치)은 화면이 그 모순을 그려도 아무 테스트도 깨지지 않는다.
 *
 *  - MH6: `/api/history/pnl` — 페어 `net_profit_loss = profit_loss − fee − tax`, `cost_bp` 는 정의식
 *         `(fee+tax) ÷ ((매수금액+매도금액)/2) × 10⁴`(±0.05), summary 합계 = closed 페어 합
 *         (`realized_total_krw`·`realized_net_total_krw`·`fee_sum`·`tax_sum`·`closed_count`), 세후 ≤ 세전.
 *  - MH7: 그 핸들러 블록에 `as never` 캐스트가 없다(타입 불일치를 숨기지 않는다).
 *  - MH8: `/api/performance/daily` — `daily_net_pnl = daily_realized_pnl − daily_fee − daily_tax`,
 *         세후 ≤ 세전, 첫 행의 「창 이전 누적」 이 세전·세후 같다
 *         (`(1+누적)/(1+당일)` 이 두 축에서 같아야 한다 — 비용은 창 안에만 있다).
 *  - MH9: `/api/performance/summary` 세후 ≤ 세전(가드).
 *  - MH10: `/api/balance` 기본 목은 실제 모양 `{holdings: [...], summary: {7키}}` — 구 `positions`·`total_eval`
 *          `total_asset` 모양 금지. 보유가 있으면 각 행에 실비용 칸(`sell_cost_rate`·`cost_status`·`buy_fee_paid`·`buy_fee_status`).
 *  - MH11: `/api/history` 기본 행은 실제 모양 — `fee`·`cost_status`·`order_price` 키(SELL 이면 `tax`·`net_profit_loss` 도).
 */

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const BASE = 'http://localhost:3000/api'

async function data(url: string): Promise<unknown> {
  const res = await fetch(url)
  const body = (await res.json()) as { success: boolean; data: unknown }
  expect(body.success).toBe(true)
  return body.data
}

type Row = Record<string, unknown>
const n = (v: unknown) => Number(v)

describe('cycle411c — MSW 기본 목 산수 정합 (F13)', () => {
  it('MH6: /api/history/pnl 페어·요약 산수', async () => {
    const d = (await data(`${BASE}/history/pnl`)) as { pairs: Row[]; summary: Row }
    const closed = d.pairs.filter((p) => p.status === 'closed')
    for (const p of d.pairs) {
      if (p.net_profit_loss == null) continue
      expect(n(p.net_profit_loss)).toBeCloseTo(n(p.profit_loss) - n(p.fee) - n(p.tax), 6)
      expect(n(p.net_profit_loss)).toBeLessThanOrEqual(n(p.profit_loss))
      if (p.status === 'closed' && p.cost_bp != null) {
        const buy = n(p.buy_price) * n(p.buy_qty)
        const sell = n(p.sell_price) * n(p.sell_qty)
        const bp = ((n(p.fee) + n(p.tax)) / ((buy + sell) / 2)) * 1e4
        expect(Math.abs(n(p.cost_bp) - bp)).toBeLessThanOrEqual(0.05)
      }
    }
    const s = d.summary
    const sum = (k: string) => closed.reduce((a, p) => a + n(p[k]), 0)
    expect(n(s.closed_count)).toBe(closed.length)
    expect(n(s.realized_total_krw)).toBeCloseTo(sum('profit_loss'), 6)
    expect(n(s.realized_net_total_krw)).toBeCloseTo(sum('net_profit_loss'), 6)
    expect(n(s.fee_sum)).toBeCloseTo(sum('fee'), 6)
    expect(n(s.tax_sum)).toBeCloseTo(sum('tax'), 6)
    expect(n(s.realized_net_total_krw)).toBeLessThanOrEqual(n(s.realized_total_krw))
  })

  it('MH7: /history/pnl 기본 핸들러에 as never 캐스트가 없다', () => {
    const src = readFileSync(resolve(__dirname, '../../test/handlers.ts'), 'utf8')
    const start = src.indexOf('`${base}/history/pnl`')
    expect(start).toBeGreaterThan(0)
    const end = src.indexOf('http.get(', start + 10)
    const handler = src.slice(start, end > start ? end : undefined)
    expect(handler).not.toMatch(/\bas never\b/)
  })

  it('MH8: /api/performance/daily 행 산수 · 누적/당일 정합', async () => {
    const rows = (await data(`${BASE}/performance/daily?days=30`)) as Row[]
    expect(rows.length).toBeGreaterThan(0)
    for (const r of rows) {
      expect(n(r.daily_net_pnl)).toBeCloseTo(n(r.daily_realized_pnl) - n(r.daily_fee) - n(r.daily_tax), 6)
      expect(n(r.net_daily_profit_rate)).toBeLessThanOrEqual(n(r.daily_profit_rate))
      expect(n(r.net_cumulative_return_rate)).toBeLessThanOrEqual(n(r.cumulative_return_rate))
    }
    const r0 = rows[0]
    const grossPrior = (1 + n(r0.cumulative_return_rate) / 100) / (1 + n(r0.daily_profit_rate) / 100)
    const netPrior = (1 + n(r0.net_cumulative_return_rate) / 100) / (1 + n(r0.net_daily_profit_rate) / 100)
    expect(Math.abs(netPrior - grossPrior)).toBeLessThan(1e-7)
  })

  it('MH9 (가드): /api/performance/summary 세후 ≤ 세전', async () => {
    const s = (await data(`${BASE}/performance/summary`)) as Row
    expect(n(s.net_total_profit_rate)).toBeLessThanOrEqual(n(s.total_profit_rate))
    expect(n(s.net_avg_daily_profit_rate)).toBeLessThanOrEqual(n(s.avg_daily_profit_rate))
  })

  it('MH10: /api/balance 기본 목 = 실제 모양', async () => {
    const d = (await data(`${BASE}/balance`)) as Row
    expect(Object.keys(d).sort()).toEqual(['holdings', 'summary'])
    expect(Array.isArray(d.holdings)).toBe(true)
    expect(Object.keys(d.summary as Row).sort()).toEqual([
      'deposit', 'eval_total', 'net_asset', 'profit_loss_total', 'purchase_total',
      'stock_eval_amount', 'total_eval_amount',
    ])
    for (const h of d.holdings as Row[]) {
      for (const k of [
        'ticker', 'name', 'quantity', 'sellable_quantity', 'avg_price', 'purchase_amount',
        'current_price', 'eval_amount', 'eval_profit_loss', 'eval_profit_rate',
        'sell_cost_rate', 'cost_status', 'buy_fee_paid', 'buy_fee_status',
      ]) {
        expect(Object.keys(h)).toContain(k)
      }
    }
  })

  it('MH11: /api/history 기본 행 = 실제 모양(비용 칸·order_price)', async () => {
    const d = (await data(`${BASE}/history`)) as { trades: Row[] }
    expect(d.trades.length).toBeGreaterThan(0)
    for (const t of d.trades) {
      for (const k of ['fee', 'cost_status', 'order_price']) expect(Object.keys(t)).toContain(k)
      if (t.trade_type === 'SELL') {
        for (const k of ['tax', 'net_profit_loss']) expect(Object.keys(t)).toContain(k)
      }
    }
  })
})
