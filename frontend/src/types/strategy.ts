export const STRATEGY_COLORS: Record<string, { bg: string; text: string; badge: string; hex: string }> = {
  momentum: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    badge: 'bg-blue-100 text-blue-700',
    hex: '#3B82F6',
  },
  volatility_breakout: {
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    badge: 'bg-purple-100 text-purple-700',
    hex: '#8B5CF6',
  },
  long_tail_volatility: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    badge: 'bg-amber-100 text-amber-700',
    hex: '#F59E0B',
  },
  donchian_swing: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-700',
    hex: '#10B981',
  },
  bull_flag_breakout: {
    bg: 'bg-pink-50',
    text: 'text-pink-700',
    badge: 'bg-pink-100 text-pink-700',
    hex: '#EC4899',
  },
  vcp_breakout: {
    bg: 'bg-cyan-50',
    text: 'text-cyan-700',
    badge: 'bg-cyan-100 text-cyan-700',
    hex: '#06B6D4',
  },
  kojiro: {
    bg: 'bg-violet-50',
    text: 'text-violet-700',
    badge: 'bg-violet-100 text-violet-700',
    hex: '#7C3AED',
  },
}

const DEFAULT_COLOR = {
  bg: 'bg-gray-50',
  text: 'text-gray-700',
  badge: 'bg-gray-100 text-gray-700',
  hex: '#6B7280',
}

export function getStrategyColor(key: string) {
  return STRATEGY_COLORS[key] ?? DEFAULT_COLOR
}

/**
 * 사이클 F — TE(트레이딩 예지치)/RR(손익비) 전략별 최근 N개월 성과 지표.
 * 백엔드 `src/engine/te_metrics.py::TeRrMetrics` (dataclass) 1:1 매핑.
 * GET /api/strategies/te?months=3 → ApiResponse<TeRrMetrics[]>
 *
 * 관찰 전용 — 매매 hot path 무접촉. get_trade_pairs(진입가 기준·왕복) 소스.
 */
export interface TeRrMetrics {
  strategy_id: string
  n: number
  win: number
  loss: number
  even: number
  win_rate: number
  avg_win_pct: number | null
  avg_loss_pct: number | null
  te_pct: number
  te_krw_avg: number
  realized_sum_krw: number
  rr: number | null
  required_rr: number | null
  rr_margin: number | null
  rr_available: boolean
  sample_tier: 'insufficient' | 'low' | 'normal'
  verdict: 'undecided' | 'superior' | 'inferior' | 'flat'
  structure_tag: 'robust' | 'fragile' | 'balanced' | null
  single_trade_dominant: boolean
}
