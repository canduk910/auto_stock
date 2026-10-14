/**
 * cycle457 — 거래일지 차트 조회 API 클라이언트(`GET /api/journal-chart`).
 *
 * 일봉 + 그 전략이 판정에 쓰는 지표 값을 한 번에 받는다. 백엔드는 KIS 조회 실패를 HTTP 200 +
 * `success:false` 로 돌려주므로 그 경우 `Error(message)` 를 던져 `useQuery` 오류 상태로 흘린다
 * (`api/stock-chart.ts` 와 같은 규약 · 같은 타임아웃).
 */

import apiClient from './client'
import { STOCK_CHART_TIMEOUT_MS } from './stock-chart'
import type { ApiResponse } from '../types/common'
import type { JournalChartData } from '../types/journal-chart'

export const getJournalChart = async (
  ticker: string,
  strategy: string,
  from: string | null,
): Promise<JournalChartData> => {
  const params: Record<string, string> = { ticker, strategy }
  if (from) params.from = from
  const { data } = await apiClient.get<ApiResponse<JournalChartData | null>>('/journal-chart', {
    params,
    timeout: STOCK_CHART_TIMEOUT_MS,
  })
  if (!data.success || !data.data) throw new Error(data.message || '차트 조회 실패')
  return data.data
}
