/**
 * 백테스트 관련 타입 (Phase 1).
 *
 * Phase 1 — MCP 헬스체크 응답만. Phase 2 이후 BacktestMetrics/BacktestRun/Summary 확장.
 */

export interface McpHealthResponse {
  enabled: boolean
  reachable: boolean
  tools_count: number
  error: string | null
}
