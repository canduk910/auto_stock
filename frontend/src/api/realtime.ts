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

/**
 * 사이클 35 (2026-05-21) — 세션별 종목 상세 정보 (UI 노출용).
 *
 * 백엔드 `/api/realtime/subscriptions` 응답의 `sessions[*].tickers_detail` 신규 필드.
 * stale 종목 우선 정렬 + cap 200 (세션당, 응답 크기 보호).
 *
 * 사이클 37 (2026-05-21) — KIS 실제 last_cntg_hour / today_volume 추가.
 * - `last_tick` (WS 수신) 과 `last_cntg_hour` (KIS 실제) 비교 → WS 구독 문제 진단.
 * - 캐시 미스 (TTL 5분 / cap 20) → null.
 */
export interface SubscriptionTickerDetail {
  ticker: string
  ticker_name: string
  stale: boolean
  // ISO KST tz, null=수신 이력 없음
  last_tick: string | null
  // 사이클 28: 연속 stale 사이클 수
  retries: number
  // 사이클 28: 마지막 강제 재구독 시각 (ISO KST | null)
  last_resub: string | null
  // 사이클 37: KIS 실제 체결시각 (HHMMSS 형식 문자열), 캐시 미스 시 null
  last_cntg_hour: string | null
  // 사이클 37: KIS 당일 누적 거래량, 캐시 미스 시 null
  today_volume: number | null
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
  // 사이클 35 — 종목별 상세 정보 (UI expand 용, cap 200)
  tickers_detail?: SubscriptionTickerDetail[]
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
  // 사이클 18 (2026-05-19, B-1) — stale 종목별 마지막 tick 시각 (ISO KST | null).
  // ScanMonitor 끊김 펼치기에서 종목별 "마지막: HH:MM:SS" 표시 + 시간대 컨텍스트 톤 분기 근거.
  last_tick_map?: Record<string, string | null>
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
