/**
 * cycle276 후속 B-2 — 배치 요약 맵의 **복합 키** 규약 가드.
 *
 * 배치 요약은 날짜 없이 주문번호로 묻지만 모달 상세는 그 행의 날짜와 함께 묻는다.
 * KIS 주문번호(ODNO)는 하루 단위로만 유일하므로, 응답 맵을 주문번호 단독 키로 접으면
 * 오래된 날짜의 평가가 사라진다 — 그 행은 버튼이 비활성인데 상세 조회는 200 을 준다.
 * 그래서 라우트가 `"<trade_date>|<order_no>"` 로 키를 만들고 화면은 두 값으로 조회한다.
 */

import { readFileSync } from 'fs'
import { resolve } from 'path'
import { describe, expect, it } from 'vitest'

import {
  findLlmSummary,
  llmEvalKey,
  llmSummaryDatesFor,
} from '../../api/llm-evaluations'
import { makeLlmEvaluationSummary } from '../../test/factories'
import type { LlmEvaluationSummaryMap } from '../../types/llm-evaluation'

const ORDER = '0000123456'
const OTHER = '0000222222'

const map: LlmEvaluationSummaryMap = {
  [llmEvalKey('2026-09-11', ORDER)]: makeLlmEvaluationSummary({
    order_no: ORDER,
    trade_date: '2026-09-11',
    score: 62,
  }),
  [llmEvalKey('2026-09-08', ORDER)]: makeLlmEvaluationSummary({
    order_no: ORDER,
    trade_date: '2026-09-08',
    score: 88,
  }),
  [llmEvalKey('2026-09-11', OTHER)]: makeLlmEvaluationSummary({
    order_no: OTHER,
    trade_date: '2026-09-11',
    score: 44,
  }),
}

describe('cycle276 후속 B-2 — 복합 키 조회 헬퍼', () => {
  it('키 형식은 `날짜|주문번호` 다 (라우트 summary_key 와 같은 규약)', () => {
    expect(llmEvalKey('2026-09-11', ORDER)).toBe(`2026-09-11|${ORDER}`)
  })

  it('같은 주문번호의 두 날짜를 각각 구분해 찾는다', () => {
    expect(findLlmSummary(map, '2026-09-11', ORDER)?.score).toBe(62)
    expect(findLlmSummary(map, '2026-09-08', ORDER)?.score).toBe(88)
  })

  it('기록 없는 날짜는 undefined 다 (다른 날짜 기록을 대신 주지 않는다)', () => {
    expect(findLlmSummary(map, '2026-09-09', ORDER)).toBeUndefined()
  })

  it('날짜나 주문번호가 비면 조회하지 않는다 (빈 키로 잘못 맞추지 않게)', () => {
    expect(findLlmSummary(map, '', ORDER)).toBeUndefined()
    expect(findLlmSummary(map, null, ORDER)).toBeUndefined()
    expect(findLlmSummary(map, undefined, ORDER)).toBeUndefined()
    expect(findLlmSummary(map, '2026-09-11', '')).toBeUndefined()
  })

  it('그 주문번호로 기록이 있는 날짜 전부를 정렬해 돌려준다', () => {
    expect(llmSummaryDatesFor(map, ORDER)).toEqual(['2026-09-08', '2026-09-11'])
    expect(llmSummaryDatesFor(map, OTHER)).toEqual(['2026-09-11'])
    expect(llmSummaryDatesFor(map, '0000999999')).toEqual([])
    expect(llmSummaryDatesFor(map, '')).toEqual([])
  })

  it('두 그리드가 요약 맵을 주문번호로 직접 인덱싱하지 않는다', () => {
    // 직접 인덱싱은 복합 키 맵에서 **항상 undefined** 라 버튼이 전부 비활성이 되거나,
    // 반대로 (구 응답 형태가 섞이면) 다른 날짜 기록으로 버튼을 켠다. 조회는 헬퍼 하나로만.
    for (const rel of [
      '../../components/TradeHistoryGrid.tsx',
      '../../components/TradePnLGrid.tsx',
    ]) {
      const src = readFileSync(resolve(__dirname, rel), 'utf-8')
      expect(src).not.toMatch(/summaries\[\s*(orderNo|no)\s*\]/)
      expect(src).toContain('findLlmSummary(')
    }
  })
})
