import { useState } from "react"
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import LoadingSpinner from "./LoadingSpinner"
import ErrorAlert from "./ErrorAlert"
import { formatKstDateTime } from "../../utils/kst"
import { breadthAxisMax, buildBreadthChartRows, formatUpRatio, mmdd } from "../marketBreadthChart"
import type { BreadthChartRow } from "../marketBreadthChart"
import type { BreadthMarketKey, MarketBreadthData } from "../../types/market-breadth"

// cycle416 — 매크로 6번째 섹션 「시장 등락 통계」(KRX 공개 API 일별 매매정보 집계, 관찰 전용).
// 전 종목 스캔이라 조회가 다른 섹션보다 느릴 수 있어(최대 45초) 섹션 래퍼는 로딩·실패·정상
// 모든 상태에서 보여 "무엇을 기다리는지"를 알린다(다른 5섹션과 다른 점).

const RED_CLASS = "text-red-600"
const BLUE_CLASS = "text-blue-600"

const MARKET_LABELS: Record<BreadthMarketKey, string> = {
  kospi: "코스피",
  kosdaq: "코스닥",
  total: "합계",
}

const MARKET_ORDER: BreadthMarketKey[] = ["kospi", "kosdaq", "total"]

type ColumnKey = "up" | "down" | "flat" | "limit_up" | "limit_down" | "no_trade"

const COLUMNS: { key: ColumnKey; label: string; colorClass?: string }[] = [
  { key: "up", label: "상승", colorClass: RED_CLASS },
  { key: "down", label: "하락", colorClass: BLUE_CLASS },
  { key: "flat", label: "보합" },
  { key: "limit_up", label: "상한가", colorClass: RED_CLASS },
  { key: "limit_down", label: "하한가", colorClass: BLUE_CLASS },
  { key: "no_trade", label: "거래 없음" },
]

// 검증 결함(screens#1·trader#4) — 기본 <Tooltip/> 은 하락을 음수로("하락 : -625"), 비율을 "%" 없이
// 보여준다. 명세 §6.2-4 「날짜 · 상승 n(상한가 m) · 하락 n(하한가 m) · 보합 · 거래 없음 · 상승 비율 %」를
// 그대로 그리는 커스텀 툴팁으로 바꾼다.
function BreadthTooltip({ active, payload }: { active?: boolean; payload?: { payload: BreadthChartRow }[] }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  return (
    <div className="rounded-lg border bg-white px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 font-medium text-gray-700">{row.label}</div>
      <div className={RED_CLASS}>
        상승 {row.up.toLocaleString()}
        {row.limit_up > 0 ? `(상한가 ${row.limit_up.toLocaleString()})` : ""}
      </div>
      <div className={BLUE_CLASS}>
        하락 {Math.abs(row.down).toLocaleString()}
        {row.limit_down > 0 ? `(하한가 ${row.limit_down.toLocaleString()})` : ""}
      </div>
      <div className="text-gray-600">보합 {row.flat.toLocaleString()}</div>
      <div className="text-gray-600">거래 없음 {row.no_trade.toLocaleString()}</div>
      <div className="text-gray-600">상승 비율 {formatUpRatio(row.up_ratio_pct == null ? null : row.up_ratio_pct / 100)}</div>
    </div>
  )
}

// recharts `LabelList` 의 `content` 콜백 타입은 패키지 안에서만 쓰이는 제네릭이라 여기서
// 그대로 흉내 내지 않는다 — 실제로 넘어오는 필드(x·y·width·height·value)만 느슨하게 받는다.
const num = (v: unknown): number => (v == null ? 0 : Number(v))

