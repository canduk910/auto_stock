import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBalance } from '../api/balance'
import { manualSell } from '../api/trading'
import { useTradingStatus } from '../contexts/TradingStatusContext'
import { getStrategyColor } from '../types/strategy'
import type { Holding } from '../types/balance'
import ConfirmModal from './ConfirmModal'
import { pnlColorClass as profitColor } from '../utils/pnlColor'
import ScrollPane from './ScrollPane'

const STRATEGY_NAMES: Record<string, string> = {
  momentum: '모멘텀',
  volatility_breakout: '변동성돌파',
  long_tail_volatility: '롱테일 변동성',
  donchian_swing: '20일 신고가 스윙',
}

const MARKET_BADGE_BASE = 'inline-block px-1.5 py-0.5 rounded text-xs font-medium'

/**
 * 거래시장 배지 라벨/색상 결정 (J1, 2026-05-11).
 *
 * stock_master(CTPF1002R 캐시) 의 nxt_tradable/krx_halted 조합에 따라:
 *   - true  && !halted → KRX+NXT (emerald)
 *   - true  &&  halted → NXT만   (amber)
 *   - false && !halted → KRX     (gray)
 *   - false &&  halted → 정지    (red)
 *   - 미캐시(null/undefined) → 확인중 (light-gray)
 */
/**
 * cycle339 — 손절가 칸의 설명.
 *
 * 🔴 **가격 무관 청산은 이 숫자에 안 담긴다** — VB 의 15:20 일괄매도, kojiro 의
 * stage3 추세종료, 익일청산이 그것이다. 손절가가 보인다고 그 가격까지 안 팔리는
 * 것이 아니므로 그 사실을 툴팁이 말한다.
 */
function stopTitle(h: Holding): string {
  if (h.stop_source === 'engine_idle') {
    // 🔴 「손절선이 없다」가 아니라 「지금은 모른다」다. 엔진은 21:30 에 메모리
    // 포지션을 비우고 07:45 에 DB 에서 되살린다 — 그 사이에는 알 길이 없다.
    return '매매 엔진 정지 중 — 장 시작(07:45) 후 표시된다. 손절선이 없다는 뜻이 아니다.'
  }
  if (!h.stop_price) {
    return '손절선을 판정할 수 없다 (보유 전략 미상 또는 손절 파라미터 없음). 숫자를 지어내지 않는다.'
  }
  const base =
    h.stop_source === 'effective'
      ? '전략이 실제로 쓰는 실효 손절선 (청산 판정과 같은 산식)'
      : '고정% 손절 근사 — 매입가 × (1 + 하드손절%). 트레일링·시간 청산은 담기지 않는다'
  return `${base}. ⚠️ 가격과 무관한 청산(15:20 일괄매도 · 스테이지 종료 · 익일청산)은 이 값에 담기지 않는다.`
}

/** 목표가 칸의 설명 — 대부분의 전략에 목표가가 **없다**는 사실을 말한다. */
function targetTitle(h: Holding): string {
  if (h.target_source === 'measured_move') {
    return '측정 목표가 (깃대폭 + 깃발고점) — 눌림목 돌파 전략의 부분 익절 트리거다. 전량 청산선이 아니다.'
  }
  return '이 전략은 목표가를 쓰지 않는다 — 트레일링·시간·스테이지로 청산한다.'
}

