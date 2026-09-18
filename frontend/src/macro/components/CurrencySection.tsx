import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts"
import LoadingSpinner from "./LoadingSpinner"
import ErrorAlert from "./ErrorAlert"
import type { CurrenciesResponse, CurrencyQuote } from "../../types/macro"

// 원본 `macro_lite/components/CurrencySection.jsx` 이식.
// Recharts 는 Tailwind 클래스를 못 받는 SVG 속성이라, 색은 우리 디자인시스템의
// CSS 변수(`var(--color-...)`)로 대체한다(hex 리터럴을 소스에 새로 두지 않는다 — frontend/CLAUDE.md).
// 원본 매핑: 상승 red-500(#ef4444)→--color-red-500 / 하락 blue-500(#3b82f6)→--color-blue-500 /
// 보합 gray-500(#6b7280)→--color-gray-500. 한국 관례(상승=빨강/하락=파랑)는 원본 그대로 보존.

const fmt = (v: number | null | undefined) =>
  v != null
    ? v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "-"

function CurrencyCard({ item }: { item: CurrencyQuote }) {
  const { symbol, name, price, change, change_pct, sparkline } = item
  const isUp = change > 0
  const isDown = change < 0
  const color = isUp ? "var(--color-red-500)" : isDown ? "var(--color-blue-500)" : "var(--color-gray-500)"
  const sign = isUp ? "+" : ""
  const gradId = `curr-${symbol.replace(/[^a-zA-Z0-9]/g, "")}`

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

interface CurrencySectionProps {
  data: CurrenciesResponse | null
  loading: boolean
  error: string | null
}

export default function CurrencySection({ data, loading, error }: CurrencySectionProps) {
  if (loading) return <LoadingSpinner message="환율 로딩 중..." />
  if (error) return <ErrorAlert message={error} />
  if (!data?.currencies?.length) return null

  return (
    <section data-testid="macro-section-currency">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">환율</h2>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {data.currencies.map((item) => (
          <CurrencyCard key={item.symbol} item={item} />
        ))}
      </div>
    </section>
  )
}
