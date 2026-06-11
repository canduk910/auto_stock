/**
 * 사이클 103 영역 0 — 실시간 건강 모니터링 타입.
 *
 * 4 카드:
 *   - dispatch_drop_summary: 메시지 누락 집계
 *   - callback_exception:    콜백 예외
 *   - stale_force_retry:     강제 재구독
 *   - ws_auto_restart:       자동 재기동
 *
 * system_logs prefix 검색 영역 활용 (searchLogs API).
 */

export interface RealtimeHealthLogEntry {
  id: number
  level: string
  message: string
  created_at: string // KST ISO
}

export interface RealtimeHealthCard {
  prefix: string
  logs: RealtimeHealthLogEntry[]
  count: number
}

export interface RealtimeHealthData {
  dispatch_drop: RealtimeHealthCard
  callback_exception: RealtimeHealthCard
  stale_force_retry: RealtimeHealthCard
  ws_auto_restart: RealtimeHealthCard
}

export type TimeWindow = '24h' | '7d'
