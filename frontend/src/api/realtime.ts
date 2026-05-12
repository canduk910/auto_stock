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
