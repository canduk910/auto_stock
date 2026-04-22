import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from '../api/trading'

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  idle: { label: '대기', color: 'bg-gray-100 text-gray-700' },
  booting: { label: '기동 중', color: 'bg-yellow-100 text-yellow-700' },
  next_day_clear: { label: '익일 청산', color: 'bg-orange-100 text-orange-700' },
  scanning: { label: '종목 스캔', color: 'bg-blue-100 text-blue-700' },
  trading: { label: '매매 중', color: 'bg-green-100 text-green-700' },
  buy_stopped: { label: '매수 중단', color: 'bg-amber-100 text-amber-700' },
  closing: { label: '장 마감', color: 'bg-purple-100 text-purple-700' },
  settling: { label: '정산 중', color: 'bg-indigo-100 text-indigo-700' },
}

export default function ScanMonitor() {
  const [expanded, setExpanded] = useState(false)

  const { data: status } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
  })

  const phase = status?.phase ?? 'idle'
  const scan = status?.scan
  const signals = status?.strategy?.buy_signals ?? []
  const phaseInfo = PHASE_LABELS[phase] ?? PHASE_LABELS.idle

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">조건검색 현황</h3>
        <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${phaseInfo.color}`}>
          {phaseInfo.label}
        </span>
      </div>

      {/* 스캔 요약 */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center p-2 bg-gray-50 rounded">
          <div className="text-lg font-bold text-gray-900">{scan?.filtered_count ?? 0}</div>
          <div className="text-xs text-gray-500">필터링</div>
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

      {/* 구독 종목 리스트 + 실시간 등락률 */}
      {scan && scan.filtered_count > 0 && (
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
                    .sort((a, b) => (scan.ticker_prices?.[b]?.prdy_ctrt ?? 0) - (scan.ticker_prices?.[a]?.prdy_ctrt ?? 0))
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
                          <td className={`py-1 pr-2 text-right font-medium ${rate >= 29 ? 'text-red-600 font-bold' : rate >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
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
                  <th className="pb-1 pr-2">종목</th>
                  <th className="pb-1 pr-2 text-right">현재가</th>
                  <th className="pb-1 text-right">등락률</th>
                </tr>
              </thead>
              <tbody>
                {[...signals].reverse().map((s, i) => (
                  <tr key={i} className="border-b border-gray-50">
                    <td className="py-1 pr-2 text-gray-500">{s.time}</td>
                    <td className="py-1 pr-2 font-medium">{s.name ? `${s.name}(${s.ticker})` : s.ticker}</td>
                    <td className="py-1 pr-2 text-right">{s.price.toLocaleString()}</td>
                    <td className="py-1 text-right text-red-500">+{s.change_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
