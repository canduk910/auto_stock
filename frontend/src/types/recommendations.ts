export type RecommendationStatus = 'pending' | 'applied' | 'rejected' | 'partial' | 'expired'

export interface RecommendationMetrics {
  trades_count?: number
  buy_count?: number
  sell_count?: number
  win_count?: number
  loss_count?: number
  win_rate?: number // 0~1
  avg_profit_pct?: number
  avg_loss_pct?: number
  max_profit_pct?: number
  max_loss_pct?: number
  stop_loss_hits?: number
  total_realized_pnl?: number
  daily_avg_return?: number
  daily_return_std?: number
  cumulative_return?: number
  analyzed_days?: number
}

export interface RecommendationItem {
  id: string
  created_at: string
  target_date: string
  strategy_id: string
  status: RecommendationStatus
  current_params: Record<string, number>
  recommended_params: Record<string, number>
  applied_params: Record<string, number> | null
  reasoning: string | null
  metrics: RecommendationMetrics | null
  applied_at: string | null
  rejected_at: string | null
}
