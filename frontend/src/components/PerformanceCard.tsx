import { useQuery } from '@tanstack/react-query'
import { getPerformanceSummary } from '../api/performance'

function formatKRW(value: number): string {
  return value.toLocaleString('ko-KR') + '원'
}

function profitColor(value: number): string {
  if (value > 0) return 'text-[#FF3333]'
  if (value < 0) return 'text-[#3366FF]'
  return 'text-[#333333]'
}

interface Props {
  selectedStrategy: string
}

export default function PerformanceCard({ selectedStrategy }: Props) {
  const strategyParam = selectedStrategy === 'all' ? undefined : selectedStrategy

  const { data, isLoading, isError } = useQuery({
    queryKey: ['performanceSummary', strategyParam],
    queryFn: () => getPerformanceSummary(strategyParam),
  })

  if (isLoading) return <div className="p-6 text-gray-500">실적 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">실적 데이터를 불러올 수 없습니다.</div>
  if (!data) return null

  const cards = [
    { label: '운영 일수', value: `${data.total_days}일` },
    { label: '최근 자산', value: formatKRW(data.latest_asset) },
    {
      label: '누적 수익률',
      value: data.total_profit_rate.toFixed(2) + '%',
      colorValue: data.total_profit_rate,
    },
    {
      label: '일평균 수익률',
      value: data.avg_daily_profit_rate.toFixed(2) + '%',
      colorValue: data.avg_daily_profit_rate,
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 mb-1">{card.label}</p>
          <p
            className={`text-lg font-semibold ${
              card.colorValue !== undefined ? profitColor(card.colorValue) : 'text-gray-900'
            }`}
          >
            {card.value}
          </p>
        </div>
      ))}
    </div>
  )
}
