import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from '../api/trading'
import { getStrategyColor } from '../types/strategy'
import type { BuySignal } from '../types/trading'

interface VBTarget {
  k: number
  target_price: number
  open_price: number
  target_offset: number
  open_confirmed: boolean
}

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  idle: { label: '대기', color: 'bg-gray-100 text-gray-700' },
  booting: { label: '기동 중', color: 'bg-yellow-100 text-yellow-700' },
  next_day_clear: { label: '익일 청산', color: 'bg-orange-100 text-orange-700' },
  scanning: { label: '종목 스캔', color: 'bg-blue-100 text-blue-700' },
  trading: { label: '매매 중', color: 'bg-green-100 text-green-700' },
  buy_stopped: { label: '매수 중단', color: 'bg-amber-100 text-amber-700' },
  closing: { label: '장 마감', color: 'bg-purple-100 text-purple-700' },
  settling: { label: '정산 중', color: 'bg-indigo-100 text-indigo-700' },
  vb_trading: { label: 'VB 매매 중', color: 'bg-teal-100 text-teal-700' },
}

interface Props {
  selectedStrategy: string
}

export default function ScanMonitor({ selectedStrategy }: Props) {
  const [expanded, setExpanded] = useState(false)

  const { data: status } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
  })

  const phase = status?.phase ?? 'idle'
  const scan = status?.scan
  const phaseInfo = PHASE_LABELS[phase] ?? PHASE_LABELS.idle

  const strategies = status?.strategies ?? {}
  const isAll = selectedStrategy === 'all'

  // 전략별 매수 신호 집계
  let signals: (BuySignal & { strategyKey?: string; strategyName?: string })[] = []
  const strategyKeys = Object.keys(strategies)

  if (strategyKeys.length > 0) {
    if (isAll) {
      for (const [key, strat] of Object.entries(strategies)) {
        for (const sig of strat.buy_signals) {
          signals.push({ ...sig, strategyKey: key, strategyName: strat.name })
        }
      }
    } else if (strategies[selectedStrategy]) {
      const strat = strategies[selectedStrategy]
      signals = strat.buy_signals.map((sig) => ({
        ...sig,
        strategyKey: selectedStrategy,
        strategyName: strat.name,
      }))
    }
  } else {
    // 폴백: 기존 구조
    signals = status?.strategy?.buy_signals ?? []
  }

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">조건검색 현황</h3>
        <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${phaseInfo.color}`}>
          {phaseInfo.label}
        </span>
      </div>

      {/* 스캔 요약 — 전략별 분리 */}
      {(() => {
        // 전략별 스캔 데이터 결정
        const showMomentumScan = isAll || selectedStrategy === 'momentum'
        const vbStrat = strategies['volatility_breakout']
        const vbCount = vbStrat?.scanned_count ?? 0

        return (
          <>
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">
                  {showMomentumScan ? (scan?.filtered_count ?? 0) : vbCount}
                </div>
                <div className="text-xs text-gray-500">
                  {isAll ? '모멘텀 필터' : '필터링'}
                </div>
              </div>
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{scan?.subscribed_count ?? 0}</div>
                <div className="text-xs text-gray-500">구독 중</div>
              </div>
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-sm font-medium text-gray-900">{scan?.last_scan_time ?? '-'}</div>
                <div className="text-xs text-gray-500">마지막 스캔</div>
              </div>
            </div>

            {/* 전체 탭: VB 스캔 카운트도 표시 */}
            {isAll && vbCount > 0 && (
              <div className="mb-3 px-2 py-1.5 bg-indigo-50 rounded text-xs text-indigo-700">
                변동성 돌파 스캔: {vbCount}종목 (09:00:05~ 매매)
              </div>
            )}

            {/* VB 탭: 운영시각 안내 */}
            {!isAll && selectedStrategy === 'volatility_breakout' && (
              <div className="mb-3 px-2 py-1.5 bg-teal-50 rounded text-xs text-teal-700 flex items-center justify-between">
                <span>매매 시간: 09:00:05 ~ 15:20 (시가 확정 직후 시작)</span>
                <span className="text-teal-500">{vbCount > 0 ? `${vbCount}종목 감시 중` : ''}</span>
              </div>
            )}

            {/* 모멘텀 종목 리스트 */}
            {showMomentumScan && scan && scan.filtered_count > 0 && (
              <div className="mb-4">
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="text-xs text-blue-600 hover:underline"
                >
                  {expanded ? '종목 리스트 접기' : `종목 리스트 펼치기 (${scan.filtered_count}개)`}
                </button>
                {expanded && (
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-1 pr-2">종목</th>
                          <th className="pb-1 pr-2 text-right">현재가</th>
                          <th className="pb-1 pr-2 text-right">전일대비</th>
                          <th className="pb-1 pr-2 text-right">시총(억)</th>
                          <th className="pb-1 text-right">거래대금(억)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...scan.filtered_tickers]
                          .sort(
                            (a, b) =>
                              (scan.ticker_prices?.[b]?.prdy_ctrt ?? 0) -
                              (scan.ticker_prices?.[a]?.prdy_ctrt ?? 0),
                          )
                          .map((ticker) => {
                            const name = scan.ticker_names?.[ticker]
                            const price = scan.ticker_prices?.[ticker]
                            const mkt = scan.ticker_market_info?.[ticker]
                            const rate = price?.prdy_ctrt ?? 0
                            return (
                              <tr key={ticker} className="border-b border-gray-50">
                                <td className="py-1 pr-2 font-medium">
                                  {name ? `${name}(${ticker})` : ticker}
                                </td>
                                <td className="py-1 pr-2 text-right">
                                  {price ? price.current_price.toLocaleString() : '-'}
                                </td>
                                <td
                                  className={`py-1 pr-2 text-right font-medium ${rate >= 29 ? 'text-red-600 font-bold' : rate >= 0 ? 'text-red-500' : 'text-blue-500'}`}
                                >
                                  {price ? `${rate >= 0 ? '+' : ''}${rate.toFixed(1)}%` : '-'}
                                </td>
                                <td className="py-1 pr-2 text-right text-gray-500">
                                  {mkt ? mkt.market_cap.toLocaleString() : '-'}
                                </td>
                                <td className="py-1 text-right text-gray-500">
                                  {mkt ? mkt.trade_amount.toLocaleString() : '-'}
                                </td>
                              </tr>
                            )
                          })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* VB 전용 탭: 타겟 가격 테이블 */}
            {!isAll && selectedStrategy === 'volatility_breakout' && (() => {
              const targets = (vbStrat?.targets ?? {}) as Record<string, VBTarget>
              const targetEntries = Object.entries(targets)
              if (targetEntries.length === 0) {
                return (
                  <div className="mb-4">
                    <p className="text-xs text-gray-400">
                      {vbCount > 0
                        ? `${vbCount}종목 스캔 완료 — K값 계산 대기 중`
                        : '스캔된 종목 없음'}
                    </p>
                  </div>
                )
              }
              return (
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-medium text-gray-700">
                      타겟 가격 ({targetEntries.length}종목)
                    </h4>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-1 pr-2">종목</th>
                          <th className="pb-1 pr-2 text-right">K값</th>
                          <th className="pb-1 pr-2 text-right">시가</th>
                          <th className="pb-1 pr-2 text-right">타겟가</th>
                          <th className="pb-1 pr-2 text-right">현재가</th>
                          <th className="pb-1 text-center">상태</th>
                        </tr>
                      </thead>
                      <tbody>
                        {targetEntries
                          .sort(([, a], [, b]) => {
                            // 시가 확정된 것 먼저, 타겟 돌파 근접한 것 우선
                            if (a.open_confirmed !== b.open_confirmed) return a.open_confirmed ? -1 : 1
                            return (b.target_price || 0) - (a.target_price || 0)
                          })
                          .map(([ticker, t]) => {
                            const name = scan?.ticker_names?.[ticker] ?? ''
                            const curPrice = scan?.ticker_prices?.[ticker]?.current_price ?? 0
                            const pct = t.target_price > 0 && curPrice > 0
                              ? ((curPrice / t.target_price - 1) * 100).toFixed(1)
                              : null
                            const nearTarget = pct !== null && parseFloat(pct) >= -2
                            return (
                              <tr key={ticker} className={`border-b border-gray-50 ${nearTarget ? 'bg-yellow-50' : ''}`}>
                                <td className="py-1 pr-2 font-medium">
                                  {name ? `${name}(${ticker})` : ticker}
                                </td>
                                <td className="py-1 pr-2 text-right text-gray-600">{t.k.toFixed(3)}</td>
                                <td className="py-1 pr-2 text-right">
                                  {t.open_price > 0 ? t.open_price.toLocaleString() : '-'}
                                </td>
                                <td className="py-1 pr-2 text-right font-medium text-indigo-600">
                                  {t.target_price > 0 ? t.target_price.toLocaleString() : '-'}
                                </td>
                                <td className="py-1 pr-2 text-right">
                                  {curPrice > 0 ? curPrice.toLocaleString() : '-'}
                                </td>
                                <td className="py-1 text-center">
                                  {!t.open_confirmed ? (
                                    <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-500">시가 대기</span>
                                  ) : curPrice >= t.target_price ? (
                                    <span className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 font-medium">돌파</span>
                                  ) : nearTarget ? (
                                    <span className="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700">근접 {pct}%</span>
                                  ) : (
                                    <span className="px-1.5 py-0.5 rounded text-xs bg-blue-50 text-blue-600">{pct}%</span>
                                  )}
                                </td>
                              </tr>
                            )
                          })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )
            })()}
          </>
        )
      })()}

      {/* 매수 신호 이력 */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 mb-2">최근 매수 신호</h4>
        {signals.length === 0 ? (
          <p className="text-xs text-gray-400">신호 없음</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-1 pr-2">시각</th>
                  {isAll && strategyKeys.length > 1 && (
                    <th className="pb-1 pr-2">전략</th>
                  )}
                  <th className="pb-1 pr-2">종목</th>
                  <th className="pb-1 pr-2 text-right">현재가</th>
                  <th className="pb-1 text-right">등락률</th>
                </tr>
              </thead>
              <tbody>
                {[...signals].reverse().map((s, i) => {
                  const color = s.strategyKey ? getStrategyColor(s.strategyKey) : null
                  return (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-1 pr-2 text-gray-500">{s.time}</td>
                      {isAll && strategyKeys.length > 1 && (
                        <td className="py-1 pr-2">
                          {color && (
                            <span className={`px-1.5 py-0.5 rounded text-xs ${color.badge}`}>
                              {s.strategyName}
                            </span>
                          )}
                        </td>
                      )}
                      <td className="py-1 pr-2 font-medium">
                        {s.name ? `${s.name}(${s.ticker})` : s.ticker}
                      </td>
                      <td className="py-1 pr-2 text-right">{s.price.toLocaleString()}</td>
                      <td className="py-1 text-right text-red-500">+{s.change_rate}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
