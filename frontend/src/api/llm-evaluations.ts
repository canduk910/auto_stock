/**
 * cycle276 — AI 매수평가(LLM shadow) 기록 조회 API 클라이언트.
 *
 * 정본 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §5 / §10.2.
 *
 * - 배치 요약(`GET /api/llm-evaluations?order_nos=…`) = 그리드 한 페이지의 버튼 활성/비활성을
 *   **한 요청**으로 정한다. 행마다 개별 조회하면 페이지당 20~30 요청이 나간다(명세 §10.3).
 *   기록이 없는 주문번호는 응답 맵에 **키 자체가 없다** — "있음/없음" 이 곧 버튼 상태다.
 * - 단건 상세(`GET /api/llm-evaluations/{order_no}`) = 팝업이 열릴 때만 부른다.
 * - **try/catch 를 두지 않는다** — axios 오류를 React Query 로 흘려 보내야 404(회색 안내)와
 *   500·네트워크(빨강 오류)를 화면이 구분할 수 있다(cycle266 정본). 여기서 삼키면
 *   "적재 대상 아님" 과 "서버 장애" 가 같은 화면이 된다.
 * - `apiClient` 단일 인스턴스만 쓰고 인터셉터를 추가하지 않는다(리포 관례).
 */

import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type {
  LlmEvaluation,
  LlmEvaluationSummary,
  LlmEvaluationSummaryMap,
} from '../types/llm-evaluation'

/**
 * 배치 요약 맵의 키 = `"<trade_date>|<order_no>"` (라우트 `summary_key()` 와 같은 규약).
 *
 * 주문번호 **단독** 키는 쓸 수 없다 — KIS 주문번호(ODNO)는 하루 단위로만 유일해서 같은
 * 번호가 여러 날짜에 존재하고, 단독 키로 접으면 한 날짜의 평가만 남는다. 그러면 나머지
 * 날짜의 행은 버튼이 비활성인데 상세 조회(날짜와 함께 묻는다)로는 멀쩡히 답을 받는다.
 */
export const llmEvalKey = (tradeDate: string | null | undefined, orderNo: string): string =>
  `${tradeDate ?? ''}|${orderNo}`

/** 그 날짜·그 주문번호의 요약. 둘 중 하나라도 비면 `undefined`(대조 불가). */
export const findLlmSummary = (
  summaries: LlmEvaluationSummaryMap,
  tradeDate: string | null | undefined,
  orderNo: string,
): LlmEvaluationSummary | undefined => {
  if (!tradeDate || !orderNo) return undefined
  return summaries[llmEvalKey(tradeDate, orderNo)]
}

/**
 * 그 주문번호로 기록이 있는 **날짜 전부**(정렬·중복 제거). 비활성 사유를 "기록이 아예
 * 없다" 와 "다른 날짜의 기록이다" 로 가르는 데 쓴다 — 후자를 "기록 없음" 이라고 말하면
 * 반대 방향의 거짓말이 된다. 맵은 페이지 상한 200건이라 전체 순회 비용이 무의미하다.
 */
export const llmSummaryDatesFor = (
  summaries: LlmEvaluationSummaryMap,
  orderNo: string,
): string[] => {
  if (!orderNo) return []
  const dates = new Set<string>()
  for (const s of Object.values(summaries)) {
    if (s && s.order_no === orderNo && s.trade_date) dates.add(s.trade_date)
  }
  return Array.from(dates).sort()
}

/**
 * 배치 요약 조회. 주문번호가 없으면 **요청을 만들지 않는다**(빈 CSV 는 라우트가 422 로 거부).
 *
 * 응답 맵의 키는 `llmEvalKey()` 복합 키다 — 조회는 `findLlmSummary()` 로 한다.
 */
export const getLlmEvaluationSummaries = async (
  orderNos: string[],
  tradeDate?: string,
): Promise<LlmEvaluationSummaryMap> => {
  if (orderNos.length === 0) return {}
  const { data } = await apiClient.get<ApiResponse<LlmEvaluationSummaryMap>>(
    '/llm-evaluations',
    { params: { order_nos: orderNos.join(','), trade_date: tradeDate } },
  )
  return data.data ?? {}
}

/** 단건 상세 조회. 기록이 없으면 라우트가 404 를 준다(호출부가 회색 안내로 분기). */
export const getLlmEvaluation = async (
  orderNo: string,
  tradeDate?: string,
): Promise<LlmEvaluation> => {
  const { data } = await apiClient.get<ApiResponse<LlmEvaluation>>(
    `/llm-evaluations/${orderNo}`,
    { params: { trade_date: tradeDate } },
  )
  return data.data
}
