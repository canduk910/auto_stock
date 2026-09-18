import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts"
import LoadingSpinner from "./LoadingSpinner"
import ErrorAlert from "./ErrorAlert"
import type { CommoditiesResponse, CommodityQuote } from "../../types/macro"

// 원본 `macro_lite/components/CommoditySection.jsx` 이식.
// 색 hex 리터럴 → CSS 변수 치환은 CurrencySection.tsx 와 동일 규약(frontend/CLAUDE.md).

const fmt = (v: number | null | undefined) =>
  v != null
    ? v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "-"

function CommodityCard({ item }: { item: CommodityQuote }) {
  const { symbol, name, price, change, change_pct, sparkline } = item
  const isUp = change > 0
  const isDown = change < 0
  const color = isUp ? "var(--color-red-500)" : isDown ? "var(--color-blue-500)" : "var(--color-gray-500)"
  const sign = isUp ? "+" : ""
  const gradId = `comm-${symbol.replace(/[^a-zA-Z0-9]/g, "")}`

  const chartData = (sparkline || []).map((point, i) =>
    typeof point === "object" ? point : { i, v: point },
  )

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-500 mb-1">{name}</div>
      <div className="text-2xl font-bold text-gray-900">{fmt(price)}</div>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm font-semibold" style={{ color }}>
          {change != null ? `${sign}${fmt(change)}` : ""}
        </span>
        <span className="text-sm" style={{ color }}>
          {change_pct != null ? `(${sign}${change_pct.toFixed(2)}%)` : ""}
        </span>
      </div>
      {chartData.length > 0 && (
        <div className="mt-3 h-16">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <YAxis domain={["dataMin", "dataMax"]} hide />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.[0]) return null
                  const d = payload[0].payload as { date?: string; v: number }
                  return (
                    <div className="rounded bg-gray-800 text-white text-xs px-2 py-1 shadow">
                      {d.date && <div>{d.date}</div>}
                      <div className="font-semibold">{fmt(d.v)}</div>
                    </div>
                  )
                }}
                cursor={{ stroke: "var(--color-gray-400)", strokeWidth: 1 }}
              />
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                stroke={color}
                strokeWidth={1.5}
                fill={`url(#${gradId})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

interface CommoditySectionProps {
  data: CommoditiesResponse | null
  loading: boolean
  error: string | null
}

export default function CommoditySection({ data, loading, error }: CommoditySectionProps) {
  if (loading) return <LoadingSpinner message="원자재 로딩 중..." />
  if (error) return <ErrorAlert message={error} />
  if (!data?.commodities?.length) return null

  return (
    <section data-testid="macro-section-commodity">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">원자재</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {data.commodities.map((item) => (
          <CommodityCard key={item.symbol} item={item} />
        ))}
      </div>
    </section>
  )
}
