/**
 * 사이클 34 (2026-05-21) — 조건검색 단계별 후보 추적 API client.
 *
 * 백엔드 `/api/strategy-funnel/*` 1:1 매핑.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'

/**
 * 사이클 41 (2026-05-22) — 종목명 + 탈락 사유 정밀 추적 확장.
 * 사이클 34 string 배열은 하위 호환 (`SurvivedItem = string | dict`).
 */
export interface SurvivedTickerRow {
  ticker: string
  name?: string  // 사이클 41 — 종목명 자동 lookup
}

export type SurvivedItem = string | SurvivedTickerRow

export interface ExcludedSampleRow {
  ticker: string
  name?: string  // 사이클 41 — 종목명 자동 lookup
  reason: string  // 사이클 41 — 수치 포함 사유
}

export interface FunnelSnapshot {
  id: string
  target_date: string
  snapshot_at?: string
  strategy_id: string
  step_no: number
  step_name: string
  step_conditions?: string | null  // 사이클 41 — UI 툴팁용 단계 조건
  survived_count: number
  excluded_count: number
  survived_tickers: SurvivedItem[] | null
  excluded_sample: ExcludedSampleRow[] | null
  // 사이클 171 (2026-06-22) — 잠정(provisional) 플래그 (migration 040)
  // true = 16:20 저녁 잠정 캡처 (전일 마스터 + 16:10 basics 기준, 아침 델타 미반영)
  // false = 09:30 자동 / 수동 trigger (확정)
  is_provisional?: boolean
}

export interface FunnelResponse {
  target_date: string
  strategy_id: string | null
  snapshots: FunnelSnapshot[]
  // 사이클 132 (2026-06-15) — 휴장일 UI 안내 영역 영구 영속 (Q3=A)
  // 영업일 = (true, null) / 휴장일 = (false, "오늘은 휴장일 ...") / 조회 실패 graceful = (true, null)
  is_business_day?: boolean
  holiday_note?: string | null
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
      is_business_day: true,  // 사이클 132 — graceful 영업일 가정
      holiday_note: null,
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
