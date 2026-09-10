/**
 * 사이클 F — TE(트레이딩 예지치)/RR(손익비) 전략별 성과 API client.
 *
 * 백엔드 `GET /api/strategies/te?months=3` 1:1 매핑. 관찰 전용.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { TeRrMetrics } from '../types/strategy'
import type { ParamsSchemaData } from '../types/strategy-params'

export async function getStrategyTeRr(months = 3): Promise<TeRrMetrics[]> {
  const resp = await apiClient.get<ApiResponse<TeRrMetrics[]>>('/strategies/te', {
    params: { months },
  })
  return resp.data.data
}

/**
 * cycle278 — 전략 파라미터 카탈로그 스키마.
 *
 * `GET /api/strategies/params-schema` 1회로 (a) 99키 스펙 (b) 전략별 적용 키·현재값·기본값
 * (c) 닫힌 어휘(그룹·타입·단위·리스크) (d) 불변식을 모두 받는다. 편집 화면은 **이 한 응답**으로
 * 렌더한다 — 현재값을 `GET /api/strategies`(staleTime 15s + 60s 폴링)에서 따로 읽으면
 * 변경분 미리보기가 낡은 기준값으로 계산된다.
 */
export async function getStrategyParamsSchema(): Promise<ParamsSchemaData> {
  const resp = await apiClient.get<ApiResponse<ParamsSchemaData>>('/strategies/params-schema')
  return resp.data.data
}
