/**
 * cycle416 — 시장 등락 차트 계산 순수 함수.
 *
 * jsdom 은 recharts SVG 를 그리지 않아(폭 0) 차트에 들어가는 값은 이 순수 함수로 잰다
 * (`marketBreadthChart.test.ts`). `MarketBreadthSection.tsx` 는 이 함수들의 결과를
 * `ComposedChart` 에 그대로 넘긴다.
 *
 * ⚠️ `new Date(`·`Intl.DateTimeFormat` 금지(FG1) — 서버가 이미 KST 날짜 문자열
 * (`YYYY-MM-DD`)로 주므로 문자열 자르기만 쓴다.
 */
import type { BreadthDay, BreadthMarketKey } from '../types/market-breadth'

export interface BreadthChartRow {
  date: string
  label: string
  up: number
  /** 음수(막대를 아래로 그리기 위해) */
  down: number
  flat: number
  no_trade: number
  limit_up: number
  limit_down: number
  up_ratio_pct: number | null
}

/** `'YYYY-MM-DD'` → `'MM-DD'`. `new Date` 를 쓰지 않는다. */
export function mmdd(ymd: string): string {
  return ymd.slice(5)
}

/** `0.3252` → `'32.5%'`. null → `'—'`. */
export function formatUpRatio(ratio: number | null): string {
  if (ratio == null) return '—'
  return `${(ratio * 100).toFixed(1)}%`
}

/**
 * 응답 `days[]`(최신 먼저)를 차트용(오래된 → 최신)으로 뒤집어 행을 만든다.
 * 입력 배열은 제자리에서 바꾸지 않는다 — 표는 같은 배열을 최신 먼저 그대로 쓴다.
 */
export function buildBreadthChartRows(days: BreadthDay[], market: BreadthMarketKey): BreadthChartRow[] {
  return [...days].reverse().map((day) => {
    const stats = day[market]
    return {
      date: day.date,
      label: mmdd(day.date),
      up: stats.up,
      down: -stats.down,
      flat: stats.flat,
      no_trade: stats.no_trade,
      limit_up: stats.limit_up,
      limit_down: stats.limit_down,
      up_ratio_pct: stats.up_ratio == null ? null : stats.up_ratio * 100,
    }
  })
}

// cycle416 검증 결함(screens#4) — 1/2/5/10 만으로는 올림 간격이 최대 2배까지 벌어져
// (예: raw=2,140 → 5,000, 막대가 축의 43%만 쓴다) 중간 계단(1.2/1.5/2.5/4/6/8)을 더해
// 가장 큰 막대도 축의 80% 이상을 쓰게 좁힌다.
const NICE_STEPS = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]

/** `raw` 이상이면서 "보기 좋은 수"(NICE_STEPS × 10^n)로 올림. `raw<=0` 이면 고정 기본값. */
function niceCeil(raw: number): number {
  if (raw <= 0) return 10
  const exp = Math.floor(Math.log10(raw))
  const base = 10 ** exp
  for (const step of NICE_STEPS) {
    const candidate = step * base
    if (candidate >= raw) return candidate
  }
  return 10 * base
}

/** 대칭 축 상한 M — 창 안 max(상승, |하락|) 이상, 빈 창도 항상 > 0. */
export function breadthAxisMax(rows: BreadthChartRow[]): number {
  let raw = 0
  for (const row of rows) {
    raw = Math.max(raw, row.up, Math.abs(row.down))
  }
  return niceCeil(raw)
}
