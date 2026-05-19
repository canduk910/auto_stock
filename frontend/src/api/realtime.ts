import apiClient from './client'
import type { ApiResponse } from '../types/common'

/**
 * Phase J2 (2026-05-12) — 수동 stale 재구독.
 *
 * 백엔드 `POST /api/realtime/resubscribe` 호출 — 60s 미수신 TICK 종목 일괄 재구독.
 * F1 자동 재구독(재연결 후 60s)과 별개의 운영자 트리거.
 *
 * 응답 data:
 *   resubscribed : 재구독 종목 수
 *   tickers      : sorted ticker 리스트
 */
export interface ResubscribeResult {
  resubscribed: number
  tickers: string[]
}

export const resubscribeStale = async (): Promise<ResubscribeResult> => {
  const { data } = await apiClient.post<ApiResponse<ResubscribeResult>>(
    '/realtime/resubscribe',
    {},
  )
  return data.data ?? { resubscribed: 0, tickers: [] }
}

/**
 * 사이클 7-B/7-D (2026-05-17/18) — WebSocket 구독 슬롯 진단 + 세션별 분해.
 *
 * 백엔드 `GET /api/realtime/subscriptions` 응답:
 * - 합집합 카운트 (메인 + 보조 N)
 * - sessions 배열로 세션별 분해 (label/subscribed/acked/fresh/stale/limit/ws_connected/reconnect_count)
 * - 보조 0개 시 sessions 길이 1 (main only)
 */
export interface SubscriptionSessionTickers {
  subscribed: string[]
  acked: string[]
}

export interface SubscriptionSession {
  label: string
  subscribed: number
  acked: number
  fresh: number
  stale: number
  limit: number
  ws_connected: boolean
  reconnect_count: number
  tickers?: SubscriptionSessionTickers
}

export interface SubscriptionsResponse {
  total: number
  acked: number
  fresh_60s: number
  stale_60s: number
  limit: number
  reconnect_count: number
  ws_connected: boolean
  sessions: SubscriptionSession[]
  tickers?: {
    subscribed: string[]
    acked: string[]
    fresh: string[]
    stale: string[]
  }
}

export const getSubscriptions = async (): Promise<SubscriptionsResponse> => {
  const { data } = await apiClient.get<ApiResponse<SubscriptionsResponse>>(
    '/realtime/subscriptions',
  )
  return (
    data.data ?? {
      total: 0,
      acked: 0,
      fresh_60s: 0,
      stale_60s: 0,
      limit: 0,
      reconnect_count: 0,
      ws_connected: false,
      sessions: [],
    }
  )
}

/**
 * 사이클 15-C-1 (2026-05-19) — REST+WS 혼합 풀 매니저 상태 조회.
 *
 * 백엔드 `GET /api/realtime/stream-status` 응답:
 * - rest:    REST 관찰 중인 종목
 * - ws:      WS 활성 종목 (min_hold_remaining_secs 노출)
 * - dropped: cooldown 중인 종목 (cooldown_remaining_secs 노출)
 */
export interface StreamEntry {
  ticker: string
  strategy: string
  reason: string
  since_secs: number
  min_hold_remaining_secs?: number
  cooldown_remaining_secs?: number
}

export interface StreamStatusResponse {
  rest: StreamEntry[]
  ws: StreamEntry[]
  dropped: StreamEntry[]
}

export const getStreamStatus = async (): Promise<StreamStatusResponse> => {
  const { data } = await apiClient.get<ApiResponse<StreamStatusResponse>>(
    '/realtime/stream-status',
  )
  return data.data ?? { rest: [], ws: [], dropped: [] }
}
