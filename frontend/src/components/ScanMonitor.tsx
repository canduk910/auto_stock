import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from '../api/trading'
import { getStrategyColor } from '../types/strategy'
import type { BuySignal, ScanStats } from '../types/trading'

interface BreakoutTarget {
  k: number
  target_price: number
  open_price: number
  target_offset: number
  open_confirmed: boolean
  limit_up_reached?: boolean
}

interface SwingTarget {
  prev_close: number
  atr: number
  ema60: number
  donchian_high: number
}

const SWING_KEY = 'donchian_swing'

const SWING_STAGES: Array<{ key: keyof ScanStats; label: string }> = [
  { key: 'universe_candidates', label: '코스피200+코스닥150 합집합' },
  { key: 'universe_filtered', label: '시총 컷 통과' },
  { key: 'candle_fetch_ok', label: '일봉 fetch + 전일종가>0' },
  { key: 'donchian_pass', label: '20일 신고가 돌파' },
  { key: 'ema_uptrend_pass', label: '60일 EMA 우상향 + 종가>EMA' },
  { key: 'volume_pass', label: '거래대금 ≥ 20일평균×1.5' },
  { key: 'atr_pass', label: 'ATR(14) > 0' },
  { key: 'final_prepared', label: '최종 후보' },
]

function formatRunAt(iso?: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('ko-KR', { hour12: false })
  } catch {
    return iso
  }
}

function getKstMinutes(): number {
  // 클라이언트 시간대와 무관하게 KST(Asia/Seoul) 분 단위(0~1439) 반환
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  }).formatToParts(new Date())
  const h = parseInt(parts.find((p) => p.type === 'hour')?.value ?? '0', 10)
  const m = parseInt(parts.find((p) => p.type === 'minute')?.value ?? '0', 10)
  return h * 60 + m
}

const SWING_ENTRY_START_MIN = 9 * 60 + 5    // 09:05
const SWING_ENTRY_END_MIN = 9 * 60 + 30     // 09:30 (exclusive)
const SWING_GAP_SKIP_PCT = 3.0              // donchian DEFAULT_PARAMS.gap_skip_threshold

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  idle: { label: '대기', color: 'bg-gray-100 text-gray-700' },
  booting: { label: '기동 중', color: 'bg-yellow-100 text-yellow-700' },
  next_day_clear: { label: '익일 청산', color: 'bg-orange-100 text-orange-700' },
  scanning: { label: '종목 스캔', color: 'bg-blue-100 text-blue-700' },
  trading: { label: '매매 중', color: 'bg-green-100 text-green-700' },
  buy_stopped: { label: '매수 중단', color: 'bg-amber-100 text-amber-700' },
  closing: { label: '장 마감', color: 'bg-purple-100 text-purple-700' },
  settling: { label: '정산 중', color: 'bg-indigo-100 text-indigo-700' },
  vb_trading: { label: '돌파 매매 중', color: 'bg-teal-100 text-teal-700' },
  presubscribe_wait: { label: '사전 구독 대기', color: 'bg-sky-100 text-sky-700' },
}

const BREAKOUT_KEYS = ['volatility_breakout', 'long_tail_volatility'] as const
const BREAKOUT_LABELS: Record<string, string> = {
  volatility_breakout: '변동성 돌파',
  long_tail_volatility: '롱테일 변동성',
}

interface Props {
  selectedStrategy: string
}

