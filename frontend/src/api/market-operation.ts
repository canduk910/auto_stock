/**
 * 사이클 186 (2026-06-29) — 장운영상태 API.
 *
 * GET /api/realtime/market-operation → MarketOperationStatus.
 * realtime-health.ts / strategy-funnel.ts 패턴 답습.
 *
 * 영속 의무:
 *   - ApiResponse data.data 추출 패턴 (사이클 84 답습)
 *   - 0건 정상 fallback (graceful)
 */

import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketOperationStatus } from '../types/market-operation'

const FALLBACK: MarketOperationStatus = {
  vi_active_count: 0,
  halt_active_count: 0,
  last_event_count: 0,
  iscd_stat_active_count: 0,
  vi_active_sample: [],
  halt_active_sample: [],
  circuit_breaker: {
    suspected: false,
    reasons: [],
    halt_ratio: 0,
    halted: 0,
    observed: 0,
    representative_mkop_cls_code: '',
    halt_reasons_sample: [],
  },
  details: [],
}

export async function fetchMarketOperationStatus(): Promise<MarketOperationStatus> {
  const res = await apiClient.get<ApiResponse<MarketOperationStatus>>(
    '/realtime/market-operation',
  )
  return res.data.data ?? FALLBACK
}
