/**
 * cycle387 — 종목 차트(KLineChart) 조회 API 클라이언트.
 *
 * 정본: `_workspace/red/cycle387_stock_chart_spec.md` §2.6.
 *
 * - `GET /api/stock-chart/candles?ticker=&period=&years=` 단일 엔드포인트.
 * - 백엔드는 KIS 조회 실패를 HTTP 200 + `success:false` 로 돌려준다 — 그 경우는 여기서
 *   `Error(message)` 를 던져 모달의 `useQuery` 오류 상태로 흘린다(`llm-evaluations.ts` 규약과
 *   달리 이 호출은 성공/실패를 본문으로 판정해야 하므로 예외 변환이 필요하다).
 * - axios 오류(422 검증 실패·네트워크 오류)는 **잡지 않고** 그대로 흘린다 — 모달이
 *   `axios.isAxiosError` 로 422 `detail` 을 꺼내 보여 준다.
 * - 타임아웃 60초 = 백엔드 최악 경로(대기 상한 20초 + 조회 시간 예산 25초 + 마지막 호출)가 끝나는
 *   시간. nginx `location /api/` 에는 `proxy_read_timeout` 이 없어 기본값 60초이고(120초는
 *   `/api/macro/` 전용), 이 값은 그와 같다.
 */

import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { ChartPeriod, StockChartData } from '../types/stock-chart'

export const STOCK_CHART_TIMEOUT_MS = 60_000

export const getStockChart = async (
  ticker: string,
  period: ChartPeriod,
  years = 5,
): Promise<StockChartData> => {
  const { data } = await apiClient.get<ApiResponse<StockChartData | null>>('/stock-chart/candles', {
    params: { ticker, period, years },
    timeout: STOCK_CHART_TIMEOUT_MS,
  })
  if (!data.success || !data.data) throw new Error(data.message || '차트 조회 실패')
  return data.data
}
