import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBalance } from '../api/balance'
import { getTradingStatus, manualSell } from '../api/trading'
import { getStrategyColor } from '../types/strategy'
import ConfirmModal from './ConfirmModal'

const STRATEGY_NAMES: Record<string, string> = {
  momentum: '모멘텀',
  volatility_breakout: '변동성돌파',
  long_tail_volatility: '롱테일 변동성',
}

function profitColor(value: number): string {
  if (value > 0) return 'text-[#FF3333]'
  if (value < 0) return 'text-[#3366FF]'
  return 'text-[#333333]'
}

function formatKRW(value: number): string {
  return value.toLocaleString('ko-KR')
}

interface Props {
  selectedStrategy: string
}

export default function BalanceTable({ selectedStrategy }: Props) {
  const queryClient = useQueryClient()
  const [sellTarget, setSellTarget] = useState<{ ticker: string; name: string; quantity: number } | null>(null)
  const [sellResult, setSellResult] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['balance'],
    queryFn: getBalance,
    refetchInterval: 10000,
  })

  const { data: status } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
  })

  const sellMutation = useMutation({
    mutationFn: ({ ticker, quantity }: { ticker: string; quantity: number }) =>
      manualSell(ticker, quantity),
    onSuccess: (result) => {
      setSellTarget(null)
      setSellResult(result.message)
      queryClient.invalidateQueries({ queryKey: ['balance'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setTimeout(() => setSellResult(null), 5000)
    },
    onError: (err: Error) => {
      setSellTarget(null)
      setSellResult(`매도 실패: ${err.message}`)
      setTimeout(() => setSellResult(null), 5000)
    },
  })

  if (isLoading) return <div className="p-6 text-gray-500">잔고 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">잔고를 불러올 수 없습니다.</div>
  if (!data) return null

  const { summary, holdings } = data

  // 종목→전략 매핑
  const tickerStrategyMap: Record<string, string> = {}
  if (status?.strategies) {
    for (const [key, strat] of Object.entries(status.strategies)) {
      for (const ticker of strat.position_tickers) {
        tickerStrategyMap[ticker] = key
      }
    }
  }

  const isAll = selectedStrategy === 'all'

  // WebSocket 실시간 시세로 현재가/평가 덮어쓰기
  const realtimePrices = status?.scan?.ticker_prices ?? {}
  const enrichedHoldings = holdings.map((h) => {
    const rt = realtimePrices[h.ticker]
    if (!rt || !rt.current_price) return h
    const currentPrice = rt.current_price
    const evalAmount = currentPrice * h.quantity
    const evalProfitLoss = evalAmount - h.purchase_amount
    const evalProfitRate = h.purchase_amount > 0
      ? (evalProfitLoss / h.purchase_amount) * 100
      : 0
    return { ...h, current_price: currentPrice, eval_amount: evalAmount, eval_profit_loss: evalProfitLoss, eval_profit_rate: evalProfitRate }
  })

  const isValidTicker = (t: string) => /^\d{6}$/.test(t)

  const filteredHoldings = isAll
    ? enrichedHoldings.filter((h) => isValidTicker(h.ticker))
    : enrichedHoldings.filter((h) => isValidTicker(h.ticker) && tickerStrategyMap[h.ticker] === selectedStrategy)

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

      {sellResult && (
        <div className={`p-3 rounded-lg text-sm ${
          sellResult.includes('실패') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
        }`}>
          {sellResult}
        </div>
      )}

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">종목명</th>
              {isAll && (
                <th className="px-4 py-3 text-left font-medium text-gray-600">전략</th>
              )}
              <th className="px-4 py-3 text-right font-medium text-gray-600">보유수량</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">매입가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">현재가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">평가금액</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">평가손익</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">수익률</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600"></th>
            </tr>
          </thead>
          <tbody>
            {filteredHoldings.length === 0 ? (
              <tr>
                <td colSpan={isAll ? 9 : 8} className="px-4 py-8 text-center text-gray-400">
                  보유 종목이 없습니다.
                </td>
              </tr>
            ) : (
              filteredHoldings.map((h) => {
                const stratKey = tickerStrategyMap[h.ticker]
                const color = stratKey ? getStrategyColor(stratKey) : null
                return (
                  <tr key={h.ticker} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-700">{h.name}</td>
                    {isAll && (
                      <td className="px-4 py-3">
                        {color ? (
                          <span className={`px-1.5 py-0.5 rounded text-xs ${color.badge}`}>
                            {STRATEGY_NAMES[stratKey] ?? stratKey}
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-500">-</span>
                        )}
                      </td>
                    )}
                    <td className="px-4 py-3 text-right text-gray-700">{formatKRW(h.quantity)}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{formatKRW(h.avg_price)}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{formatKRW(h.current_price)}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{formatKRW(h.eval_amount)}원</td>
                    <td className={`px-4 py-3 text-right font-medium ${profitColor(h.eval_profit_loss)}`}>
                      {formatKRW(h.eval_profit_loss)}원
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${profitColor(h.eval_profit_rate)}`}>
                      {h.eval_profit_rate.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => setSellTarget({
                          ticker: h.ticker,
                          name: h.name,
                          quantity: h.sellable_quantity,
                        })}
                        disabled={h.sellable_quantity <= 0}
                        className="px-2.5 py-1 text-xs font-medium text-blue-600 border border-blue-300 rounded hover:bg-blue-50 disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        매도
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {sellTarget && (
        <ConfirmModal
          open={true}
          title="수동 매도"
          message={`${sellTarget.name}(${sellTarget.ticker}) ${sellTarget.quantity}주를 시장가로 매도하시겠습니까?`}
          onConfirm={() => sellMutation.mutate({
            ticker: sellTarget.ticker,
            quantity: sellTarget.quantity,
          })}
          onCancel={() => setSellTarget(null)}
          loading={sellMutation.isPending}
        />
      )}
    </div>
  )
}
