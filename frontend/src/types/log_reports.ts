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

export interface LogReportMetrics {
  target_date: string
  logs: LogReportLogMetrics
  trades: LogReportTradeMetrics
}

export interface LogReportItem {
  id: string
  target_date: string
  summary: string | null
  findings: Finding[]
  metrics: LogReportMetrics | null
  model: string | null
  created_at: string
}
