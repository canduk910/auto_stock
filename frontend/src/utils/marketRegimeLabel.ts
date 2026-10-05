/**
 * cycle410 — 6장세 라벨 표시 상수(한글 이름·색). 컴포넌트 파일에서 export 하면
 * vite fast-refresh 가 깨져 여기 둔다(`utils/marketRegime.ts` 선례).
 */
import type { MarketUnitMode, RegimeLabel } from '../types/market-regime-label'

export const REGIME_LABEL_KO: Record<RegimeLabel, string> = {
  stable_up: '안정상승',
  volatile_up: '변동상승',
  stable_flat: '안정횡보',
  volatile_flat: '변동횡보',
  stable_down: '안정하락',
  volatile_down: '변동하락',
}

/** 띠 칸 색 — 상승 = 초록, 횡보 = 회색, 하락 = 빨강, 변동이면 진하게. */
export const REGIME_LABEL_COLOR: Record<RegimeLabel, string> = {
  stable_up: 'bg-emerald-300',
  volatile_up: 'bg-emerald-600',
  stable_flat: 'bg-gray-300',
  volatile_flat: 'bg-gray-500',
  stable_down: 'bg-rose-300',
  volatile_down: 'bg-rose-600',
}

export function formatSignedPct1(v: number): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

/** 시장 유닛 배수 표기 — null = 「—」. */
export function formatUnitM(m: number | null): string {
  return m == null ? '—' : `×${m}`
}

/** m 띠 칸 색 — 진할수록 랏이 크다(0 = 신규 진입 없음). */
export function unitColor(m: number | null): string {
  if (m == null) return 'bg-gray-100'
  if (m >= 1) return 'bg-sky-700'
  if (m >= 0.75) return 'bg-sky-500'
  if (m >= 0.5) return 'bg-sky-300'
  return 'bg-gray-200'
}

export const UNIT_MODE_KO: Record<MarketUnitMode, string> = {
  enforce: '적용',
  shadow: '기록만',
  off: '꺼짐',
}
