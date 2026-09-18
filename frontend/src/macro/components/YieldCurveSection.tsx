import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  Legend,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import LoadingSpinner from "./LoadingSpinner"
import { attachSp500, hasSp500 } from "../sp500Overlay"
import ErrorAlert from "./ErrorAlert"
import { computeEventRows, makeLabelRenderer } from "./EventLabelsOverlay"
import type {
  Sp500Point,
  YieldCurveCurrent,
  YieldCurveData,
  YieldCurveHistoryRow,
  YieldCurveResponse,
} from "../../types/macro"

// 원본 `macro_lite/components/YieldCurveSection.jsx` 이식.
// 색 hex 리터럴 → CSS 변수 치환 매핑(frontend/CLAUDE.md 「새 hex 리터럴 금지」):
//   상승/정배열 blue-500(#3b82f6) → --color-blue-500
//   역전 경고 red-500(#ef4444) → --color-red-500
//   침체 음영 gray-500(#6b7280)/gray-700(#374151) → --color-gray-500/--color-gray-700
//   스프레드 양(+) green-500(#22c55e) → green→sky 별칭 → --color-sky-500 (양수=정상 스프레드)
//   10Y 금리 라인 indigo-500(#6366f1) → indigo→navy 별칭 → --color-navy-500

const fmt = (v: number | null | undefined) =>
  v != null
    ? v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "-"

function CurrentRatesCards({ current }: { current?: YieldCurveCurrent }) {
  const entries = [
    { label: "3개월", value: current?.["3m"] },
    { label: "5년", value: current?.["5y"] },
    { label: "10년", value: current?.["10y"] },
    { label: "30년", value: current?.["30y"] },
  ]
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
      {entries.map((e) => (
        <div key={e.label} className="rounded-lg border bg-white px-4 py-3 shadow-sm">
          <div className="text-xs text-gray-500">{e.label}</div>
          <div className="text-xl font-bold text-gray-900">{fmt(e.value)}%</div>
        </div>
      ))}
    </div>
  )
}

function SpreadCard({ spread, inverted }: { spread: number | null; inverted: boolean }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm h-full flex flex-col justify-center">
      <div className="text-sm font-medium text-gray-500 mb-1">10Y-3M 스프레드</div>
      <div className={`text-3xl font-bold ${spread != null && spread < 0 ? "text-red-600" : "text-emerald-600"}`}>
        {fmt(spread)}%
      </div>
      {inverted ? (
        <div className="mt-2">
          <span className="inline-block px-2 py-1 rounded bg-red-100 text-red-700 text-xs font-semibold">
            ⚠ 역전 경고
          </span>
          <div className="text-[11px] text-gray-500 mt-1">장단기 금리 역전 — 경기 침체 선행 신호</div>
        </div>
      ) : (
        <div className="text-[11px] text-gray-500 mt-2">정상 (장기금리 &gt; 단기금리)</div>
      )}
    </div>
  )
}

