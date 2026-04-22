import { useQuery } from '@tanstack/react-query'
import { getBalance } from '../api/balance'

function profitColor(value: number): string {
  if (value > 0) return 'text-[#FF3333]'
  if (value < 0) return 'text-[#3366FF]'
  return 'text-[#333333]'
}

function formatKRW(value: number): string {
  return value.toLocaleString('ko-KR')
}

export default function BalanceTable() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['balance'],
    queryFn: getBalance,
    refetchInterval: 10000,
  })

  if (isLoading) return <div className="p-6 text-gray-500">잔고 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">잔고를 불러올 수 없습니다.</div>
  if (!data) return null

  const { summary, holdings } = data

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 mb-1">예수금</p>
          <p className="text-lg font-bold text-gray-900">{formatKRW(summary.deposit)}원</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 mb-1">총 평가금</p>
          <p className="text-lg font-bold text-gray-900">{formatKRW(summary.total_eval_amount)}원</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 mb-1">순자산</p>
          <p className="text-lg font-bold text-gray-900">{formatKRW(summary.net_asset)}원</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 mb-1">총 평가손익</p>
          <p className={`text-lg font-bold ${profitColor(summary.profit_loss_total)}`}>
            {formatKRW(summary.profit_loss_total)}원
          </p>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">종목명</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">보유수량</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">매입가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">현재가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">평가금액</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">평가손익</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">수익률</th>
            </tr>
          </thead>
          <tbody>
            {holdings.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  보유 종목이 없습니다.
                </td>
              </tr>
            ) : (
              holdings.map((h) => (
                <tr key={h.ticker} className="border-b hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-700">{h.name}</td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {formatKRW(h.quantity)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {formatKRW(h.avg_price)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {formatKRW(h.current_price)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {formatKRW(h.eval_amount)}원
                  </td>
                  <td className={`px-4 py-3 text-right font-medium ${profitColor(h.eval_profit_loss)}`}>
                    {formatKRW(h.eval_profit_loss)}원
                  </td>
                  <td className={`px-4 py-3 text-right font-medium ${profitColor(h.eval_profit_rate)}`}>
                    {h.eval_profit_rate.toFixed(2)}%
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
