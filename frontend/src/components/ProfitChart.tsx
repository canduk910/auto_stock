import { useQuery } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { getDailyPerformance, getMonthlyPerformance } from '../api/performance'

export default function ProfitChart() {
  const { data: daily, isLoading: dailyLoading } = useQuery({
    queryKey: ['dailyPerformance'],
    queryFn: () => getDailyPerformance(30),
  })

  const { data: monthly, isLoading: monthlyLoading } = useQuery({
    queryKey: ['monthlyPerformance'],
    queryFn: getMonthlyPerformance,
  })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">일별 수익률</h3>
        {dailyLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : !daily?.length ? (
          <p className="text-gray-400">데이터가 없습니다.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={daily}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" fontSize={12} />
              <YAxis fontSize={12} unit="%" />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="daily_profit_rate"
                stroke="#FF3333"
                strokeWidth={2}
                dot={false}
                name="수익률(%)"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">월별 수익률</h3>
        {monthlyLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : !monthly?.length ? (
          <p className="text-gray-400">데이터가 없습니다.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" fontSize={12} />
              <YAxis fontSize={12} unit="%" />
              <Tooltip formatter={(v) => Number(v).toFixed(2) + '%'} />
              <Bar dataKey="total_profit_rate" fill="#3366FF" name="수익률" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