function CurveShapeChart({ current }: { current?: YieldCurveCurrent }) {
  if (!current) return null
  const points = [
    { maturity: "3M", rate: current["3m"] },
    { maturity: "5Y", rate: current["5y"] },
    { maturity: "10Y", rate: current["10y"] },
    { maturity: "30Y", rate: current["30y"] },
  ].filter((p) => p.rate != null)

  // 역전 구간 감지
  const isInverted = (i: number) => i > 0 && (points[i].rate as number) < (points[i - 1].rate as number)

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-500 mb-2">수익률 곡선</div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="maturity" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} domain={["auto", "auto"]} tickFormatter={(v) => `${v}%`} />
            <Tooltip
              formatter={(v) => [`${fmt(Number(v))}%`, "수익률"]}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Line
              type="monotone"
              dataKey="rate"
              stroke="var(--color-blue-500)"
              strokeWidth={2}
              dot={(props: { cx?: number; cy?: number; index?: number }) => {
                const { cx, cy, index } = props
                const inv = index != null && isInverted(index)
                return (
                  <circle
                    key={index}
                    cx={cx}
                    cy={cy}
                    r={5}
                    fill={inv ? "var(--color-red-500)" : "var(--color-blue-500)"}
                    stroke="white"
                    strokeWidth={2}
                  />
                )
              }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// R2 (원본, 2026-05-04, 수정 2026-05-05):
// 차트 데이터의 실제 dateset 안에 있는 가장 가까운 date 로 snap.
// 이유: Recharts categorical XAxis(dataKey="date")에 데이터에 존재하지 않는 x1/x2 를 주면
//       매칭 실패 → ifOverflow="extendDomain" 이 차트 양 끝으로 확장되어 전 기간 음영.
function _snapToDataset(dataDates: Set<string>, sortedDates: string[], target: string): string | null {
  if (!sortedDates.length) return null
  if (target < sortedDates[0]) return sortedDates[0]
  if (target > sortedDates[sortedDates.length - 1]) return sortedDates[sortedDates.length - 1]
  if (dataDates.has(target)) return target
  let best = sortedDates[0]
  let bestDiff = Math.abs(new Date(target).getTime() - new Date(best).getTime())
  for (const d of sortedDates) {
    const diff = Math.abs(new Date(target).getTime() - new Date(d).getTime())
    if (diff < bestDiff) {
      best = d
      bestDiff = diff
    }
  }
  return best
}

interface ChartEvent {
  start: string
  end: string
  label: string
}

interface SnappedEvent extends ChartEvent {
  x1: string
  x2: string
}

function _eventsForChart(
  events: { recessions: ChartEvent[]; bear_markets: ChartEvent[] } | undefined,
  history: YieldCurveHistoryRow[],
): { recessions: SnappedEvent[]; bear_markets: SnappedEvent[] } {
  if (!events || !history?.length) return { recessions: [], bear_markets: [] }
  const dataDates = new Set(history.map((h) => h.date))
  const sortedDates = [...dataDates].sort()
  const minD = sortedDates[0]
  const maxD = sortedDates[sortedDates.length - 1]
  const adapt = (e: ChartEvent): SnappedEvent | null => {
    if (e.end < minD || e.start > maxD) return null
    const x1 = _snapToDataset(dataDates, sortedDates, e.start)
    const x2 = _snapToDataset(dataDates, sortedDates, e.end)
    if (!x1 || !x2 || x1 === x2) return null
    return { ...e, x1, x2 }
  }
  const recs = (events.recessions || []).map(adapt).filter((e): e is SnappedEvent => e != null)
  const bears = (events.bear_markets || []).map(adapt).filter((e): e is SnappedEvent => e != null)
  return { recessions: recs, bear_markets: bears }
}

function SpreadHistoryChart({
  history,
  events,
  sp500,
}: {
  history: YieldCurveHistoryRow[]
  events?: { recessions: ChartEvent[]; bear_markets: ChartEvent[] }
  /** cycle310 — S&P500 주간 종가. 없거나 빈 배열이면 붉은 선을 그리지 않는다. */
  sp500?: Sp500Point[] | null
}) {
  if (!history?.length) return null

  // cycle310 — S&P500 붉은 선 겹치기. as-of 조인이라 날짜가 어긋나도 선이 끊기지 않는다.
  const rows = attachSp500(history, sp500)
  const showSp = hasSp500(rows)
  // 🔴 이 차트는 1962년부터라 S&P 가 17 → 7,600(약 450배)이다. **선형축이면 1990년
  // 이전이 통째로 바닥에 깔려** 붉은 선이 오른쪽 20% 구간에만 보인다. 100년짜리 가격
  // 시계열은 로그축이 표준이다. Recharts 의 log 축은 `domain="auto"` 를 제대로 못 잡고
  // 0·음수를 만나면 축이 깨지므로 **양수만으로 도메인을 직접 계산**해 넘긴다.
  const spDomain = (() => {
    const vals = rows
      .map((r) => r.sp500)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v > 0)
    if (!vals.length) return undefined
    return [Math.min(...vals), Math.max(...vals)] as [number, number]
  })()

  const ev = _eventsForChart(events, history)
  const rowMap = computeEventRows([
    ...ev.bear_markets.map((b) => ({ kind: "bear" as const, x1: b.x1, x2: b.x2, label: b.label })),
    ...ev.recessions.map((r) => ({ kind: "rec" as const, x1: r.x1, x2: r.x2, label: r.label })),
  ])

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-500 mb-2">
        10Y-3M 스프레드 + 10Y 금리 추이
        <span className="ml-2 text-[10px] text-gray-400">■ 회색=NBER 침체 / ▼ 붉은색=S&amp;P -20% 약세장</span>
      </div>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" allowDuplicatedCategory={false} />
            {/* 좌축: 스프레드 (Area) */}
            <YAxis yAxisId="spread" tick={{ fontSize: 12 }} domain={["auto", "auto"]} tickFormatter={(v) => `${v}%`} />
            {/* 우축: 10Y 금리 (Line) — 별도 스케일로 음의 스프레드와 시각적 충돌 방지 */}
            <YAxis yAxisId="y10y" orientation="right" tick={{ fontSize: 12 }} domain={["auto", "auto"]} tickFormatter={(v) => `${v}%`} />
            {/* cycle310 — S&P500 전용 3번째 축. 단위가 %가 아니라 지수라 앞의 두 축과
                절대 섞지 않는다(섞으면 금리 1~5% 가 7,000 옆에서 직선이 된다).
                `hide` 로 눈금은 감추고 스케일만 쓴다 — 축이 셋이면 차트가 좁아진다. */}
            {showSp && spDomain && (
              <YAxis yAxisId="sp500" orientation="right" hide scale="log" domain={spDomain} allowDataOverflow />
            )}
            <Tooltip
              formatter={(v, name) =>
                String(name) === "S&P 500"
                  ? [Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 0 }), String(name)]
                  : [`${fmt(Number(v))}%`, String(name)]
              }
              labelFormatter={(l) => l}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {/* 음영 + ReferenceArea 자체 label(콜백, viewBox 수신). 글로벌 row 할당으로 충돌 회피.
                레이어 순서(bear 먼저 → rec 나중)는 원본과 동일하게 보존한다. */}
            {ev.bear_markets.map((b, i) => {
              const { row, displayLabel } = rowMap.rowDisplayFor("bear", b.x1, b.x2)
              return (
                <ReferenceArea
                  key={`bear-${i}`}
                  yAxisId="spread"
                  x1={b.x1}
                  x2={b.x2}
                  fill="var(--color-red-500)"
                  fillOpacity={0.1}
                  stroke="none"
                  ifOverflow="hidden"
                  label={makeLabelRenderer({ kind: "bear", displayLabel, row, fill: "var(--color-red-700)" })}
                />
              )
            })}
            {ev.recessions.map((r, i) => {
              const { row, displayLabel } = rowMap.rowDisplayFor("rec", r.x1, r.x2)
              return (
                <ReferenceArea
                  key={`rec-${i}`}
                  yAxisId="spread"
                  x1={r.x1}
                  x2={r.x2}
                  fill="var(--color-gray-500)"
                  fillOpacity={0.18}
                  stroke="var(--color-gray-700)"
                  strokeOpacity={0.3}
                  strokeDasharray="3 3"
                  ifOverflow="hidden"
                  label={makeLabelRenderer({ kind: "rec", displayLabel, row, fill: "var(--color-gray-700)" })}
                />
              )
            })}
            <ReferenceLine yAxisId="spread" y={0} stroke="var(--color-gray-500)" strokeDasharray="4 4" strokeWidth={1.5} />
            <defs>
              <linearGradient id="spreadPos" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-sky-500)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--color-sky-500)" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="spreadNeg" x1="0" y1="1" x2="0" y2="0">
                <stop offset="0%" stopColor="var(--color-red-500)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--color-red-500)" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <Area
              yAxisId="spread"
              type="monotone"
              dataKey="spread"
              name="10Y-3M 스프레드"
              stroke="var(--color-gray-500)"
              strokeWidth={1.5}
              fill="url(#spreadPos)"
              dot={false}
              isAnimationActive={false}
            />
            <Line
              yAxisId="y10y"
              type="monotone"
              dataKey="y10y"
              name="10Y 금리"
              stroke="var(--color-navy-500)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            {showSp && spDomain && (
              <Line
                yAxisId="sp500"
                type="monotone"
                dataKey="sp500"
                name="S&P 500"
                stroke="var(--color-red-500)"
                strokeWidth={1.5}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

