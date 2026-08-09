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

interface Props {
  selectedStrategy: string
}

const DAILY_DAYS = 40
const CUMULATIVE_DAYS = 180  // 약 6개월 (영업일+달력 혼합 여유, 백엔드는 N일치 raw 반환)

export default function ProfitChart({ selectedStrategy }: Props) {
  const strategyParam = selectedStrategy === 'all' ? undefined : selectedStrategy

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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          당일 수익률 (실현손익 기준, 최근 {DAILY_DAYS}일)
        </h3>
        {dailyLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : !hasDaily ? (
          <p className="text-gray-400">데이터가 없습니다.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={daily}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" fontSize={12} />
              <YAxis fontSize={12} unit="%" />
              <Tooltip formatter={(v) => Number(v).toFixed(2) + '%'} />
              <Bar dataKey="daily_profit_rate" name="당일 수익률">
                {daily!.map((d, i) => (
                  <Cell
                    key={i}
                    fill={(d.daily_profit_rate ?? 0) >= 0 ? PROFIT_COLOR : LOSS_COLOR}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          누적 수익률 (TWR 복리, 최근 6개월)
        </h3>
        {cumLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : !hasCumulative ? (
          <p className="text-gray-400">데이터가 없습니다.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={cumulative}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" fontSize={12} />
              <YAxis fontSize={12} unit="%" />
              <Tooltip formatter={(v) => Number(v).toFixed(2) + '%'} />
              <Line
                type="monotone"
                dataKey="cumulative_return_rate"
                stroke={PROFIT_COLOR}
                strokeWidth={2}
                dot={false}
                name="누적 수익률"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
