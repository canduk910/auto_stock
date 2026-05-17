import apiClient from './client'
import type { ApiResponse } from '../types/common'

/**
 * 시스템 로그 클라이언트 (사이클 6, 2026-05-17).
 *
 * /api/logs 페이징 + KST 기간 필터.
 */

export interface LogEntry {
  id: number
  timestamp: string
  log_level: string
  message: string
}

export interface LogsPayload {
  items: LogEntry[]
  total: number
  total_pages: number
}

export interface LogsFilter {
  from_date?: string | null  // YYYY-MM-DD (KST)
  to_date?: string | null    // YYYY-MM-DD (KST)
  level?: string | null      // INFO/WARNING/ERROR/CRITICAL/DEBUG
  page?: number              // 1-base
  size?: number              // 기본 50
}

const EMPTY_PAYLOAD: LogsPayload = { items: [], total: 0, total_pages: 0 }

export async function fetchLogs(filter: LogsFilter = {}): Promise<LogsPayload> {
  const params: Record<string, string | number> = {}
  if (filter.from_date) params.from_date = filter.from_date
  if (filter.to_date) params.to_date = filter.to_date
  if (filter.level) params.level = filter.level
  if (filter.page) params.page = filter.page
  if (filter.size) params.size = filter.size

  const { data } = await apiClient.get<ApiResponse<LogsPayload>>('/logs', { params })
  return data.data ?? EMPTY_PAYLOAD
}
