// DK Stock 디자인시스템 v2 (가을 팔레트) — 전략 식별 7색
export const STRATEGY_COLORS: Record<string, { bg: string; text: string; badge: string; hex: string }> = {
  momentum: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    badge: 'bg-blue-100 text-blue-700',
    hex: '#3d73b7',
  },
  volatility_breakout: {
    bg: 'bg-navy-50',
    text: 'text-navy-700',
    badge: 'bg-navy-100 text-navy-700',
    hex: '#364c6d',
  },
  long_tail_volatility: {
    bg: 'bg-beige-50',
    text: 'text-beige-700',
    badge: 'bg-beige-100 text-beige-700',
    hex: '#b39364',
  },
  donchian_swing: {
    bg: 'bg-sky-50',
    text: 'text-sky-700',
    badge: 'bg-sky-100 text-sky-700',
    hex: '#488eb4',
  },
  bull_flag_breakout: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    badge: 'bg-red-100 text-red-700',
    hex: '#c34a36',
  },
  vcp_breakout: {
    bg: 'bg-brown-50',
    text: 'text-brown-700',
    badge: 'bg-brown-100 text-brown-700',
    hex: '#9d6644',
  },
  kojiro: {
    bg: 'bg-navy-50',
    text: 'text-navy-900',
    badge: 'bg-navy-200 text-navy-900',
    hex: '#141c2b',
  },
}

const DEFAULT_COLOR = {
  bg: 'bg-gray-50',
  text: 'text-gray-700',
  badge: 'bg-gray-100 text-gray-700',
  hex: '#74716a',
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
