import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { McpHealthResponse } from '../types/backtest'

/**
 * 외부 MCP 백테스트 서버 헬스체크 조회.
 * 어떤 경우에도 HTTP 200 — `enabled/reachable/tools_count/error` 4필드로 상태 표시.
 * Phase 1 산출. Phase 4 백테스트 카드에서 본 함수의 reachable 로 UI 게이트.
 */
export const getMcpHealth = async (): Promise<McpHealthResponse> => {
  const { data } = await apiClient.get<ApiResponse<McpHealthResponse>>(
    '/backtest/mcp/health',
  )
  return (
    data.data ?? {
      enabled: false,
      reachable: false,
      tools_count: 0,
      error: null,
    }
  )
}