export default function ScanMonitor({ selectedStrategy }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [swingExpanded, setSwingExpanded] = useState(false)

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
  const isBreakout = (BREAKOUT_KEYS as readonly string[]).includes(selectedStrategy)
  const isSwing = selectedStrategy === SWING_KEY
  const swingStrat = strategies[SWING_KEY]
  const swingStats: ScanStats | null = swingStrat?.scan_stats ?? null
  const swingCount = swingStrat?.scanned_count ?? 0

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

      {/* 스캔 요약 */}
      {(() => {
        const showMomentumScan = isAll || selectedStrategy === 'momentum'
        const breakoutCounts: Record<string, number> = {}
        for (const k of BREAKOUT_KEYS) {
          breakoutCounts[k] = strategies[k]?.scanned_count ?? 0
        }
        const selectedBreakoutCount = isBreakout ? breakoutCounts[selectedStrategy] : 0
        // swing 탭이면 최종 후보 수, 아니면 기존 분기
        const summaryCount = isSwing
          ? swingCount
          : (showMomentumScan ? (scan?.filtered_count ?? 0) : selectedBreakoutCount)
        const summaryLabel = isSwing
          ? '신고가 후보'
          : (isAll ? '모멘텀 필터' : '필터링')

        return (
          <>
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{summaryCount}</div>
                <div className="text-xs text-gray-500">{summaryLabel}</div>
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

            {/* 전체 탭: 돌파 전략별 카운트 */}
            {isAll && BREAKOUT_KEYS.map((k) => {
              const c = breakoutCounts[k]
              if (!c) return null
              return (
                <div key={k} className="mb-2 px-2 py-1.5 bg-indigo-50 rounded text-xs text-indigo-700">
                  {BREAKOUT_LABELS[k]} 스캔: {c}종목 (09:00:05~ 매매)
                </div>
              )
            })}

            {/* 전체 탭: 스윙 한 줄 요약 (donchian) */}
            {isAll && swingStrat?.enabled && (
              <div className="mb-2 px-2 py-1.5 bg-emerald-50 rounded text-xs text-emerald-700">
                20일 신고가 스윙: 유니버스 {swingStats?.universe_filtered ?? 0}/
                {swingStats?.universe_candidates ?? 0} → 최종 후보 {swingCount}종목
                {swingStats?.last_run_at && (
                  <span className="ml-2 text-emerald-500">({formatRunAt(swingStats.last_run_at)})</span>
                )}
              </div>
            )}

            {/* 돌파 탭(VB/LTV): 운영시각 안내 */}
            {isBreakout && (
              <div className="mb-3 px-2 py-1.5 bg-teal-50 rounded text-xs text-teal-700 flex items-center justify-between">
                <span>매매 시간: 09:00:05 ~ 15:20 (시가 확정 직후 시작)</span>
                <span className="text-teal-500">
                  {selectedBreakoutCount > 0 ? `${selectedBreakoutCount}종목 감시 중` : ''}
                </span>
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

            {/* 스윙 전용 탭(donchian_swing): 깔때기 통계 + 후보 종목 테이블 */}
            {isSwing && (() => {
              const stats = swingStats
              const universeMax = Math.max(
                stats?.universe_candidates ?? 0,
                stats?.universe_filtered ?? 0,
                1,
              )
              const stages = SWING_STAGES.map((stg) => ({
                ...stg,
                value: (stats?.[stg.key] as number | undefined) ?? 0,
              }))
              const lastRunAt = stats?.last_run_at ?? null

              const targets = (swingStrat?.targets ?? {}) as Record<string, SwingTarget>
              const targetEntries = Object.entries(targets)

              const positionsDetail = swingStrat?.positions_detail ?? {}
              const kstMin = getKstMinutes()
              const gapSkipPct =
                Number((swingStrat?.params as Record<string, unknown> | undefined)?.gap_skip_threshold) ||
                SWING_GAP_SKIP_PCT

              return (
                <div className="mb-4">
                  <div className="mb-3 px-3 py-2 bg-emerald-50 border border-emerald-100 rounded text-xs text-emerald-800">
                    <div className="font-medium mb-1">진입 케이스 — 다음 영업일 09:05~09:30 KST</div>
                    <ul className="space-y-0.5 text-emerald-700 list-disc pl-4">
                      <li>전일 종가가 <b>20일 신고가 돌파</b> + 60일 EMA 우상향 + 종가&gt;EMA + 거래대금 ≥ 20일평균×1.5 (prepare 단계 통과)</li>
                      <li>익일 09:05~09:30 사이 시장가 매수 — <b>1종목당 1회</b>만 시도</li>
                      <li>시가가 전일 종가 대비 <b>+{gapSkipPct.toFixed(0)}%↑ 갭상승</b>이면 스킵 (추격 방지)</li>
                      <li>청산: ATR(14)×2 트레일링 + 하드 손절 -7% (시간 청산 없음, 멀티데이 보유)</li>
                    </ul>
                    <div className="mt-1 text-emerald-500">마지막 스캔 {formatRunAt(lastRunAt)}</div>
                  </div>

                  {/* 단계별 깔때기 — 어디서 0이 되는지 한눈에 */}
                  <div className="border border-gray-200 rounded p-3 mb-3">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-medium text-gray-700">
                        조건 통과 단계별 후보 수
                      </h4>
                      {!stats && (
                        <span className="text-xs text-gray-400">아직 스캔 전</span>
                      )}
                    </div>
                    <div className="space-y-1">
                      {stages.map((stg, i) => {
                        const widthPct = Math.round((stg.value / universeMax) * 100)
                        const isZero = stg.value === 0
                        const isFinal = stg.key === 'final_prepared'
                        const barColor = isZero
                          ? 'bg-rose-200'
                          : isFinal
                            ? 'bg-emerald-400'
                            : 'bg-emerald-200'
                        return (
                          <div key={stg.key as string} className="flex items-center gap-2 text-xs">
                            <div className="w-7 text-right text-gray-400 font-mono">{i + 1}.</div>
                            <div className="flex-1">
                              <div className="flex items-baseline justify-between mb-0.5">
                                <span className={isZero ? 'text-rose-600 font-medium' : 'text-gray-700'}>
                                  {stg.label}
                                </span>
                                <span
                                  className={`font-mono font-medium ${
                                    isZero ? 'text-rose-600' : isFinal ? 'text-emerald-700' : 'text-gray-700'
                                  }`}
                                >
                                  {stg.value}
                                </span>
                              </div>
                              <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                                <div
                                  className={`h-full ${barColor}`}
                                  style={{ width: `${Math.max(widthPct, stg.value > 0 ? 4 : 0)}%` }}
                                />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    {stats && stats.final_prepared === 0 && (
                      <p className="mt-3 text-xs text-rose-600">
                        최종 후보 0종목 — 위에서 처음으로 0이 되는 단계가 탈락 원인입니다.
                      </p>
                    )}
                  </div>

                  {/* 최종 후보 종목 테이블 */}
                  {targetEntries.length === 0 ? (
                    <p className="text-xs text-gray-400">
                      {swingCount > 0
                        ? `${swingCount}종목 후보 — 신호 데이터 대기 중`
                        : '최종 후보 종목이 없습니다.'}
                    </p>
                  ) : (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-medium text-gray-700">
                          최종 후보 ({targetEntries.length}종목)
                        </h4>
                        <button
                          onClick={() => setSwingExpanded((v) => !v)}
                          className="text-xs text-blue-600 hover:underline"
                        >
                          {swingExpanded ? '접기' : '펼치기'}
                        </button>
                      </div>
                      {swingExpanded && (
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-gray-500 border-b">
                                <th className="pb-1 pr-2">종목</th>
                                <th className="pb-1 pr-2 text-right">전일종가</th>
                                <th className="pb-1 pr-2 text-right">20일 신고가</th>
                                <th className="pb-1 pr-2 text-right">EMA60</th>
                                <th className="pb-1 pr-2 text-right">ATR(14)</th>
                                <th className="pb-1 pr-2 text-right">현재가</th>
                                <th className="pb-1 pr-2 text-right">갭률</th>
                                <th className="pb-1 text-center">진입 상태</th>
                              </tr>
                            </thead>
                            <tbody>
                              {targetEntries
                                .sort(([, a], [, b]) => (b.prev_close || 0) - (a.prev_close || 0))
                                .map(([ticker, t]) => {
                                  const name = scan?.ticker_names?.[ticker] ?? ''
                                  const priceInfo = scan?.ticker_prices?.[ticker]
                                  const curPrice = priceInfo?.current_price ?? 0
                                  const openPrice = priceInfo?.open_price ?? 0
                                  const gapPct =
                                    openPrice > 0 && t.prev_close > 0
                                      ? ((openPrice - t.prev_close) / t.prev_close) * 100
                                      : null
                                  const isHeld = ticker in positionsDetail
                                  const gapSkipped = gapPct !== null && gapPct >= gapSkipPct

                                  let badgeLabel: string
                                  let badgeCls: string
                                  if (isHeld) {
                                    badgeLabel = '보유 중'
                                    badgeCls = 'bg-emerald-100 text-emerald-700'
                                  } else if (gapSkipped) {
                                    badgeLabel = '갭 스킵'
                                    badgeCls = 'bg-gray-100 text-gray-500'
                                  } else if (kstMin < SWING_ENTRY_START_MIN) {
                                    badgeLabel = '장 시작 전'
                                    badgeCls = 'bg-slate-100 text-slate-600'
                                  } else if (kstMin >= SWING_ENTRY_END_MIN) {
                                    // 진입 시간(09:30) 이후 — 오늘은 진입 못함, 다음 영업일 대기
                                    badgeLabel = '진입 시간 종료'
                                    badgeCls = 'bg-amber-100 text-amber-700'
                                  } else {
                                    badgeLabel = '진입 대기'
                                    badgeCls = 'bg-blue-100 text-blue-700'
                                  }

                                  return (
                                    <tr key={ticker} className="border-b border-gray-50">
                                      <td className="py-1 pr-2 font-medium">
                                        {name ? `${name}(${ticker})` : ticker}
                                      </td>
                                      <td className="py-1 pr-2 text-right">
                                        {t.prev_close ? t.prev_close.toLocaleString() : '-'}
                                      </td>
                                      <td className="py-1 pr-2 text-right text-emerald-700 font-medium">
                                        {t.donchian_high ? t.donchian_high.toLocaleString() : '-'}
                                      </td>
                                      <td className="py-1 pr-2 text-right text-gray-600">
                                        {t.ema60 ? t.ema60.toLocaleString() : '-'}
                                      </td>
                                      <td className="py-1 pr-2 text-right text-gray-600">
                                        {t.atr ? t.atr.toLocaleString() : '-'}
                                      </td>
                                      <td className="py-1 pr-2 text-right">
                                        {curPrice > 0 ? curPrice.toLocaleString() : '-'}
                                      </td>
                                      <td
                                        className={`py-1 pr-2 text-right font-mono ${
                                          gapPct === null
                                            ? 'text-gray-400'
                                            : gapPct >= 0
                                              ? 'text-red-500'
                                              : 'text-blue-500'
                                        }`}
                                      >
                                        {gapPct === null ? '-' : `${gapPct >= 0 ? '+' : ''}${gapPct.toFixed(2)}%`}
                                      </td>
                                      <td className="py-1 text-center">
                                        <span className={`px-1.5 py-0.5 rounded text-xs ${badgeCls}`}>
                                          {badgeLabel}
                                        </span>
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
                </div>
              )
            })()}

            {/* 돌파 전용 탭(VB/LTV): 종목 스캔 + 타겟 가격 테이블 */}
            {isBreakout && (() => {
              const strat = strategies[selectedStrategy]
              const targets = (strat?.targets ?? {}) as Record<string, BreakoutTarget>
              const targetEntries = Object.entries(targets)
              if (targetEntries.length === 0) {
                return (
                  <div className="mb-4">
                    <p className="text-xs text-gray-400">
                      {selectedBreakoutCount > 0
                        ? `${selectedBreakoutCount}종목 스캔 완료 — K값 계산 대기 중`
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
                                  {t.limit_up_reached ? (
                                    <span className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-700 font-medium">상한가 모드</span>
                                  ) : !t.open_confirmed ? (
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
