/**
 * `sp500Overlay` 회귀 가드 (cycle310).
 *
 * 이 헬퍼가 틀리면 붉은 선이 **조용히 어긋난다** — 차트는 여전히 그려지므로 화면만 보고는
 * 알 수 없다. 그래서 as-of 조인의 경계를 숫자로 고정한다.
 */
import { describe, expect, it } from "vitest"
import { attachSp500, hasSp500 } from "../sp500Overlay"

const SP = [
  { date: "2026-01-05", close: 100 },
  { date: "2026-01-12", close: 110 },
  { date: "2026-01-26", close: 130 },
]

describe("attachSp500 — as-of 조인", () => {
  it("날짜가 정확히 맞지 않아도 그 날짜 이하의 마지막 종가를 붙인다", () => {
    const rows = [
      { date: "2026-01-05", v: 1 }, // 같은 날 → 100
      { date: "2026-01-08", v: 2 }, // 05 와 12 사이 → 여전히 100
      { date: "2026-01-12", v: 3 }, // 같은 날 → 110
      { date: "2026-01-20", v: 4 }, // 12 와 26 사이 → 110 유지 (앞의 값을 끌고 간다)
      { date: "2026-02-02", v: 5 }, // 마지막 이후 → 130 유지
    ]
    expect(attachSp500(rows, SP).map((r) => r.sp500)).toEqual([100, 100, 110, 110, 130])
  })

  it("S&P 첫 종가보다 이른 구간은 null 로 둔다 — 없는 값을 지어내지 않는다", () => {
    const rows = [
      { date: "2025-12-01", v: 0 },
      { date: "2026-01-04", v: 0 },
      { date: "2026-01-05", v: 0 },
    ]
    // 0 이나 첫 종가로 메우면 "없는 사실을 그린 선" 이 된다. null 이어야 Recharts 가 비운다.
    expect(attachSp500(rows, SP).map((r) => r.sp500)).toEqual([null, null, 100])
  })

  it("원본 배열·객체를 변형하지 않는다", () => {
    const rows = [{ date: "2026-01-12", v: 9 }]
    const out = attachSp500(rows, SP)
    expect(rows[0]).not.toHaveProperty("sp500")
    expect(out[0]).toMatchObject({ date: "2026-01-12", v: 9, sp500: 110 })
  })

  it("S&P 가 비어 있으면 키를 아예 만들지 않는다 (전 구간 null 선을 그리지 않는다)", () => {
    const rows = [{ date: "2026-01-12", v: 1 }]
    for (const empty of [[], null, undefined]) {
      const out = attachSp500(rows, empty)
      expect(out[0]).not.toHaveProperty("sp500")
      expect(hasSp500(out)).toBe(false)
    }
  })

  it("차트 데이터가 비면 빈 배열", () => {
    expect(attachSp500([], SP)).toEqual([])
    expect(attachSp500(null, SP)).toEqual([])
  })

  it("깨진 종가(NaN·문자열·음수 날짜 결측)는 건너뛰고 직전 값을 유지한다", () => {
    const dirty = [
      { date: "2026-01-05", close: 100 },
      { date: "2026-01-12", close: Number.NaN },
      { date: "2026-01-19", close: "121" as unknown as number },
      { date: "2026-01-26", close: 130 },
    ]
    const rows = [
      { date: "2026-01-12", v: 1 }, // NaN 은 채택 안 함 → 100 유지
      { date: "2026-01-19", v: 2 }, // 숫자 문자열은 Number() 로 통과 → 121
      { date: "2026-01-26", v: 3 },
    ]
    expect(attachSp500(rows, dirty).map((r) => r.sp500)).toEqual([100, 121, 130])
  })

  it("hasSp500 은 실제 숫자가 하나라도 있어야 true", () => {
    expect(hasSp500([{ date: "a", sp500: null }])).toBe(false)
    expect(hasSp500([{ date: "a", sp500: null }, { date: "b", sp500: 1 }])).toBe(true)
    expect(hasSp500(null)).toBe(false)
  })
})
