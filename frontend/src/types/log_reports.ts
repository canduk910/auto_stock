export type Severity = 'high' | 'medium' | 'low'
export type FindingCategory =
  | 'trading'
  | 'order'
  | 'websocket'
  | 'scan'
  | 'balance'
  | 'settlement'
  | 'data_quality'
  | 'infra'
  | 'etc'

export interface Finding {
  category: FindingCategory
  severity: Severity
  title: string
  detail: string
  suggestion: string
}

export interface LogReportLogMetrics {
  level_counts: Record<string, number>
  top_patterns: Record<string, Array<{ pattern: string; count: number }>>
  samples: Record<string, Array<{ ts: string; message: string }>>
  total_logs: number
}

export interface LogReportTradeMetrics {
  trades_total: number
  buy_count: number
  sell_count: number
  realized_pnl: number
  by_strategy: Record<string, number>
  by_status: Record<string, number>
}

// cycle366 (P6) — 리포트·지표 정확도 관측. `trading_day` 는 3상태다: true=개장 /
// false=휴장 / null=판정 불가("모름", 휴장으로 단정하지 않는다). `market_closed` 는
// `trading_day === false` 일 때만 true — 0건 통계가 결함이 아니라 정상임을 알린다.
// 구버전 리포트 행에는 이 키가 없을 수 있어 optional.
export interface LogReportAccuracy {
  trading_day: boolean | null
  market_closed: boolean
  by_ticker_pnl_total_tickers: number
  by_ticker_pnl_truncated: boolean
  after_market_blind_secs_total: number
  pre_market_blind_secs_total: number
}

export interface LogReportMetrics {
  target_date: string
  logs: LogReportLogMetrics
  trades: LogReportTradeMetrics
  report_accuracy?: LogReportAccuracy
}

export interface LogReportItem {
  id: string
  target_date: string
  summary: string | null
  findings: Finding[]
  metrics: LogReportMetrics | null
  model: string | null
  created_at: string
  // cycle249 (W2, 2026-09-05) — 매일 20:20 KST Claude 루틴이
  // POST /api/log-reports/{date}/external 로 채우는 외부(Claude) 분석 필드.
  // 전부 NULL 허용 — 채워지기 전 행은 undefined/null 로 온다.
  ext_provider?: string | null
  ext_model?: string | null
  ext_summary?: string | null
  ext_findings?: Finding[] | null
  ext_report_md?: string | null
  ext_created_at?: string | null
}