// 검증 결함(trader#5) — 상한가·하한가 막대 라벨. 0 이면 아무것도 그리지 않는다(명세 §6.2-4).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function LimitUpLabel(props: any) {
  const x = num(props?.x)
  const y = num(props?.y)
  const width = num(props?.width)
  const value = props?.value as number | string | undefined
  if (!value) return null
  return (
    <text x={x + width / 2} y={y - 4} textAnchor="middle" fontSize={10} fill="var(--color-red-700)">
      {value}
    </text>
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function LimitDownLabel(props: any) {
  const x = num(props?.x)
  const y = num(props?.y)
  const width = num(props?.width)
  const height = num(props?.height)
  const value = props?.value as number | string | undefined
  if (!value) return null
  return (
    <text x={x + width / 2} y={y + height + 10} textAnchor="middle" fontSize={10} fill="var(--color-blue-700)">
      {value}
    </text>
  )
}

interface MarketBreadthSectionProps {
  data: MarketBreadthData | null
  loading: boolean
  error: string | null
  days?: number
}

export default function MarketBreadthSection({ data, loading, error, days = 20 }: MarketBreadthSectionProps) {
  const [market, setMarket] = useState<BreadthMarketKey>("total")

  return (
    <section data-testid="macro-section-market-breadth">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">시장 등락 통계</h2>
      {loading && <LoadingSpinner message={`최근 ${days}영업일 전 종목 시세를 받는 중...`} />}
      {!loading && error && <ErrorAlert message={error} />}
      {!loading && !error && data && <BreadthBody data={data} market={market} onMarketChange={setMarket} />}
    </section>
  )
}

function BreadthBody({
  data,
  market,
  onMarketChange,
}: {
  data: MarketBreadthData
  market: BreadthMarketKey
  onMarketChange: (m: BreadthMarketKey) => void
}) {
  const summary = data.summary[market]
  const chartRows = buildBreadthChartRows(data.days, market)
  const axisMax = breadthAxisMax(chartRows)
  const adrLabel = summary.n_days === data.window.requested ? "ADR" : `ADR(${summary.n_days}일)`
  const adrValue = summary.adr == null ? "—" : summary.adr.toFixed(1)
  const showMissing = data.missing_dates.length > 0
  const showShort = !showMissing && !data.window.complete

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 text-sm text-gray-500 mb-3">
        <span>
          {data.window.from}~{data.window.to}
        </span>
        <span>·</span>
        <span>{data.window.n_days}영업일</span>
        <span>·</span>
        <span>KRX</span>
        <span>·</span>
        <span>기준 {formatKstDateTime(data.asof_kst)}</span>
      </div>

      <div className="flex gap-2 mb-4">
        {MARKET_ORDER.map((m) => (
          <button
            key={m}
            type="button"
            data-testid={`breadth-market-${m}`}
            aria-pressed={market === m}
            onClick={() => onMarketChange(m)}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              market === m
                ? "bg-gray-900 text-white border-gray-900"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
            }`}
          >
            {MARKET_LABELS[m]}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 mb-4">
        <div data-testid="breadth-chip-adr" className="rounded-lg border bg-white px-3 py-2 text-sm">
          <span className="text-gray-500">{adrLabel}</span> <span className="font-semibold">{adrValue}</span>
        </div>
        <div data-testid="breadth-chip-up" className={`rounded-lg border bg-white px-3 py-2 text-sm font-semibold ${RED_CLASS}`}>
          상승 {summary.up.toLocaleString()}
        </div>
        <div data-testid="breadth-chip-down" className={`rounded-lg border bg-white px-3 py-2 text-sm font-semibold ${BLUE_CLASS}`}>
          하락 {summary.down.toLocaleString()}
        </div>
        <div data-testid="breadth-chip-limit-up" className={`rounded-lg border bg-white px-3 py-2 text-sm ${RED_CLASS}`}>
          상한가 {summary.limit_up.toLocaleString()}
        </div>
        <div data-testid="breadth-chip-limit-down" className={`rounded-lg border bg-white px-3 py-2 text-sm ${BLUE_CLASS}`}>
          하한가 {summary.limit_down.toLocaleString()}
        </div>
        <div data-testid="breadth-chip-up-ratio" className="rounded-lg border bg-white px-3 py-2 text-sm">
          상승 비율 {formatUpRatio(summary.up_ratio)}
        </div>
      </div>

      {showMissing && (
        <div
          data-testid="breadth-missing"
          className="mb-3 rounded border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-800"
        >
          {data.missing_dates.length}일 자료를 받지 못했습니다: {data.missing_dates.map(mmdd).join(', ')} — 잠시 뒤 새로 고치면 채워질 수 있습니다
        </div>
      )}

      <div data-testid="breadth-chart" data-market={market} className="h-64 mb-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartRows}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-gray-200)" />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis
              yAxisId="count"
              domain={[-axisMax, axisMax]}
              fontSize={12}
              tickFormatter={(v: number) => Math.abs(v).toLocaleString()}
            />
            <YAxis
              yAxisId="ratio"
              orientation="right"
              domain={[0, 100]}
              ticks={[0, 50, 100]}
              tickFormatter={(v: number) => `${v}%`}
              fontSize={12}
            />
            <ReferenceLine yAxisId="ratio" y={50} stroke="var(--color-gray-400)" strokeDasharray="3 3" />
            <Tooltip content={<BreadthTooltip />} />
            <Legend />
            <Bar yAxisId="count" dataKey="up" name="상승" fill="var(--color-red-500)">
              <LabelList dataKey="limit_up" content={LimitUpLabel} />
            </Bar>
            <Bar yAxisId="count" dataKey="down" name="하락" fill="var(--color-blue-500)">
              <LabelList dataKey="limit_down" content={LimitDownLabel} />
            </Bar>
            <Line
              yAxisId="ratio"
              dataKey="up_ratio_pct"
              name="상승 비율"
              stroke="var(--color-gray-700)"
              dot={{ r: 2, fill: "var(--color-gray-700)" }}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {showShort && (
        <div data-testid="breadth-short" className="mb-3 text-sm text-gray-500">
          요청한 영업일을 다 채우지 못해 {data.window.n_days}일뿐 보여드립니다
        </div>
      )}
      {data.pending_date && (
        <div data-testid="breadth-pending" className="mb-3 text-sm text-gray-500">
          {mmdd(data.pending_date)} 자료는 아직 KRX 에 올라오지 않았습니다(보통 다음 날 아침 8시쯤 — 휴장일이었다면 그대로 빠집니다)
        </div>
      )}

      <div className="overflow-x-auto">
        <table data-testid="breadth-table" className="min-w-[560px] w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th scope="col" className="py-1 pr-3">날짜</th>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" className="py-1 pr-3 text-right">
                  {c.label}
                </th>
              ))}
              <th scope="col" className="py-1 pr-3 text-right">상승 비율</th>
            </tr>
          </thead>
          <tbody>
            {data.days.map((day) => {
              const stats = day[market]
              return (
                <tr key={day.date} data-testid={`breadth-row-${day.date}`} className="border-b border-gray-100">
                  <td data-testid="breadth-cell-date" className="py-1 pr-3">
                    {mmdd(day.date)}
                  </td>
                  {COLUMNS.map((c) => (
                    <td
                      key={c.key}
                      data-testid={`breadth-cell-${c.key}`}
                      className={`py-1 pr-3 text-right ${c.colorClass ?? ""}`}
                    >
                      {stats[c.key].toLocaleString()}
                    </td>
                  ))}
                  <td data-testid="breadth-cell-up_ratio" className="py-1 pr-3 text-right">
                    {formatUpRatio(stats.up_ratio)}
                  </td>
                </tr>
              )
            })}
            <tr data-testid="breadth-row-total" className="font-semibold">
              <td data-testid="breadth-cell-date" className="py-1 pr-3">
                {summary.n_days}일 합계
              </td>
              {COLUMNS.map((c) => (
                <td
                  key={c.key}
                  data-testid={`breadth-cell-${c.key}`}
                  className={`py-1 pr-3 text-right ${c.colorClass ?? ""}`}
                >
                  {summary[c.key].toLocaleString()}
                </td>
              ))}
              <td data-testid="breadth-cell-up_ratio" className="py-1 pr-3 text-right">
                {formatUpRatio(summary.up_ratio)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p data-testid="breadth-footnote" className="mt-2 text-xs text-gray-500">
        ADR = 기간 상승 종목 수 합 ÷ 하락 종목 수 합 × 100. 업계 통상 기준선 {data.adr_reference.oversold} 이하
        침체권 · {data.adr_reference.overheated} 이상 과열권(보조 지표, 단독 판단 기준 아님). 이 화면 방식의 과거
        20일 ADR 중앙값(2020-10~2025-10): 코스피 92 · 코스닥 88 · 합계 89. 상한가·하한가는 그날 ±30% 가격제한폭
        값에 닫힌 종목(신규상장일·정리매매 제외), 거래 없음은 거래량 0 종목.
      </p>
    </div>
  )
}
