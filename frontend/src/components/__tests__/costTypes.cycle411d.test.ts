/**
 * cycle411 3차 검증 후 LOW 결함 — 체결 id 병행 리스트 타입 정직화 (number[] → string[]).
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md`.
 *
 * `trade_history.id` 는 DB 스키마(`supabase/migrations/001_init.sql`)에서
 * `UUID DEFAULT gen_random_uuid() PRIMARY KEY` 다 — 정수가 아니다. `TradePair` 의
 * `buy_trade_ids`·`sell_trade_ids`·`partial_sell_trade_ids` 가 `number[]` 로 선언돼
 * 있던 것은 실제 값(UUID 문자열)과 타입이 어긋난 결함이다.
 *
 * vitest 런타임에선 타입이 지워지므로 선언 원문을 읽어 확인한다(`costTypes.cycle411c` 와 같은 방식).
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

describe('cycle411d — 체결 id 병행 리스트 타입 = string[] (UUID)', () => {
  it('TradePair.buy_trade_ids·sell_trade_ids·partial_sell_trade_ids = string[]', () => {
    const body = block('trading.ts', 'TradePair')
    for (const field of ['buy_trade_ids', 'sell_trade_ids', 'partial_sell_trade_ids']) {
      const line = fieldLine(body, field)
      expect(line, `TradePair.${field} 선언 없음`).toBeDefined()
      expect(line!, `TradePair.${field} 은 string[] 이어야 한다(trade_history.id = UUID)`).toMatch(/string\[\]/)
      expect(line!, `TradePair.${field} 에 number[] 가 남아 있다`).not.toMatch(/number\[\]/)
    }
  })
})
