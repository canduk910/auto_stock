/**
 * cycle276 F28 — MSW 기본 목 정직화 영구 가드.
 *
 * ## 배경 (cycle266 §C-3 재발 차단)
 * `src/test/handlers.ts` 의 `/api/history` 기본 응답이 `items` 를 돌려주고 있었다.
 * 실제 백엔드 응답과 프론트 타입(`TradeHistoryData`)은 `trades` + `total_pages` 다.
 * 목이 *의도한 계약* 이 아니라 **실제 응답**을 담지 않으면, 그리드가 빈 표를 렌더해도
 * 어떤 테스트도 깨지지 않는다 — cycle266 이 `change_rate` 문자열 직렬화 결함을
 * 3개월 넘게 초록으로 덮은 그 경로다(종목마스터 일봉 탭은 그동안 한 번도 동작하지 않았다).
 *
 * 이 가드는 목의 키 이름을 코드로 고정한다. 구현 파일이 아니라 **목**을 지키는 테스트라
 * 구현 전에도 통과한다(회귀 방지용 잠금장치).
 */

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

import { server } from '../../test/server'

const HANDLERS_PATH = path.join(__dirname, '..', '..', 'test', 'handlers.ts')

async function fetchJson(url: string): Promise<{ success: boolean; data: unknown }> {
  const res = await fetch(url)
  return (await res.json()) as { success: boolean; data: unknown }
}

describe('cycle276 F28 — MSW 기본 목 정직화', () => {
  it('/api/history 기본 응답은 trades + total_pages 를 갖는다 (items 금지)', async () => {
    const body = await fetchJson('http://localhost:3000/api/history')
    const data = body.data as Record<string, unknown>
    expect(Object.keys(data)).toContain('trades')
    expect(Object.keys(data)).toContain('total_pages')
    expect(Object.keys(data)).not.toContain('items')
    expect(Array.isArray(data.trades)).toBe(true)
    // 체결 그리드의 "AI 자문" 열은 행의 `order_no` 로 동작한다 — 목에 없으면
    // 버튼 테스트가 빈 값으로 조용히 통과한다.
    const first = (data.trades as Array<Record<string, unknown>>)[0]
    expect(typeof first.order_no).toBe('string')
    expect(first.order_no).not.toBe('')
  })

  it('/api/history/pnl 기본 응답의 페어는 buy_order_nos/sell_order_nos/pair_key 를 갖는다', async () => {
    const body = await fetchJson('http://localhost:3000/api/history/pnl')
    const data = body.data as Record<string, unknown>
    const pairs = data.pairs as Array<Record<string, unknown>>
    expect(pairs.length).toBeGreaterThan(0)
    expect(Array.isArray(pairs[0].buy_order_nos)).toBe(true)
    expect(Array.isArray(pairs[0].sell_order_nos)).toBe(true)
    expect(Object.keys(pairs[0])).toContain('pair_key')
  })

  it('/api/llm-evaluations 배치·단건 라우트가 기본 목에 등록돼 있다', async () => {
    const source = readFileSync(HANDLERS_PATH, 'utf-8')
    expect(source).toContain('${base}/llm-evaluations`')
    expect(source).toContain('${base}/llm-evaluations/:orderNo`')

    // 배치 기본값은 "기록 없음"(빈 맵) — 기본값이 전부 있음이면 비활성 분기가 죽는다.
    const batch = await fetchJson('http://localhost:3000/api/llm-evaluations?order_nos=0000123456')
    expect(batch.data).toEqual({})

    const detail = await fetchJson('http://localhost:3000/api/llm-evaluations/0000123456')
    const rec = detail.data as Record<string, unknown>
    expect(rec.order_no).toBe('0000123456')
    // 계좌번호 원문 키는 응답 표면에 존재하지 않는다(C39/C40).
    expect(Object.keys(rec)).not.toContain('account_no')
    expect(Object.keys(rec)).toContain('account_no_masked')
  })

  it('server 인스턴스가 기본 핸들러로 기동한다 (setup.ts 계약)', () => {
    expect(server).toBeDefined()
  })
})
