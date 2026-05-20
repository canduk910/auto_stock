/**
 * 사이클 21 (2026-05-20) — stale 시간대 컨텍스트 공용 헬퍼.
 *
 * ScanMonitor 의 사이클 18 분기를 KisAccountPoolCard 로 이전하면서 재사용 위해 분리.
 *
 * - KRX 메인 (09:00~15:30) = "결함 가능" 빨강
 * - PRE_NXT (08:00~09:00) = "거래량 적음" 노랑
 * - 그 외 (NXT 애프터 / 시간 외 / 새벽) = "한산 시 정상" 회색
 */

export type StaleContext = 'main_critical' | 'pre_open' | 'normal_quiet' | 'unknown'

export function getKstMinutes(): number {
  // 클라이언트 시간대와 무관하게 KST(Asia/Seoul) 분 단위(0~1439) 반환
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  }).formatToParts(new Date())
  const h = parseInt(parts.find((p) => p.type === 'hour')?.value ?? '0', 10)
  const m = parseInt(parts.find((p) => p.type === 'minute')?.value ?? '0', 10)
  return h * 60 + m
}

export function getStaleContextByKstMinutes(t: number): StaleContext {
  if (t >= 9 * 60 && t < 15 * 60 + 30) return 'main_critical'
  if (t >= 8 * 60 && t < 9 * 60) return 'pre_open'
  return 'normal_quiet' // 시간 외 / NXT 애프터 / 새벽
}

export const STALE_CONTEXT_META: Record<StaleContext, { label: string; cls: string }> = {
  main_critical: { label: 'KRX 메인 — stale 결함 가능', cls: 'text-red-700 bg-red-50' },
  pre_open: { label: 'NXT 프리 — 거래량 적음, 관찰', cls: 'text-yellow-700 bg-yellow-50' },
  normal_quiet: { label: '시간 외 한산 시 정상', cls: 'text-gray-600 bg-gray-50' },
  unknown: { label: '', cls: '' },
}

/**
 * 사이클 21 — stale ticker 의 last_tick ISO 를 KST HH:MM:SS 로 포맷.
 * null 또는 invalid 시 "—" 반환.
 */
export function formatLastTickKst(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(iso))
  } catch {
    return iso
  }
}
