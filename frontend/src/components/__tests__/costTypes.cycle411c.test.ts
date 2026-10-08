/**
 * cycle411 2차 보완 Red F12 — 실비용 칸 타입 정직화.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」 F12.
 * 백엔드는 비용 조회가 실패하면 세후·비용 칸을 **`null`** 로 싣는다(B2·B4·F3·F4, 「모름」 ≠ 0).
 * 타입이 `number` 뿐이면 화면이 null 분기를 빼먹어도 컴파일이 통과한다(B3 의 `null.toFixed` 흰 화면).
 * 서버가 싣지만 화면이 아직 안 쓰는 칸(`partial_*`)도 타입에는 둔다.
 * vitest 런타임에선 타입이 지워지므로 선언 원문을 읽어 확인한다(`costsTypes.cycle411b` 와 같은 방식).
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function block(file: string, iface: string): string {
  const src = readFileSync(resolve(__dirname, '../../types', file), 'utf8')
  const m = src.match(new RegExp(`export interface ${iface}\\s*(?:extends [^{]+)?\\{([\\s\\S]*?)\\n\\}`))
  expect(m, `${file}::${iface} 없음`).not.toBeNull()
  return m![1]
}

function fieldLine(body: string, field: string): string | undefined {
  return body.split('\n').find((l) => new RegExp(`^\\s*${field}\\??\\s*:`).test(l))
}

function expectNullable(file: string, iface: string, fields: string[]) {
  const body = block(file, iface)
  for (const f of fields) {
    const line = fieldLine(body, f)
    expect(line, `${iface}.${f} 선언 없음`).toBeDefined()
    expect(line!, `${iface}.${f} 에 null 이 없다`).toMatch(/\|\s*null\b|\bnull\s*\|/)
  }
}

describe('cycle411c — 실비용 칸 타입 정직화 (F12)', () => {
  it('PerformanceSummary 세후 두 칸 = number | null', () => {
    expectNullable('trading.ts', 'PerformanceSummary', ['net_total_profit_rate', 'net_avg_daily_profit_rate'])
  })

  it('DailyPerformance 비용·세후 6칸 = … | null', () => {
    expectNullable('trading.ts', 'DailyPerformance', [
      'daily_fee', 'daily_tax', 'daily_net_pnl', 'net_daily_profit_rate',
      'net_cumulative_return_rate', 'cost_status',
    ])
  })

  it('TradeRecord 비용 칸 = … | null (CANCELLED·PENDING 행은 None)', () => {
    expectNullable('trading.ts', 'TradeRecord', ['fee', 'tax', 'net_profit_loss', 'cost_status'])
  })

  it('TradePair cost_status null · partial_fee/partial_tax/partial_sell_trade_ids 선언', () => {
    expectNullable('trading.ts', 'TradePair', ['cost_status', 'partial_fee', 'partial_tax'])
    const line = fieldLine(block('trading.ts', 'TradePair'), 'partial_sell_trade_ids')
    expect(line, 'TradePair.partial_sell_trade_ids 선언 없음').toBeDefined()
    // cycle411d — trade_history.id = UUID 문자열. costTypes.cycle411d 가 세 체결 id 칸
    // 전부(buy_trade_ids·sell_trade_ids·partial_sell_trade_ids)를 string[] 로 고정한다.
    expect(line!).toMatch(/string\[\]/)
  })

  it('TradePnLSummary.slippage_n = number | null (F4)', () => {
    expectNullable('trading.ts', 'TradePnLSummary', ['slippage_n'])
  })

  it('TeRrMetrics 세후 합·비용 합 = number | null (B4)', () => {
    expectNullable('strategy.ts', 'TeRrMetrics', ['realized_net_sum_krw', 'fee_sum', 'tax_sum'])
  })
})
