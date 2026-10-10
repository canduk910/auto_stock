/**
 * 대시보드 경고등 API 클라이언트 (cycle434).
 *
 * 엔드포인트: GET /api/system/alerts — 오늘(KST) 장부 불일치·주문 결과 모름/
 * 청산 실패·일일 작업 실패 집계. 응답 래퍼: ApiResponse<SystemAlertsData>.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { SystemAlertsData } from '../types/system-alerts'

export async function getSystemAlerts(): Promise<SystemAlertsData> {
  const { data } = await apiClient.get<ApiResponse<SystemAlertsData>>('/system/alerts')
  return data.data
}