interface YieldCurveSectionProps {
  data: YieldCurveResponse | null
  loading: boolean
  error: string | null
  /** cycle310 — 별도 엔드포인트라 실패 도메인이 다르다. 없으면 붉은 선만 빠진다. */
  sp500?: Sp500Point[] | null
}

export default function YieldCurveSection({ data, loading, error, sp500 }: YieldCurveSectionProps) {
  if (loading) return <LoadingSpinner message="금리 데이터 로딩 중..." />
  if (error) return <ErrorAlert message={error} />
  if (!data) return null

  // API 응답: { yield_curve: {...}, updated_at, errors }
  const yc: YieldCurveData = data.yield_curve ?? (data as unknown as YieldCurveData)

  return (
    <section data-testid="macro-section-yield-curve">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">장단기 금리차</h2>
      {/* 1행: 현재 금리 4개 카드 */}
      <CurrentRatesCards current={yc.current} />
      {/* 2행: 좌측 스프레드 카드 + 우측 수익률 곡선 (반쪽) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <SpreadCard spread={yc.spread_10y_3m} inverted={yc.inverted} />
        <CurveShapeChart current={yc.current} />
      </div>
      {/* 3행: 장단기 금리차 시계열 (전체 폭) */}
      <SpreadHistoryChart history={yc.history} events={yc.events} sp500={sp500} />
    </section>
  )
}
