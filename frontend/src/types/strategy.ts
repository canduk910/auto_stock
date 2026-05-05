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
