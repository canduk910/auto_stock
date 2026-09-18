/**
 * cycle303 — `/macro` 화면(macro_lite 이식 1단계) 회귀 가드.
 *
 * 팀장 명세(`_workspace/cycle303_macro_integration_spec.md` §6) 「경기사이클 보존 목록」
 * 7항목 중 계측 가능한 항목(국면 4칸·체제 4칸·강조·DivergenceNote·지표 카드 5종)과
 * 타입 계약 2가지(`data.cycle || data` 폴백, `regime?.regime` optional chaining)를 이 파일이
 * 회귀 가드로 고정한다. 나머지(나란히 배치·InfoTooltip·체제 상세)는 각 컴포넌트 소스 자체가
 * 구조를 담보한다(`MacroCycleSection.tsx` 참고).
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse, delay } from "msw"
import { server } from "../../test/server"
import MacroPage from "../MacroPage"

const MACRO_CYCLE_URL = "/api/macro/macro-cycle"
const YIELD_CURVE_URL = "/api/macro/yield-curve"
const CREDIT_SPREAD_URL = "/api/macro/credit-spread"
const CURRENCIES_URL = "/api/macro/currencies"
const COMMODITIES_URL = "/api/macro/commodities"

function baseCycleData(overrides: Record<string, unknown> = {}) {
  return {
    cycle: {
      phase: "expansion",
      phase_label: "확장기",
      phase_desc: "양의 수익률곡선, 낮은 VIX, 좁은 스프레드",
      confidence: 62,
      scores: {
        yield_curve: { score: 0.15, weight: 0.3, signal: "스프레드 +1.00%" },
        credit_spread: { score: 0.06, weight: 0.2, signal: "안정" },
        vix: { score: 0.06, weight: 0.2, signal: "18.0 (보통)" },
        sector_rotation: { score: 0.0375, weight: 0.15, signal: "혼합" },
        dollar: { score: 0.0375, weight: 0.15, signal: "보합" },
      },
      leader_sectors: ["XLK", "XLY"],
    },
    regime: {
      regime: "selective",
      regime_desc: "선별 (중립 적극)",
      params: {},
      vix: 18.0,
      buffett_ratio: 1.1,
      fear_greed_score: 50,
      buffett_level: "normal",
      fg_level: "neutral",
      credit_adjustment: null,
      credit_override: null,
    },
    updated_at: "2026-09-18T09:00:00+09:00",
    errors: [],
    ...overrides,
  }
}

function emptyYieldCurve() {
  return {
    yield_curve: { current: {}, spread_10y_3m: null, history: [], inverted: false, events: { recessions: [], bear_markets: [] } },
    updated_at: "2026-09-18T09:00:00+09:00",
    errors: [],
  }
}

function emptyCreditSpread() {
  return {
    credit_spread: {
      oas_current: null,
      oas_history_10y: [],
      oas_percentile: null,
      ig_current: null,
      hy_ig_spread: null,
      partial_failure: [],
    },
    updated_at: "2026-09-18T09:00:00+09:00",
    errors: [],
  }
}

function currenciesWith(list: unknown[]) {
  return { currencies: list, updated_at: "2026-09-18T09:00:00+09:00", errors: [] }
}

function commoditiesWith(list: unknown[]) {
  return { commodities: list, updated_at: "2026-09-18T09:00:00+09:00", errors: [] }
}

const sampleCurrency = {
  symbol: "USDKRW=X",
  name: "USD/KRW",
  price: 1300.0,
  prev_close: 1290.0,
  change: 10.0,
  change_pct: 0.7,
  sparkline: [],
}
const sampleCommodity = {
  symbol: "GC=F",
  name: "금",
  price: 2000.0,
  prev_close: 1990.0,
  change: 10.0,
  change_pct: 0.5,
  sparkline: [],
}

function mockAll(overrides: {
  cycle?: unknown
  yieldCurve?: unknown
  creditSpread?: unknown
  currencies?: unknown
  commodities?: unknown
} = {}) {
  server.use(
    http.get(MACRO_CYCLE_URL, () => HttpResponse.json(overrides.cycle ?? baseCycleData())),
    http.get(YIELD_CURVE_URL, () => HttpResponse.json(overrides.yieldCurve ?? emptyYieldCurve())),
    http.get(CREDIT_SPREAD_URL, () => HttpResponse.json(overrides.creditSpread ?? emptyCreditSpread())),
    http.get(CURRENCIES_URL, () => HttpResponse.json(overrides.currencies ?? currenciesWith([sampleCurrency]))),
    http.get(COMMODITIES_URL, () => HttpResponse.json(overrides.commodities ?? commoditiesWith([sampleCommodity]))),
  )
}

describe("MacroPage — /macro 화면 회귀 가드 (cycle303)", () => {
  beforeEach(() => {
    mockAll()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it("5개 섹션이 모두 렌더된다", async () => {
    render(<MacroPage />)

    expect(await screen.findByTestId("macro-section-cycle")).toBeTruthy()
    expect(await screen.findByTestId("macro-section-yield-curve")).toBeTruthy()
    expect(await screen.findByTestId("macro-section-credit-spread")).toBeTruthy()
    expect(await screen.findByTestId("macro-section-currency")).toBeTruthy()
    expect(await screen.findByTestId("macro-section-commodity")).toBeTruthy()
  })

  it("경기사이클이 국면 4칸 · 체제 4칸을 갖는다 (3칸으로 줄면 RED)", async () => {
    render(<MacroPage />)
    await screen.findByTestId("macro-section-cycle")

    const phaseCells = screen.getAllByTestId(/^macro-cycle-phase-/)
    expect(phaseCells).toHaveLength(4)

    const regimeCells = screen.getAllByTestId(/^macro-cycle-regime-/)
    expect(regimeCells).toHaveLength(4)
  })

  it("현재 국면/체제 칸만 나머지와 다른 강조 상태를 갖는다", async () => {
    render(<MacroPage />)
    await screen.findByTestId("macro-section-cycle")

    const phaseCells = screen.getAllByTestId(/^macro-cycle-phase-/)
    const activePhases = phaseCells.filter((el) => el.getAttribute("data-active") === "true")
    expect(activePhases).toHaveLength(1)
    expect(activePhases[0].getAttribute("data-testid")).toBe("macro-cycle-phase-expansion")
    // 강조 칸은 확대(scale-105)+진한 배경, 나머지는 흐림(opacity-60) — 클래스가 갈린다
    expect(activePhases[0].className).toContain("scale-105")
    const dimmedPhases = phaseCells.filter((el) => el !== activePhases[0])
    for (const el of dimmedPhases) {
      expect(el.className).toContain("opacity-60")
    }

    const regimeCells = screen.getAllByTestId(/^macro-cycle-regime-/)
    const activeRegimes = regimeCells.filter((el) => el.getAttribute("data-active") === "true")
    expect(activeRegimes).toHaveLength(1)
    expect(activeRegimes[0].getAttribute("data-testid")).toBe("macro-cycle-regime-selective")
  })

  it("판단 근거 지표 카드 5종이 있다", async () => {
    render(<MacroPage />)
    await screen.findByTestId("macro-section-cycle")

    const indicatorCards = screen.getAllByTestId(/^macro-cycle-indicator-/)
    expect(indicatorCards).toHaveLength(5)
    for (const key of ["yield_curve", "credit_spread", "vix", "sector_rotation", "dollar"]) {
      expect(screen.getByTestId(`macro-cycle-indicator-${key}`)).toBeTruthy()
    }
  })

  it("DivergenceNote — 국면(확장)과 체제(방어)가 엇갈리면 경고가 뜬다", async () => {
    mockAll({
      cycle: baseCycleData({
        regime: {
          regime: "defensive",
          regime_desc: "방어 (공포 현금)",
          vix: 40,
          buffett_ratio: 1.7,
          fear_greed_score: 90,
          buffett_level: "extreme",
          fg_level: "extreme_greed",
        },
      }),
    })
    render(<MacroPage />)

    expect(await screen.findByTestId("macro-cycle-divergence-note")).toBeTruthy()
  })

  it("DivergenceNote — 국면(확장)과 체제(선별 매수)가 일치하면 경고가 뜨지 않는다", async () => {
    // baseCycleData 기본값 = phase 'expansion' + regime 'selective' → 확장 국면에 매수
    // 체제라 엇갈림이 아니다(둘 다 '팽창적' 방향 — DivergenceNote 두 분기 모두 해당 없음).
    render(<MacroPage />)
    await screen.findByTestId("macro-section-cycle")

    expect(screen.queryByTestId("macro-cycle-divergence-note")).toBeNull()
  })

  it("타입 계약 2 — regime 이 없어도 깨지지 않는다", async () => {
    mockAll({ cycle: baseCycleData({ regime: null }) })
    render(<MacroPage />)

    expect(await screen.findByTestId("macro-section-cycle")).toBeTruthy()
    // RegimeDetail 은 regime=null 이면 렌더 자체를 생략한다 — 체제 칸이 전혀 없어야 한다
    expect(screen.queryAllByTestId(/^macro-cycle-regime-/)).toHaveLength(0)
    // 국면 4칸은 regime 여부와 무관하게 그대로 살아 있다
    expect(screen.getAllByTestId(/^macro-cycle-phase-/)).toHaveLength(4)
  })

  it("타입 계약 1 — data.cycle 없이 평탄한 응답(MacroCycleData 를 최상위로 바로 줌)도 깨지지 않는다", async () => {
    const flat = {
      phase: "recovery",
      phase_label: "회복기",
      phase_desc: "수익률곡선 정상화, VIX 하락, 스프레드 축소",
      confidence: 40,
      scores: {
        yield_curve: { score: 0.1, weight: 0.3, signal: "스프레드 +0.50%" },
        credit_spread: { score: 0.02, weight: 0.2, signal: "축소 중" },
        vix: { score: 0.02, weight: 0.2, signal: "14.0 (낮음)" },
        sector_rotation: { score: 0.03, weight: 0.15, signal: "경기민감주 우위" },
        dollar: { score: 0.03, weight: 0.15, signal: "약세" },
      },
      leader_sectors: [],
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    }
    mockAll({ cycle: flat })
    render(<MacroPage />)

    expect(await screen.findByTestId("macro-section-cycle")).toBeTruthy()
    const activePhases = screen
      .getAllByTestId(/^macro-cycle-phase-/)
      .filter((el) => el.getAttribute("data-active") === "true")
    expect(activePhases).toHaveLength(1)
    expect(activePhases[0].getAttribute("data-testid")).toBe("macro-cycle-phase-recovery")
  })

  it("로딩 중에는 각 섹션이 스피너를 보여준다", async () => {
    server.use(
      http.get(MACRO_CYCLE_URL, async () => {
        await delay(50)
        return HttpResponse.json(baseCycleData())
      }),
    )
    render(<MacroPage />)

    expect(screen.getByText("경기 사이클 로딩 중...")).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId("macro-section-cycle")).toBeTruthy())
  })

  it("서버 에러 시 오류 문구를 보여주고 화면이 깨지지 않는다", async () => {
    server.use(http.get(MACRO_CYCLE_URL, () => HttpResponse.json({ detail: "internal error" }, { status: 500 })))
    render(<MacroPage />)

    await waitFor(() => expect(screen.getByText(/오류:/)).toBeTruthy())
    // 다른 섹션들은 별도 도메인 실패라 영향받지 않는다
    expect(await screen.findByTestId("macro-section-currency")).toBeTruthy()
  })

  it("빈 데이터(환율/원자재 0건)는 해당 섹션을 그리지 않고 조용히 넘어간다", async () => {
    mockAll({ currencies: currenciesWith([]), commodities: commoditiesWith([]) })
    render(<MacroPage />)

    await screen.findByTestId("macro-section-cycle")
    expect(screen.queryByTestId("macro-section-currency")).toBeNull()
    expect(screen.queryByTestId("macro-section-commodity")).toBeNull()
  })
})
