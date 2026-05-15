/**
 * 백테스트 관련 타입 (Phase 1 + Phase 4).
 *
 * Phase 1 — McpHealthResponse (외부 MCP 서버 헬스체크).
 * Phase 4 — BacktestMetrics / BacktestSummary (자문에 동봉되는 비교 요약).
 */

export interface McpHealthResponse {
  enabled: boolean
  reachable: boolean
  tools_count: number
  error: string | null
}

/**
 * 외부 MCP 서버 `get_backtest_result_tool` 응답에서 정규화된 8개 메트릭.
 * 누락 값은 null. 백엔드 `src/models/backtest.py::BacktestMetrics` 와 1:1.
 */
export interface BacktestMetrics {
  total_return_pct: number | null
  cagr: number | null
  sharpe_ratio: number | null
  sortino_ratio: number | null
  max_drawdown: number | null
  win_rate: number | null
  profit_factor: number | null
  total_trades: number | null
}

/**
 * Phase 3 — `parameter_recommendations.backtest_summary` JSONB 영속화 구조.
 *
 * - `current` / `recommended`: 전략별 메트릭 (또는 null — (b) 폴백 / 백테스트 실패)
 * - `diff`: `recommended - current` 계산 결과 (전략별 부분 dict)
 * - 자기 전략 두 row 모두 종료 상태일 때만 동봉됨 → 진행중이면 본 객체 자체가 null
 */
export interface BacktestSummary {
  current: Record<string, BacktestMetrics | null>
  recommended: Record<string, BacktestMetrics | null>
  diff: Record<string, Partial<BacktestMetrics>>
}

/** 8 메트릭 키 — diff/렌더 순서 통일용 */
export const BACKTEST_METRIC_KEYS: ReadonlyArray<keyof BacktestMetrics> = [
  'total_return_pct',
  'cagr',
  'sharpe_ratio',
  'sortino_ratio',
  'max_drawdown',
  'win_rate',
  'profit_factor',
  'total_trades',
]
