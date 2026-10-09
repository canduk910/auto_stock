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
  /** 호출 실패로 빠진 날(응답 `missing_dates`) — x축 자리를 0/null 로 비워 둔 칸. */
  missing: boolean
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
 *
 * `missingDates`(= 응답 `missing_dates`, cycle418-B 남은 결함 #2) — 호출 실패로 빠진 날을
 * 0/null · `missing=true` 칸으로 x축에 끼워 넣는다. 영업일 달력을 새로 계산하지 않고 응답이
 * 이미 준 두 날짜 배열(`days` + `missing_dates`)만 `YYYY-MM-DD` 문자열 그대로 정렬해 합친다 —
 * 출처는 응답 하나다. `days[]` 에 이미 있는 날짜는 중복으로 끼우지 않는다(정상 입력에서는
 * 두 배열이 겹치지 않지만, 겹치는 입력이 와도 x축에 같은 날짜 칸이 두 번 생기지 않게 막는다).
 */
export function buildBreadthChartRows(
  days: BreadthDay[],
  market: BreadthMarketKey,
  missingDates: string[] = [],
): BreadthChartRow[] {
  const present: BreadthChartRow[] = [...days].reverse().map((day) => {
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
      missing: false,
    }
  })
  const presentDates = new Set(present.map((row) => row.date))
  const gaps: BreadthChartRow[] = missingDates
    .filter((date) => !presentDates.has(date))
    .map((date) => ({
      date,
      label: mmdd(date),
      up: 0,
      down: 0,
      flat: 0,
      no_trade: 0,
      limit_up: 0,
      limit_down: 0,
      up_ratio_pct: null,
      missing: true,
    }))
  return [...present, ...gaps].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
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
