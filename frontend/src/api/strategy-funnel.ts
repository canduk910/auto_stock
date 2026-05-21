/**
 * 사이클 34 (2026-05-21) — 조건검색 단계별 후보 추적 API client.
 *
 * 백엔드 `/api/strategy-funnel/*` 1:1 매핑.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'

export interface ExcludedSampleRow {
  ticker: string
  reason: string
}

export interface FunnelSnapshot {
  id: string
  target_date: string
  snapshot_at?: string
  strategy_id: string
  step_no: number
  step_name: string
  survived_count: number
  excluded_count: number
  survived_tickers: string[] | null
  excluded_sample: ExcludedSampleRow[] | null
}

export interface FunnelResponse {
  target_date: string
  strategy_id: string | null
  snapshots: FunnelSnapshot[]
}

export interface FunnelRecentResponse {
  strategy_id: string
  days: number
  snapshots: FunnelSnapshot[]
}

export interface FunnelSnapshotTriggerResult {
  target_date: string
  saved: Array<{ strategy_id: string; id: string }>
  count: number
}

/**
 * 단일 영업일 단계별 후보 종목 조회.
 */
export const getFunnel = async (params: {
  target_date?: string
  strategy_id?: string
}): Promise<FunnelResponse> => {
  const qs = new URLSearchParams()
  if (params.target_date) qs.set('target_date', params.target_date)
  if (params.strategy_id) qs.set('strategy_id', params.strategy_id)
  const { data } = await apiClient.get<ApiResponse<FunnelResponse>>(
    `/strategy-funnel${qs.toString() ? `?${qs}` : ''}`,
  )
  return (
    data.data ?? {
      target_date: params.target_date ?? '',
      strategy_id: params.strategy_id ?? null,
      snapshots: [],
    }
  )
}

/**
 * 특정 전략 최근 N일 추이 조회.
 */
export const getRecentFunnel = async (
  strategy_id: string,
  days = 7,
): Promise<FunnelRecentResponse> => {
  const { data } = await apiClient.get<ApiResponse<FunnelRecentResponse>>(
    `/strategy-funnel/recent?strategy_id=${encodeURIComponent(strategy_id)}&days=${days}`,
  )
  return (
    data.data ?? {
      strategy_id,
      days,
      snapshots: [],
    }
  )
}

/**
 * 수동 trigger — 활성 전략별 최근 prepare 결과 1회 캡처.
 */
export const triggerFunnelSnapshot = async (): Promise<FunnelSnapshotTriggerResult> => {
  const { data } = await apiClient.post<ApiResponse<FunnelSnapshotTriggerResult>>(
    '/strategy-funnel/snapshot',
    {},
  )
  return (
    data.data ?? {
      target_date: '',
      saved: [],
      count: 0,
    }
  )
}
