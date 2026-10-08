/**
 * cycle411 보완 Red L3 — `CostDailyDay.cost_status` 는 nullable.
 *
 * 백엔드 `/api/costs/daily` 는 체결 없는 날을 `cost_status: null` 로 싣는다
 * (`tests/unit/routes/test_cycle411_cost_overlay_routes.py` · tester x9). 타입이 non-null 이면
 * 화면이 null 분기를 빼먹어도 컴파일이 통과한다 — 타입 선언 원문을 읽어 확인한다
 * (vitest 런타임에선 타입이 지워지므로 소스 텍스트 검사).
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('cycle411b — CostDailyDay.cost_status nullable', () => {
  it('L3: cost_status 선언에 null 이 들어 있다', () => {
    const src = readFileSync(resolve(__dirname, '../../types/costs.ts'), 'utf8')
    const block = src.match(/export interface CostDailyDay\s*\{([\s\S]*?)\n\}/)
    expect(block).not.toBeNull()
    const line = block![1].split('\n').find((l) => /^\s*cost_status\??\s*:/.test(l))
    expect(line).toBeDefined()
    expect(line!).toMatch(/\|\s*null\b|\bnull\s*\|/)
  })
})
