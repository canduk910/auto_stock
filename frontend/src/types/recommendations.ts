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
  // Phase J4 (2026-05-12) — AI자문 고도화
  // 자동 적용 없음 — 모두 운영자 수동 검토 후 명시적 apply
  recommended_weight?: number | null  // AI 추천 전략 weight (0.0~1.0). null = 변경 권고 없음
  code_review_notes?: string | null    // 로직/파라미터 자유 텍스트 자문 (최대 2000자)
  applied_weight?: number | null       // 사용자가 apply 시점에 실제 적용한 weight (트래킹)
}
