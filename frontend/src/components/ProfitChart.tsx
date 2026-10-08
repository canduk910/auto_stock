import { useQuery } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { getDailyPerformance } from '../api/performance'
import { PROFIT_HEX as PROFIT_COLOR, LOSS_HEX as LOSS_COLOR } from '../utils/pnlColor'
import { useCostBasis } from '../utils/costBasis'
import CostBasisToggle from './CostBasisToggle'

interface Props {
  selectedStrategy: string
}

const DAILY_DAYS = 40
const CUMULATIVE_DAYS = 180  // 약 6개월 (영업일+달력 혼합 여유, 백엔드는 N일치 raw 반환)

export default function ProfitChart({ selectedStrategy }: Props) {
  const strategyParam = selectedStrategy === 'all' ? undefined : selectedStrategy

  // cycle411 — 세후 기본 + 세전 토글. 화면 공통(PerformanceCard 와 상태 공유).
  const [costBasis, setCostBasis] = useCostBasis()
  const isNet = costBasis === 'net'

  // 당일 수익률 — 최근 40일
  const { data: daily, isLoading: dailyLoading } = useQuery({
    queryKey: ['dailyPerformance', 'daily40', strategyParam],
    queryFn: () => getDailyPerformance(DAILY_DAYS, strategyParam),
  })

  // 누적 수익률 — 최근 6개월
  const { data: cumulative, isLoading: cumLoading } = useQuery({
    queryKey: ['dailyPerformance', 'cum6m', strategyParam],
    queryFn: () => getDailyPerformance(CUMULATIVE_DAYS, strategyParam),
  })

  const hasDaily = !!daily && daily.length > 0
  const hasCumulative = !!cumulative && cumulative.length > 0

  // net 칸이 없거나(구 서버) null(비용 조회 실패, cycle411b M4)이면 세전 칸으로 폴백한다.
  const hasNetDaily =
    hasDaily && daily!.every((d) => d.net_daily_profit_rate !== undefined && d.net_daily_profit_rate !== null)
  const hasNetCumulative =
    hasCumulative &&
    cumulative!.every(
      (d) => d.net_cumulative_return_rate !== undefined && d.net_cumulative_return_rate !== null,
    )
  const useNetDaily = isNet && hasNetDaily
  const useNetCumulative = isNet && hasNetCumulative
  const dailyKey = useNetDaily ? 'net_daily_profit_rate' : 'daily_profit_rate'
  const cumulativeKey = useNetCumulative ? 'net_cumulative_return_rate' : 'cumulative_return_rate'
  const dailyBasisLabel = useNetDaily ? '세후' : '세전'
  const cumulativeBasisLabel = useNetCumulative ? '세후' : '세전'

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="col-span-full flex justify-end">
        <CostBasisToggle value={costBasis} onChange={setCostBasis} />
      </div>
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          당일 수익률 (실현손익 기준, 최근 {DAILY_DAYS}일 · {dailyBasisLabel})
        </h3>
        {dailyLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : !hasDaily ? (
          <p className="text-gray-400">데이터가 없습니다.</p>
        ) : (
          <div data-testid="profit-chart-daily" data-series={dailyKey}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={daily}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={12} />
                <YAxis fontSize={12} unit="%" />
                <Tooltip formatter={(v) => Number(v).toFixed(2) + '%'} />
                <Bar dataKey={dailyKey} name={`당일 수익률(${dailyBasisLabel})`}>
                  {daily!.map((d, i) => (
                    <Cell
                      key={i}
                      fill={((d[dailyKey as keyof typeof d] as number | undefined) ?? 0) >= 0 ? PROFIT_COLOR : LOSS_COLOR}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          누적 수익률 (TWR 복리, 최근 6개월 · {cumulativeBasisLabel})
        </h3>
        {cumLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : !hasCumulative ? (
          <p className="text-gray-400">데이터가 없습니다.</p>
        ) : (
          <div data-testid="profit-chart-cumulative" data-series={cumulativeKey}>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={cumulative}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={12} />
                <YAxis fontSize={12} unit="%" />
                <Tooltip formatter={(v) => Number(v).toFixed(2) + '%'} />
                <Line
                  type="monotone"
                  dataKey={cumulativeKey}
                  stroke={PROFIT_COLOR}
                  strokeWidth={2}
                  dot={false}
                  name={`누적 수익률(${cumulativeBasisLabel})`}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
