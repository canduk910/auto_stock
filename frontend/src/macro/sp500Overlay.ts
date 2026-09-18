/**
 * S&P500 주간 종가를 매크로 차트 데이터에 겹쳐 붙이는 헬퍼 (cycle310).
 *
 * 🔴 **날짜가 정확히 맞는 경우는 거의 없다.** 금리차 history 는 1962년부터의 **주간**
 * 시리즈(3,377포인트)이고 하이일드 OAS 는 **영업일** 시리즈인데, S&P500 은 또 다른 요일에
 * 주간 종가가 찍힌다. 그래서 같은 날짜를 찾는 대신 **as-of 조인**(그 날짜 이하의 마지막
 * 종가)을 쓴다 — 금융 시계열을 겹칠 때의 표준 방식이고, 빈칸이 생겨 선이 끊기지 않는다.
 *
 * 성능 — 두 배열을 날짜 오름차순으로 한 번씩만 훑는다(투 포인터, O(n+m)).
 * 포인트마다 배열을 뒤지면 3,377 × 5,151 이 되어 화면이 눈에 띄게 굳는다.
 *
 * 🔴 차트 **앞쪽 구간에 S&P 값이 없을 수 있다**(예: 하이일드가 S&P 첫 종가보다 이르다).
 * 그 구간은 `null` 로 둔다 — 0 이나 첫 종가로 메우면 **없는 사실을 그린 선**이 된다.
 * Recharts 는 `connectNulls={false}` 에서 null 구간을 그냥 비운다.
 */
import type { Sp500Point } from "../types/macro"

/**
 * 날짜 필드가 있는 차트 포인트면 무엇이든 받는다.
 *
 * ⚠️ 인덱스 시그니처(`[k: string]: unknown`)를 **제약으로 쓰지 않는다** — 그러면
 * `YieldCurveHistoryRow` 처럼 인덱스 시그니처가 없는 보통 interface 가 전부 거부된다.
 * 필요한 것은 `date` 하나뿐이므로 그것만 요구한다.
 */
export interface DatedPoint {
  date?: string | null
}

/**
 * `rows` 각 포인트에 `sp500` 키를 더해 돌려준다(원본 불변).
 *
 * @param rows   차트 데이터 (날짜 오름차순 가정 — 아니면 정렬해서 넣는다)
 * @param sp     S&P500 주간 종가 (날짜 오름차순)
 * @param key    붙일 키 이름 (기본 `sp500`)
 */
export function attachSp500<T extends DatedPoint>(
  rows: readonly T[] | null | undefined,
  sp: readonly Sp500Point[] | null | undefined,
  key = "sp500",
): (T & Record<string, number | null>)[] {
  const src = Array.isArray(rows) ? rows : []
  if (!src.length) return []

  const series = Array.isArray(sp) ? sp.filter((p) => p && typeof p.date === "string") : []
  if (!series.length) {
    // S&P 를 못 받았으면 키를 아예 만들지 않는다 — 전 구간 null 인 선을 그리느니
    // 선 자체가 없는 편이 정직하다. 호출부는 `hasSp500` 로 Line 렌더를 가른다.
    return src as (T & Record<string, number | null>)[]
  }

  let i = 0
  let last: number | null = null
  return src.map((row) => {
    const d = typeof row.date === "string" ? row.date : null
    if (d) {
      while (i < series.length && series[i].date <= d) {
        const c = Number(series[i].close)
        if (Number.isFinite(c)) last = c
        i += 1
      }
    }
    return { ...row, [key]: last } as T & Record<string, number | null>
  })
}

/**
 * 붉은 선을 그릴 값이 실제로 하나라도 있는가 — Line 렌더 여부를 가른다.
 *
 * 인자를 `unknown[]` 으로 받는 이유 — `attachSp500` 이 덧붙이는 키는 런타임에 정해지고
 * (`key` 인자), `DatedPoint` 에는 인덱스 시그니처가 없어 그 키를 타입으로 표현할 수 없다.
 * 여기서 안전하게 좁혀 읽는다.
 */
export function hasSp500(rows: readonly unknown[] | null | undefined, key = "sp500"): boolean {
  if (!Array.isArray(rows)) return false
  return rows.some((r) => {
    if (!r || typeof r !== "object") return false
    const v = (r as Record<string, unknown>)[key]
    return typeof v === "number" && Number.isFinite(v)
  })
}
