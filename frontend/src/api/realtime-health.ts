/**
 * 사이클 103 영역 0 — 실시간 건강 모니터링 API.
 *
 * system_logs prefix 검색 영역 (searchLogs API) 활용.
 * 4 prefix 각각 searchLogs 호출 → 카드별 응답 집계.
 *
 * 영속 의무:
 *   - ApiResponse data.data 추출 패턴 (사이클 84 답습)
 *   - searchLogs 기존 API 영역 영속 활용 (로그 페이지 검색과 동일 endpoint)
 */

import { searchLogs } from './logs'
import type { RealtimeHealthData, TimeWindow, RealtimeHealthLogEntry } from '../types/realtime-health'

// 4 카드 prefix 상수
const PREFIXES = {
  dispatch_drop: '[dispatch_drop_summary]',
  callback_exception: '[callback_exception]',
  stale_force_retry: '[stale_force_retry]',
  ws_auto_restart: '[ws_auto_restart]',
} as const

export type CardKey = keyof typeof PREFIXES

function windowToStart(window: TimeWindow): string {
  const now = new Date()
  if (window === '7d') {
    now.setDate(now.getDate() - 7)
  } else {
    now.setHours(now.getHours() - 24)
  }
  return now.toISOString()
}

async function fetchCardLogs(
  prefix: string,
  window: TimeWindow,
): Promise<RealtimeHealthLogEntry[]> {
  const start = windowToStart(window)
  const payload = await searchLogs({
    q: prefix,
    limit: 200,
    start,
  })
  return payload.logs.map((log) => ({
    id: log.id,
    level: log.log_level,
    message: log.message,
    created_at: log.timestamp,
  }))
}

export async function fetchRealtimeHealth(window: TimeWindow = '24h'): Promise<RealtimeHealthData> {
  // 4 카드 병렬 호출
  const [dropLogs, exceptionLogs, retryLogs, restartLogs] = await Promise.all([
    fetchCardLogs(PREFIXES.dispatch_drop, window),
    fetchCardLogs(PREFIXES.callback_exception, window),
    fetchCardLogs(PREFIXES.stale_force_retry, window),
    fetchCardLogs(PREFIXES.ws_auto_restart, window),
  ])

  return {
    dispatch_drop: {
      prefix: PREFIXES.dispatch_drop,
      logs: dropLogs,
      count: dropLogs.length,
    },
    callback_exception: {
      prefix: PREFIXES.callback_exception,
      logs: exceptionLogs,
      count: exceptionLogs.length,
    },
    stale_force_retry: {
      prefix: PREFIXES.stale_force_retry,
      logs: retryLogs,
      count: retryLogs.length,
    },
    ws_auto_restart: {
      prefix: PREFIXES.ws_auto_restart,
      logs: restartLogs,
      count: restartLogs.length,
    },
  }
}
