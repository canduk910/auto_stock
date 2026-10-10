/**
 * 대시보드 경고등 타입 (cycle434).
 *
 * 백엔드 `src/engine/alert_markers.py::build_summary`/`unknown_summary` 1:1 매핑.
 * 응답은 `GET /api/system/alerts` → `ApiResponse<SystemAlertsData>`.
 */

export type AlertSignalColor = 'red' | 'yellow'

export type AlertSignalStatus = 'red' | 'yellow' | 'green' | 'unknown'

export interface AlertRecentMessage {
  level: string | null
  message: string
  timestamp: string | null
}

export interface AlertCategorySummary {
  key: string
  label: string
  color: AlertSignalColor
  // count/max_level 이 null 이면 "모름"(DB 조회 실패) — 0 과 구분한다.
  count: number | null
  max_level: string | null
  first_at: string | null
  last_at: string | null
  recent_messages: AlertRecentMessage[]
}

export interface SystemAlertsData {
  as_of: string
  status: AlertSignalStatus
  categories: AlertCategorySummary[]
}
