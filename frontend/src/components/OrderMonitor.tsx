import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from '../api/trading'

export default function OrderMonitor() {
  const { data: status } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
  })

  const detail = status?.positions_detail ?? {}
  const orders = status?.orders
  const strategy = status?.strategy
  const tickers = Object.keys(detail)

  const formatPrice = (n: number) => n.toLocaleString()

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">주문처리 현황</h3>
        <div className="flex items-center gap-2">
          {strategy?.buy_disabled && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
              매수 중단
            </span>
          )}
          <span className="text-xs text-gray-500">
            실현 손익:{' '}
            <span className={(strategy?.daily_realized_pnl ?? 0) >= 0 ? 'text-red-500' : 'text-blue-500'}>
              {formatPrice(strategy?.daily_realized_pnl ?? 0)}원
            </span>
          </span>
        </div>
      </div>

      {/* 투자 요약 */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-xs text-gray-500">투자가능금액</div>
          <div className="text-sm font-bold">{formatPrice(strategy?.total_investment ?? 0)}원</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-xs text-gray-500">보유/매수대기</div>
          <div className="text-sm font-bold">
            {tickers.length}종목 / {orders?.pending_buy_tickers?.length ?? 0}건
          </div>
        </div>
      </div>

      {/* 매수 대기 종목 */}
      {orders && orders.pending_buy_tickers.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-700 mb-1">매수 대기</h4>
          <div className="flex flex-wrap gap-1">
            {orders.pending_buy_tickers.map((t) => (
              <span key={t} className="px-2 py-0.5 bg-yellow-50 text-yellow-700 text-xs rounded animate-pulse">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 부분체결 취소 대기 */}
      {orders && orders.pending_cancels.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-700 mb-1">취소 대기 (부분체결)</h4>
          <div className="flex flex-wrap gap-1">
            {orders.pending_cancels.map((t) => (
              <span key={t} className="px-2 py-0.5 bg-orange-50 text-orange-700 text-xs rounded">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 보유 포지션 상세 */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 mb-2">보유 포지션</h4>
        {tickers.length === 0 ? (
          <p className="text-xs text-gray-400">보유 종목 없음</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-1 pr-2">종목</th>
                  <th className="pb-1 pr-2 text-right">매수가</th>
                  <th className="pb-1 pr-2 text-right">수량</th>
                  <th className="pb-1 pr-2 text-right">고점</th>
                  <th className="pb-1 text-center">익일</th>
                </tr>
              </thead>
              <tbody>
                {tickers.map((ticker) => {
                  const pos = detail[ticker]
                  return (
                    <tr key={ticker} className="border-b border-gray-50">
                      <td className="py-1.5 pr-2 font-medium">{pos.name ? `${pos.name}` : ticker}</td>
                      <td className="py-1.5 pr-2 text-right">{formatPrice(pos.buy_price)}</td>
                      <td className="py-1.5 pr-2 text-right">{pos.quantity}</td>
                      <td className="py-1.5 pr-2 text-right">{formatPrice(pos.high_since_buy)}</td>
                      <td className="py-1.5 text-center">
                        {pos.is_next_day && (
                          <span className="px-1.5 py-0.5 bg-purple-50 text-purple-700 text-xs rounded">
                            청산
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 체결 진행 */}
      {orders && Object.keys(orders.fills).length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">체결 진행</h4>
          {Object.entries(orders.fills).map(([orderNo, fill]) => {
            const pct = fill.order_qty > 0 ? (fill.filled_qty / fill.order_qty) * 100 : 0
            return (
              <div key={orderNo} className="mb-2">
                <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                  <span>{orderNo}</span>
                  <span>{fill.filled_qty}/{fill.order_qty}주 ({pct.toFixed(0)}%)</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-1.5">
                  <div
                    className="bg-green-500 h-1.5 rounded-full transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