function marketBadgeProps(h: Holding): { label: string; cls: string } {
  const nxt = h.nxt_tradable
  const halted = h.krx_halted
  if (nxt == null && halted == null) {
    return { label: '확인중', cls: `${MARKET_BADGE_BASE} bg-gray-50 text-gray-500` }
  }
  if (halted === true && nxt !== true) {
    return { label: '정지', cls: `${MARKET_BADGE_BASE} bg-red-100 text-red-800` }
  }
  if (nxt === true && halted === true) {
    return { label: 'NXT만', cls: `${MARKET_BADGE_BASE} bg-amber-100 text-amber-800` }
  }
  if (nxt === true && halted !== true) {
    return { label: 'KRX+NXT', cls: `${MARKET_BADGE_BASE} bg-emerald-100 text-emerald-800` }
  }
  // nxt=false, !halted (또는 nxt=null && halted=false 등 부분 알려진 경우)
  return { label: 'KRX', cls: `${MARKET_BADGE_BASE} bg-gray-100 text-gray-700` }
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
  // setTimeout id 보존 — unmount 시 cleanup으로 고아 setState 경고 방지
  const sellResultTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (sellResultTimerRef.current) clearTimeout(sellResultTimerRef.current)
    }
  }, [])

  const scheduleResultClear = () => {
    if (sellResultTimerRef.current) clearTimeout(sellResultTimerRef.current)
    sellResultTimerRef.current = setTimeout(() => setSellResult(null), 5000)
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['balance'],
    queryFn: getBalance,
    refetchInterval: 10000,
  })

  const { data: status } = useTradingStatus()

  const sellMutation = useMutation({
    mutationFn: ({ ticker, quantity }: { ticker: string; quantity: number }) =>
      manualSell(ticker, quantity),
    onSuccess: (result) => {
      setSellTarget(null)
      setSellResult(result.message)
      queryClient.invalidateQueries({ queryKey: ['balance'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      scheduleResultClear()
    },
    onError: (err: Error) => {
      setSellTarget(null)
      setSellResult(`매도 실패: ${err.message}`)
      scheduleResultClear()
    },
  })

  // 종목→전략 매핑 — status.strategies 변경 시에만 재계산
  const tickerStrategyMap = useMemo(() => {
    const map: Record<string, string> = {}
    if (status?.strategies) {
      for (const [key, strat] of Object.entries(status.strategies)) {
        for (const ticker of strat.position_tickers) {
          map[ticker] = key
        }
      }
    }
    return map
  }, [status?.strategies])

  // WebSocket 실시간 시세로 현재가/평가 덮어쓰기 — holdings/시세 변경 시에만
  const enrichedHoldings = useMemo(() => {
    const realtimePrices = status?.scan?.ticker_prices ?? {}
    const holdings = data?.holdings ?? []
    return holdings.map((h) => {
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
  }, [data?.holdings, status?.scan?.ticker_prices])

  const isAll = selectedStrategy === 'all'

  const filteredHoldings = useMemo(() => {
    const isValidTicker = (t: string) => /^[0-9A-Z]{6}$/.test(t)
    return isAll
      ? enrichedHoldings.filter((h) => isValidTicker(h.ticker))
      : enrichedHoldings.filter((h) => isValidTicker(h.ticker) && tickerStrategyMap[h.ticker] === selectedStrategy)
  }, [enrichedHoldings, isAll, tickerStrategyMap, selectedStrategy])

  if (isLoading) return <div className="p-6 text-gray-500">잔고 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">잔고를 불러올 수 없습니다.</div>
  if (!data) return null

  const { summary } = data

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
        <ScrollPane>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">종목명</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">섹터</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">거래시장</th>
              {isAll && (
                <th className="px-4 py-3 text-left font-medium text-gray-600">전략</th>
              )}
              <th className="px-4 py-3 text-right font-medium text-gray-600">보유수량</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">매입가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">현재가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">손절가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">목표가</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">평가금액</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">평가손익</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">수익률</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600"></th>
            </tr>
          </thead>
          <tbody>
            {filteredHoldings.length === 0 ? (
              <tr>
                <td colSpan={isAll ? 13 : 12} className="px-4 py-8 text-center text-gray-400">
                  보유 종목이 없습니다.
                </td>
              </tr>
            ) : (
              filteredHoldings.map((h) => {
                const stratKey = tickerStrategyMap[h.ticker]
                const color = stratKey ? getStrategyColor(stratKey) : null
                const market = marketBadgeProps(h)
                return (
                  <tr key={h.ticker} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-700">{h.name}</td>
                    <td
                      data-testid={`sector-${h.ticker}`}
                      className="px-4 py-3 text-gray-500"
                    >
                      {h.sector?.trim() || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        data-testid={`market-badge-${h.ticker}`}
                        className={market.cls}
                      >
                        {market.label}
                      </span>
                    </td>
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
                    <td
                      data-testid={`stop-price-${h.ticker}`}
                      title={stopTitle(h)}
                      className={`px-4 py-3 text-right ${
                        h.stop_source === 'hard_pct' ? 'text-gray-400' : 'text-gray-700'
                      }`}
                    >
                      {h.stop_price
                        ? formatKRW(h.stop_price)
                        : h.stop_source === 'engine_idle' ? '⏸' : '—'}
                      {h.stop_source === 'hard_pct' && h.stop_price ? (
                        <span className="ml-1 text-[10px] text-gray-400">근사</span>
                      ) : null}
                    </td>
                    <td
                      data-testid={`target-price-${h.ticker}`}
                      title={targetTitle(h)}
                      className="px-4 py-3 text-right text-gray-700"
                    >
                      {h.target_price ? formatKRW(h.target_price) : '—'}
                    </td>
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
        </ScrollPane>
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
