/**
 * cycle411 Red — 실비용 칸·새 엔드포인트의 MSW 기본 목 정직화 (handlers.honesty cycle276 원칙).
 *
 * 목은 **백엔드 실제 응답 키**를 담는다 — 의도한 계약만 담은 목은 결함을 초록으로 덮는다
 * (cycle266 §C-3). 키 정본 = `tests/unit/routes/test_cycle411_cost_overlay_routes.py`.
 *
 * 계약
 *  - MH1: `/api/history/pnl` 기본 페어에 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·
 *         `slippage_won`·`cost_status`·`allocated`·`buy_trade_ids`·`sell_trade_ids`, summary 에
 *         `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`·`slippage_n`.
 *  - MH2: `/api/performance/daily` 기본 응답은 **배열**(실제 라우트) 이고 행에 net 칸 6개.
 *  - MH3: `/api/performance/summary` 기본 응답에 `total_profit_rate`·`net_total_profit_rate`·`net_avg_daily_profit_rate`.
 *  - MH4: 새 `/api/costs/today`·`/api/costs/daily` 가 기본 목에 있다(setup 의 `onUnhandledRequest: "error"` —
 *         없으면 OrderMonitor 를 그리는 기존 테스트가 전부 붉어진다).
 *  - MH5: e2e `api-mocks.ts` 에도 `/api/costs/today` 가 등록돼 있다(백엔드 없는 E2E 의 ECONNREFUSED 방지 — 사이클 75 카드 #19').
 */

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

async function data(url: string): Promise<unknown> {
  const res = await fetch(url)
  const body = (await res.json()) as { success: boolean; data: unknown }
  expect(body.success).toBe(true)
  return body.data
}

const BASE = 'http://localhost:3000/api'

describe('cycle411 — 실비용 MSW 기본 목 정직화', () => {
  it('MH1: /api/history/pnl 페어·요약 새 칸', async () => {
    const d = (await data(`${BASE}/history/pnl`)) as {
      pairs: Array<Record<string, unknown>>
      summary: Record<string, unknown>
    }
    const keys = Object.keys(d.pairs[0])
    for (const k of [
      'fee', 'tax', 'net_profit_loss', 'net_profit_rate', 'cost_bp', 'slippage_won',
      'cost_status', 'allocated', 'buy_trade_ids', 'sell_trade_ids',
    ]) {
      expect(keys).toContain(k)
    }
    for (const k of ['fee_sum', 'tax_sum', 'realized_net_total_krw', 'realized_net_rate_pct', 'slippage_n']) {
      expect(Object.keys(d.summary)).toContain(k)
    }
  })

  it('MH2: /api/performance/daily 는 배열 + net 칸', async () => {
    const d = await data(`${BASE}/performance/daily?days=30`)
    expect(Array.isArray(d)).toBe(true)
    const rows = d as Array<Record<string, unknown>>
    expect(rows.length).toBeGreaterThan(0)
    for (const k of [
      'daily_profit_rate', 'cumulative_return_rate', 'daily_fee', 'daily_tax', 'daily_net_pnl',
      'net_daily_profit_rate', 'net_cumulative_return_rate', 'cost_status',
    ]) {
      expect(Object.keys(rows[0])).toContain(k)
    }
  })

  it('MH3: /api/performance/summary net 칸', async () => {
    const d = (await data(`${BASE}/performance/summary`)) as Record<string, unknown>
    for (const k of ['total_profit_rate', 'avg_daily_profit_rate', 'net_total_profit_rate', 'net_avg_daily_profit_rate']) {
      expect(Object.keys(d)).toContain(k)
    }
  })

  it('MH4: /api/costs/today · /api/costs/daily 기본 목', async () => {
    const today = (await data(`${BASE}/costs/today`)) as Record<string, unknown>
    for (const k of ['date', 'fee_rate', 'tax_rate', 'rate_source', 'cost_status', 'strategies', 'total']) {
      expect(Object.keys(today)).toContain(k)
    }
    expect(Object.keys(today.total as Record<string, unknown>).sort()).toEqual(
      ['fee', 'gross_pnl', 'net_pnl', 'tax'],
    )
    const daily = (await data(`${BASE}/costs/daily?from=2026-10-01&to=2026-10-08`)) as Record<string, unknown>
    expect(Object.keys(daily)).toEqual(expect.arrayContaining(['from', 'to', 'days']))
  })

  it('MH5: e2e api-mocks 에 /api/costs/today 등록', () => {
    const src = readFileSync(
      path.join(__dirname, '..', '..', '..', '..', 'e2e', 'fixtures', 'api-mocks.ts'),
      'utf-8',
    )
    expect(src).toMatch(/page\.route\(\s*["'`][^"'`]*\/api\/costs\/today/)
  })
})
