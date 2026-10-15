/**
 * RS·재무 관찰 화면 — 칸 값 → 표시 문자열(순수 함수).
 *
 * 🔴 「모름」(null·undefined·NaN·숫자로 못 읽는 값)은 `—` 다. 0 으로 채우지 않는다.
 * 단위는 칸마다 다르다(백엔드 `rs_fundamental_observe.py` 계산 그대로):
 * - 비율(fraction) 칸 = 0.12 → `+12.0%` : RS 가중 수익 · 섹터 대비 · 목표가 상향 폭 · 목표가 중앙 변화 · YoY 둘 · TTM/최고
 * - 백분율(이미 %) 칸 = 12.3 → `12.3%` : ROE · 부채비율
 * - 백분위(0~99) 칸 = 정수 그대로
 */

/** 숫자·숫자 문자열 → 유한 number, 그 밖 → null (빈 문자열도 null). */
export function toNum(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** 비율 → 부호 붙은 백분율. 0.1234 → `+12.3%`. */
export function fmtRatioPct(v: unknown, digits = 1): string {
  const n = toNum(v)
  if (n === null) return '—'
  const p = n * 100
  return `${p > 0 ? '+' : ''}${p.toFixed(digits)}%`
}

/** 이미 백분율인 값 → `12.3%`. */
export function fmtPercent(v: unknown, digits = 1): string {
  const n = toNum(v)
  return n === null ? '—' : `${n.toFixed(digits)}%`
}

/** 정수(백분위·개수) → 그대로. */
export function fmtInt(v: unknown): string {
  const n = toNum(v)
  return n === null ? '—' : String(Math.round(n))
}

/** 참/거짓/모름 → `예`/`아니오`/`—`. */
export function fmtBool(v: unknown): string {
  if (v === true) return '예'
  if (v === false) return '아니오'
  return '—'
}

/** 결산월 `YYYYMM` → `YYYY년 M월`. 형식이 다르면 원문, 비면 `—`. */
export function fmtQuarter(v: unknown): string {
  if (typeof v !== 'string' || v.trim() === '') return '—'
  const m = /^(\d{4})(\d{2})$/.exec(v.trim())
  return m ? `${m[1]}년 ${Number(m[2])}월` : v
}

/** 부호 색(이익색·손실색)을 고를 숫자 — 모름이면 null. */
export function signOf(v: unknown): number | null {
  return toNum(v)
}

export interface SortableRow {
  role: string
  rs_pct: number | null
  ticker: string
}

/** 보유 먼저 → RS 백분위 높은 순(모름은 뒤) → 종목코드. 입력 배열은 바꾸지 않는다. */
export function sortRows<T extends SortableRow>(rows: T[]): T[] {
  return [...rows].sort((a, b) => {
    const ra = a.role === 'held' ? 0 : 1
    const rb = b.role === 'held' ? 0 : 1
    if (ra !== rb) return ra - rb
    const pa = toNum(a.rs_pct)
    const pb = toNum(b.rs_pct)
    if (pa === null && pb !== null) return 1
    if (pb === null && pa !== null) return -1
    if (pa !== null && pb !== null && pa !== pb) return pb - pa
    return a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0
  })
}
