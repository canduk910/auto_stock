import { useState } from "react"
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import LoadingSpinner from "./LoadingSpinner"
import ErrorAlert from "./ErrorAlert"
import { formatKstDateTime } from "../../utils/kst"
import { breadthAxisMax, buildBreadthChartRows, formatUpRatio, mmdd } from "../marketBreadthChart"
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

      <div data-testid="breadth-chart" data-market={market} className="h-64 mb-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartRows}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-gray-200)" />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis yAxisId="count" domain={[-axisMax, axisMax]} fontSize={12} />
            <YAxis yAxisId="ratio" orientation="right" domain={[0, 100]} fontSize={12} hide />
            <Tooltip />
            <Legend />
            <Bar yAxisId="count" dataKey="up" name="상승" fill="var(--color-red-500)" />
            <Bar yAxisId="count" dataKey="down" name="하락" fill="var(--color-blue-500)" />
            <Line
              yAxisId="ratio"
              dataKey="up_ratio_pct"
              name="상승 비율"
              stroke="var(--color-gray-700)"
              dot={false}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {showMissing && (
        <div
          data-testid="breadth-missing"
          className="mb-3 rounded border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-800"
        >
          {data.missing_dates.length}일 자료를 받지 못했습니다: {data.missing_dates.map(mmdd).join(', ')}
        </div>
      )}
      {showShort && (
        <div data-testid="breadth-short" className="mb-3 text-sm text-gray-500">
          요청한 영업일을 다 채우지 못해 {data.window.n_days}일뿐 보여드립니다
        </div>
      )}
      {data.pending_date && (
        <div data-testid="breadth-pending" className="mb-3 text-sm text-gray-500">
          {mmdd(data.pending_date)} 자료는 아직 KRX 에 올라오지 않았습니다 — 다음 영업일 10시 이후 반영됩니다
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
        ADR 참고선 — 하단 {data.adr_reference.oversold} · 상단 {data.adr_reference.overheated}(보조 지표, 단독 판단 기준 아님)
      </p>
    </div>
  )
}
