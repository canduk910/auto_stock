import { useTradingStatus } from '../contexts/TradingStatusContext'
import { getStrategyColor } from '../types/strategy'
import type { TradingStatusData, StrategyInfo, PositionDetail, OrderStatus } from '../types/trading'

interface VBTarget {
  k: number
  target_price: number
  open_price: number
  target_offset: number
  open_confirmed: boolean
}

/** 정상 종목코드: 6자리 영숫자 (ETF·신주인수권 등 알파벳 포함 코드 허용) */
function isValidTicker(ticker: string): boolean {
  return /^[0-9A-Z]{6}$/.test(ticker)
}

interface Props {
  selectedStrategy: string
}

export default function OrderMonitor({ selectedStrategy }: Props) {
  const { data: status } = useTradingStatus()

  const strategies = status?.strategies ?? {}
  const isAll = selectedStrategy === 'all'

  // 전략별 또는 전체 데이터 집계
  const aggregated = getAggregatedData(status, strategies, selectedStrategy, isAll)

  const formatPrice = (n: number) => n.toLocaleString()

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">주문처리 현황</h3>
        <div className="flex items-center gap-2">
          {aggregated.buyDisabled && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
              매수 중단
            </span>
          )}
          <span className="text-xs text-gray-500">
            실현 손익:{' '}
            <span className={aggregated.dailyPnl >= 0 ? 'text-red-500' : 'text-blue-500'}>
              {formatPrice(aggregated.dailyPnl)}원
            </span>
          </span>
        </div>
      </div>

      {/* 전략별 투자 요약 */}
      {isAll && Object.keys(strategies).length > 1 ? (
        <div className="grid grid-cols-1 gap-2 mb-4">
          {Object.entries(strategies).map(([key, strat]) => {
            const color = getStrategyColor(key)
            return (
              <div key={key} className={`p-2 rounded ${color.bg} flex items-center justify-between`}>
                <span className={`text-xs font-medium ${color.text}`}>{strat.name}</span>
                <div className="flex gap-4 text-xs">
                  <span>투자금: {formatPrice(strat.total_investment)}원</span>
                  <span>보유: {strat.positions}종목</span>
                  <span className={strat.daily_realized_pnl >= 0 ? 'text-red-500' : 'text-blue-500'}>
                    손익: {formatPrice(strat.daily_realized_pnl)}원
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="p-2 bg-gray-50 rounded">
            <div className="text-xs text-gray-500">투자가능금액</div>
            <div className="text-sm font-bold">{formatPrice(aggregated.totalInvestment)}원</div>
          </div>
          <div className="p-2 bg-gray-50 rounded">
            <div className="text-xs text-gray-500">보유/매수대기</div>
            <div className="text-sm font-bold">
              {aggregated.positionCount}종목 / {aggregated.pendingBuyCount}건
            </div>
          </div>
        </div>
      )}

      {/* 매수 대기 내역 (체결 전) */}
      {status?.orders && Object.keys(status.orders.pending_buy_orders ?? {}).length > 0 && (
        <PendingBuyOrdersSection
          orders={status.orders}
          strategies={strategies}
          selectedStrategy={selectedStrategy}
          isAll={isAll}
        />
      )}

      {/* 매수 주문 중 (주문 접수 전) */}
      {aggregated.pendingBuyTickers.length > 0 &&
        Object.keys(status?.orders?.pending_buy_orders ?? {}).length === 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-medium text-gray-700 mb-1">매수 주문 중</h4>
            <div className="flex flex-wrap gap-1">
              {aggregated.pendingBuyTickers.map((t) => (
                <span
                  key={t}
                  className="px-2 py-0.5 bg-yellow-50 text-yellow-700 text-xs rounded animate-pulse"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

      {/* 부분체결 취소 대기 */}
      {status?.orders && status.orders.pending_cancels.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-700 mb-1">취소 대기 (부분체결)</h4>
          <div className="flex flex-wrap gap-1">
            {status.orders.pending_cancels.map((t) => (
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
        {aggregated.positions.length === 0 ? (
          <p className="text-xs text-gray-400">보유 종목 없음</p>
        ) : (
          <PositionsTable
            positions={aggregated.positions}
            strategies={strategies}
            selectedStrategy={selectedStrategy}
            isAll={isAll}
            scan={status?.scan}
          />
        )}
      </div>

      {/* 체결 진행 */}
      {status?.orders && Object.keys(status.orders.fills).length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">체결 진행</h4>
          {Object.entries(status.orders.fills).map(([orderNo, fill]) => {
            const pct = fill.order_qty > 0 ? (fill.filled_qty / fill.order_qty) * 100 : 0
            return (
              <div key={orderNo} className="mb-2">
                <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                  <span>{orderNo}</span>
                  <span>
                    {fill.filled_qty}/{fill.order_qty}주 ({pct.toFixed(0)}%)
                  </span>
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

interface PositionRow {
  ticker: string
  pos: PositionDetail
  strategyKey?: string
  strategyName?: string
}

function getAggregatedData(
  status: TradingStatusData | undefined,
  strategies: Record<string, StrategyInfo>,
  selectedStrategy: string,
  isAll: boolean,
) {
  if (!status) {
    return {
      buyDisabled: false,
      dailyPnl: 0,
      totalInvestment: 0,
      positionCount: 0,
      pendingBuyCount: 0,
      pendingBuyTickers: [] as string[],
      positions: [] as PositionRow[],
    }
  }

  const strategyKeys = Object.keys(strategies)
  const hasStrategies = strategyKeys.length > 0

  if (!hasStrategies || !isAll && !strategies[selectedStrategy]) {
    // 폴백: 기존 구조 사용
    const detail = status.positions_detail ?? {}
    const orders = status.orders
    const strategy = status.strategy
    return {
      buyDisabled: strategy?.buy_disabled ?? false,
      dailyPnl: strategy?.daily_realized_pnl ?? 0,
      totalInvestment: strategy?.total_investment ?? 0,
      positionCount: Object.keys(detail).length,
      pendingBuyCount: orders?.pending_buy_tickers?.length ?? 0,
      pendingBuyTickers: orders?.pending_buy_tickers ?? [],
      positions: Object.entries(detail).map(([ticker, pos]) => ({
        ticker,
        pos,
      })) as PositionRow[],
    }
  }

  if (!isAll) {
    const strat = strategies[selectedStrategy]
    return {
      buyDisabled: strat.buy_disabled,
      dailyPnl: strat.daily_realized_pnl,
      totalInvestment: strat.total_investment,
      positionCount: strat.positions,
      pendingBuyCount: strat.pending_buys,
      pendingBuyTickers: strat.pending_buy_tickers,
      positions: Object.entries(strat.positions_detail)
        .filter(([ticker]) => isValidTicker(ticker))
        .map(([ticker, pos]) => ({
          ticker,
          pos,
          strategyKey: selectedStrategy,
          strategyName: strat.name,
        })),
    }
  }

  // 전체: 모든 전략 합산
  let dailyPnl = 0
  let totalInvestment = 0
  let positionCount = 0
  let pendingBuyCount = 0
  let buyDisabled = false
  const pendingBuyTickers: string[] = []
  const positions: PositionRow[] = []

  for (const [key, strat] of Object.entries(strategies)) {
    dailyPnl += strat.daily_realized_pnl
    totalInvestment += strat.total_investment
    positionCount += strat.positions
    pendingBuyCount += strat.pending_buys
    if (strat.buy_disabled) buyDisabled = true
    pendingBuyTickers.push(...strat.pending_buy_tickers)
    for (const [ticker, pos] of Object.entries(strat.positions_detail)) {
      if (!isValidTicker(ticker)) continue
      positions.push({ ticker, pos, strategyKey: key, strategyName: strat.name })
    }
  }

  return {
    buyDisabled,
    dailyPnl,
    totalInvestment,
    positionCount,
    pendingBuyCount,
    pendingBuyTickers,
    positions,
  }
}

function PendingBuyOrdersSection({
  orders,
  strategies,
  selectedStrategy,
  isAll,
}: {
  orders: OrderStatus
  strategies: Record<string, StrategyInfo>
  selectedStrategy: string
  isAll: boolean
}) {
  const allPendingBuyTickers = new Set<string>()
  if (!isAll && strategies[selectedStrategy]) {
    strategies[selectedStrategy].pending_buy_tickers.forEach((t) => allPendingBuyTickers.add(t))
  }

  const entries = Object.entries(orders.pending_buy_orders)
  const filtered = isAll
    ? entries
    : entries.filter(([, order]) => allPendingBuyTickers.has(order.ticker))

  if (filtered.length === 0) return null

  return (
    <div className="mb-4">
      <h4 className="text-sm font-medium text-gray-700 mb-2">매수 대기 (체결 전)</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="pb-1 pr-2">종목</th>
              <th className="pb-1 pr-2 text-right">주문가</th>
              <th className="pb-1 pr-2 text-right">수량</th>
              <th className="pb-1 text-right">주문번호</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(([orderNo, order]) => (
              <tr key={orderNo} className="border-b border-gray-50 animate-pulse">
                <td className="py-1.5 pr-2 font-medium text-yellow-700">
                  {order.name ? `${order.name}(${order.ticker})` : order.ticker}
                </td>
                <td className="py-1.5 pr-2 text-right">{order.price.toLocaleString()}</td>
                <td className="py-1.5 pr-2 text-right">{order.quantity}주</td>
                <td className="py-1.5 text-right text-gray-400">{orderNo}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PositionsTable({
  positions,
  strategies,
  selectedStrategy,
  isAll,
  scan,
}: {
  positions: PositionRow[]
  strategies: Record<string, StrategyInfo>
  selectedStrategy: string
  isAll: boolean
  scan?: TradingStatusData['scan']
}) {
  const isBreakout = selectedStrategy === 'volatility_breakout' || selectedStrategy === 'long_tail_volatility'
  const isVB = isBreakout  // 표 컬럼 구성은 VB/LTV 동일
  const vbTargets = (strategies[selectedStrategy]?.targets ?? {}) as Record<string, VBTarget>
  const formatPrice = (n: number) => n.toLocaleString()

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-gray-500 border-b">
            {isAll && Object.keys(strategies).length > 1 && (
              <th className="pb-1 pr-2">전략</th>
            )}
            <th className="pb-1 pr-2">종목</th>
            <th className="pb-1 pr-2 text-right">매수가</th>
            <th className="pb-1 pr-2 text-right">수량</th>
            <th className="pb-1 pr-2 text-right">고점</th>
            {isVB ? (
              <>
                <th className="pb-1 pr-2 text-right">시가</th>
                <th className="pb-1 pr-2 text-right">타겟가</th>
                <th className="pb-1 pr-2 text-right">현재가</th>
                <th className="pb-1 text-center">상태</th>
              </>
            ) : (
              <th className="pb-1 text-center">익일</th>
            )}
          </tr>
        </thead>
        <tbody>
          {positions.map(({ ticker, pos, strategyKey, strategyName }) => {
            const color = strategyKey ? getStrategyColor(strategyKey) : null
            const vbt = vbTargets[ticker]
            const curPrice = scan?.ticker_prices?.[ticker]?.current_price ?? 0
            return (
              <tr key={`${strategyKey}-${ticker}`} className="border-b border-gray-50">
                {isAll && Object.keys(strategies).length > 1 && (
                  <td className="py-1.5 pr-2">
                    {color && (
                      <span className={`px-1.5 py-0.5 rounded text-xs ${color.badge}`}>
                        {strategyName}
                      </span>
                    )}
                  </td>
                )}
                <td className="py-1.5 pr-2 font-medium">
                  {pos.name ? pos.name : ticker}
                </td>
                <td className="py-1.5 pr-2 text-right">{formatPrice(pos.buy_price)}</td>
                <td className="py-1.5 pr-2 text-right">{pos.quantity}</td>
                <td className="py-1.5 pr-2 text-right">{formatPrice(pos.high_since_buy)}</td>
                {isVB ? (
                  <>
                    <td className="py-1.5 pr-2 text-right">
                      {vbt && vbt.open_price > 0 ? formatPrice(vbt.open_price) : '-'}
                    </td>
                    <td className="py-1.5 pr-2 text-right font-medium text-indigo-600">
                      {vbt && vbt.target_price > 0 ? formatPrice(vbt.target_price) : '-'}
                    </td>
                    <td className="py-1.5 pr-2 text-right">
                      {curPrice > 0 ? formatPrice(curPrice) : '-'}
                    </td>
                    <td className="py-1.5 text-center">
                      {curPrice > 0 && pos.buy_price > 0 ? (() => {
                        const plRate = ((curPrice - pos.buy_price) / pos.buy_price * 100)
                        const cls = plRate >= 0 ? 'text-red-600' : 'text-blue-600'
                        return (
                          <span className={`text-xs font-medium ${cls}`}>
                            {plRate >= 0 ? '+' : ''}{plRate.toFixed(1)}%
                          </span>
                        )
                      })() : '-'}
                    </td>
                  </>
                ) : (
                  <td className="py-1.5 text-center">
                    {pos.is_next_day && (
                      <span className="px-1.5 py-0.5 bg-purple-50 text-purple-700 text-xs rounded">
                        청산
                      </span>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
