import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { LogReportItem } from '../types/log_reports'

export const listLogReports = async (days = 30): Promise<LogReportItem[]> => {
  const { data } = await apiClient.get<ApiResponse<LogReportItem[]>>('/log-reports', {
    params: { days },
  })
  return data.data ?? []
}

export const getLogReport = async (targetDate: string): Promise<LogReportItem | null> => {
  const { data } = await apiClient.get<ApiResponse<LogReportItem>>(`/log-reports/${targetDate}`)
  return data.success ? (data.data ?? null) : null
}

export const runLogReport = async (): Promise<{
  success: boolean
  message: string
  data: LogReportItem | null
}> => {
  const { data } = await apiClient.post<ApiResponse<LogReportItem>>('/log-reports/run')
  return { success: data.success, message: data.message ?? '', data: data.data ?? null }
}
