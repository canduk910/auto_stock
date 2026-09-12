/**
 * cycle285 (2026-09-13) — 야간작업 현황 API client.
 *
 * `GET /api/market-ops` 는 `market-state.ts`(cycle282, 코드 상수 표)와 별도의 엔드포인트다
 * — 이 응답은 DB/메모리 산출물이라 실패할 수 있고, 실패해도 `/api/market-state` 의 200
 * 계약을 물들이면 안 된다(백엔드 `src/routes/market_ops.py` 모듈 docstring 참조).
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketOpsData } from '../types/market-ops'

export async function fetchMarketOps(): Promise<MarketOpsData> {
  const resp = await apiClient.get<ApiResponse<MarketOpsData>>('/market-ops')
  return resp.data.data
}
