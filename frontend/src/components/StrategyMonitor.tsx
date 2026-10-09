/**
 * cycle414 — 전략별 진행상황 상세 패널(명세 `_workspace/red/cycle414/monitor_spec.md` §2·§4).
 *
 * 공통 7칸(①상태 ②시간표 ③깔때기 ④후보 ⑤사유 ⑥진입기록 ⑦보유방어선) 틀로 전략별 진행상황을
 * 그린다. 가벼운 패널(VB·momentum·LTV)은 ①②③⑥만, 고지로는 기존 `KojiroMonitor` 로 그린다.
 *
 * 데이터 출처 — `/api/trading/status`(strategies) · `/api/strategies/monitor`(funnel·candidates·
 * holdings·skips·market_unit·prepare·ticks, 실패 시 null → scan_stats 폴백) · `/api/balance/exit-lines`
 * (보유 실효 손절선 정본) · `/api/strategy-funnel/recent`(14일 추이).
 */
import { useMemo } from 'react'
import type {
  StrategyInfo, TickerPrice, ExitLineItem, StrategyMonitorResponse,
  MonitorFunnelStep, MonitorPrepareMeta,
} from '../types/trading'
import { formatKstHHMM } from '../utils/kst'
import {
  strategyStatus, funnelBottleneck, entryWindow, signalBaseline, marketUnitBlockLabel,
  SKIP_REASON_LABELS, type MonitorTone, type StrategyStatusResult,
} from '../utils/strategyMonitor'
import { computeZeroStreak } from '../pages/StrategyFunnel'
import KojiroMonitor from './KojiroMonitor'
import ScrollPane from './ScrollPane'

type Dict = Record<string, unknown>

const FULL_PANEL_SIDS = new Set(['etf_trend', 'donchian_swing', 'vcp_breakout', 'bull_flag_breakout'])

const PRIMARY_CLS: Record<StrategyStatusResult['primary'], string> = {
  off: 'bg-gray-100 text-gray-600',
  paused: 'bg-amber-100 text-amber-800',
  shadow: 'bg-violet-100 text-violet-800',
  live: 'bg-emerald-100 text-emerald-800',
}

const CHIP_CLS: Record<MonitorTone, string> = {
  red: 'bg-rose-100 text-rose-700 font-semibold',
  orange: 'bg-amber-100 text-amber-700',
  gray: 'bg-gray-100 text-gray-600',
  violet: 'bg-violet-100 text-violet-700',
}

/** 라우트 funnel 이 없을 때의 폴백 단계 라벨(엔진 이름 그대로 — 낡은 상수 라벨 금지, §6 C3). */
const FALLBACK_STAGES: Record<string, Array<{ key: string; label: string }>> = {
  donchian_swing: [
    { key: 'universe_union', label: '코스피200+코스닥150 합집합' },
    { key: 'universe_filtered', label: '시총+거래대금 컷 통과' },
    { key: 'candle_fetch_ok', label: '일봉 fetch + 전일종가>0' },
    { key: 'donchian_pass', label: '20일 신고가 돌파' },
    { key: 'ema_uptrend_pass', label: '60일 EMA 우상향 + 종가>EMA' },
    { key: 'volume_pass', label: '거래대금 확대' },
    { key: 'atr_pass', label: 'ATR(14) > 0' },
    { key: 'final_prepared', label: '최종 후보' },
  ],
  vcp_breakout: [
    { key: 'universe_union', label: '전체 상장 유니버스' },
    { key: 'universe_candidates', label: '시총·거래대금 컷 통과' },
    { key: 'universe_filtered', label: '유니버스 확정' },
    { key: 'candle_fetch_ok', label: '일봉 fetch + 추세필터' },
    { key: 'trend_filter_pass', label: '단기/중기/장기 EMA 정렬' },
    { key: 'base_pass', label: '베이스 자동 검출' },
    { key: 'pullback_pass', label: 'Pullback 점진 수축' },
    { key: 'volume_contraction_pass', label: '거래량 수축' },
    { key: 'final_prepared', label: '최종 후보' },
  ],
  bull_flag_breakout: [
    { key: 'universe_union', label: '전체 상장 유니버스' },
    { key: 'universe_candidates', label: '시총·거래대금 컷 통과' },
    { key: 'universe_filtered', label: '유니버스 확정' },
    { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
    { key: 'pole_pass', label: '폴(Pole) 자동 검출' },
    { key: 'flag_pass', label: '플래그(Flag) 자동 검출' },
    { key: 'volume_contraction_pass', label: '거래량 수축' },
    { key: 'atr_pass', label: 'ATR(14) > 0' },
    { key: 'final_prepared', label: '최종 후보' },
  ],
}

function pnum(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? String(n) : '—'
}

function finiteOrNull(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

function won(v: unknown): string {
  const n = finiteOrNull(v)
  return n === null ? '—' : Math.round(n).toLocaleString()
}

function mmdd(dateStr: string | undefined | null): string {
  if (!dateStr) return '—'
  return dateStr.length >= 10 ? dateStr.slice(5, 10) : dateStr
}

function tickAgeSec(lastTickAt: string | null | undefined, now: Date): number | null {
  if (!lastTickAt) return null
  const t = Date.parse(lastTickAt)
  if (Number.isNaN(t)) return null
  return (now.getTime() - t) / 1000
}

/** 기준일 머리말(§2.5) — 아침 준비 / 저녁 미리보기(잠정) / 준비 중 / 준비 실패. */
function prepareHeader(prepare: MonitorPrepareMeta | null | undefined): { text: string; fail: boolean } {
  if (!prepare) return { text: '기준일 모름 — 준비 정보 없음', fail: false }
  const day = mmdd(prepare.as_of)
  if (prepare.ok === null || prepare.ok === undefined) {
    return { text: `기준일 ${day} · 준비 중…`, fail: false }
  }
  const hhmm = formatKstHHMM(prepare.finished_at ?? prepare.started_at)
  if (prepare.ok === false) {
    return { text: `기준일 ${day} · 준비 실패 ${hhmm}`, fail: true }
  }
  const label = prepare.phase === 'evening' ? '저녁 미리보기(잠정)' : '아침 준비'
  return { text: `기준일 ${day} · ${label} ${hhmm} 완료`, fail: false }
}

interface Props {
  strategyId: string
  strategies: Record<string, StrategyInfo>
  monitor?: StrategyMonitorResponse | null
  exitLines?: ExitLineItem[] | null
  tickerPrices?: Record<string, TickerPrice>
  tickerNames?: Record<string, string>
  subscribedTickers?: string[]
  funnelTrend?: Array<{ date: string; count: number }> | null
  now?: Date
}

export default function StrategyMonitor({
  strategyId, strategies, monitor, exitLines, tickerPrices, tickerNames, subscribedTickers, funnelTrend, now,
}: Props) {
  const info = strategies[strategyId]
  const nowDate = now ?? new Date()

  // 고지로는 기존 KojiroMonitor(id 보존)로 그린다 — §4.5.
  if (strategyId === 'kojiro') {
    return (
      <KojiroMonitor
        strategies={strategies}
        tickerPrices={tickerPrices}
        exitLines={exitLines ?? undefined}
        monitor={monitor ?? undefined}
      />
    )
  }

  const routeEntry = monitor?.strategies?.[strategyId] ?? null
  const marketUnit = routeEntry?.market_unit ?? null
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const status = useMemo(() => (info ? strategyStatus(strategyId, info, marketUnit) : null), [strategyId, info, marketUnit])

  const params = (info?.params ?? {}) as Dict
  const prices = tickerPrices ?? {}
  const names = tickerNames ?? {}
  const subscribedSet = useMemo(() => new Set(subscribedTickers ?? []), [subscribedTickers])
  const exitLineMap = useMemo(() => {
    const m = new Map<string, ExitLineItem>()
    for (const item of exitLines ?? []) if (item.strategy_id === strategyId) m.set(item.ticker, item)
    return m
  }, [exitLines, strategyId])

  if (!info || !status) {
    return (
      <div data-testid={`${strategyId}-monitor-empty`} className="text-sm text-gray-400 py-4 text-center">
        전략 데이터가 아직 없습니다.
      </div>
    )
  }

  const isFull = FULL_PANEL_SIDS.has(strategyId)
  const weightPct = Math.round((info.weight ?? 0) * 100)
  const targets = (info.targets ?? {}) as Record<string, Dict>

  // ── 종목명 — targets[t].name → ticker_names → 코드(§2.6) ──
  const nameOf = (ticker: string): string => {
    const t = targets[ticker]
    return (t && typeof t.name === 'string' && t.name) || names[ticker] || ticker
  }

  // ───────────────────────────── ③ 깔때기 ─────────────────────────────
  const steps: MonitorFunnelStep[] = routeEntry?.funnel ?? []
  const bottleneckNo = funnelBottleneck(steps)
  const finalStep = steps.find((s) => s.step_no === 99)
  const finalZero = finalStep ? finalStep.survived_count === 0 : false
  const bottleneckStep = bottleneckNo != null ? steps.find((s) => s.step_no === bottleneckNo) : null
  const trendZeroStreak = funnelTrend && funnelTrend.length > 0 ? computeZeroStreak(funnelTrend) : 0
  const trendMax = funnelTrend ? Math.max(1, ...funnelTrend.map((d) => d.count)) : 1

  function renderFunnelPanel() {
    if (steps.length > 0) {
      const maxVal = Math.max(1, ...steps.map((s) => s.survived_count))
      return (
        <>
          <div className="space-y-1">
            {[...steps].sort((a, b) => a.step_no - b.step_no).map((row) => {
              const widthPct = Math.round((row.survived_count / maxVal) * 100)
              const isBottleneck = row.step_no === bottleneckNo
              const zero = row.survived_count === 0
              return (
                <div
                  key={row.step_no}
                  data-testid={`${strategyId}-monitor-funnel-row-${row.step_no}`}
                  className="flex items-center gap-2 text-xs"
                >
                  <span className="flex-1 text-gray-600">
                    {row.step_no}. {row.step_name}
                    {row.step_conditions && <span className="ml-1 text-[10px] text-gray-400">{row.step_conditions}</span>}
                    {isBottleneck && <span className="ml-1 text-rose-600 font-semibold">← 여기서 0</span>}
                  </span>
                  <div className="w-24 h-2 bg-gray-100 rounded overflow-hidden shrink-0">
                    <div className={`h-2 ${zero ? 'bg-rose-300' : 'bg-violet-300'}`} style={{ width: `${widthPct}%` }} />
                  </div>
                  <span className={`w-10 text-right ${zero ? 'text-rose-600 font-medium' : 'text-gray-700'}`}>{row.survived_count}</span>
                </div>
              )
            })}
          </div>
          {finalZero && bottleneckStep && (
            <div className="mt-1 text-xs text-rose-600">
              최종 후보 0 — {bottleneckStep.step_no}단계({bottleneckStep.step_name})에서 전부 걸렸습니다
            </div>
          )}
          {funnelTrend && funnelTrend.length > 0 && (
            <div className="mt-2">
              <div className="flex items-end gap-0.5 h-8">
                {funnelTrend.map((d) => (
                  <div
                    key={d.date}
                    title={`${d.date}: ${d.count}건`}
                    className={`flex-1 rounded-t ${d.count === 0 ? 'bg-rose-300' : 'bg-blue-300'}`}
                    style={{ height: `${Math.max(4, Math.round((d.count / trendMax) * 100))}%` }}
                  />
                ))}
              </div>
              {trendZeroStreak > 0 && (
                <div className="text-[11px] text-rose-600 mt-0.5">0 연속 {trendZeroStreak}일</div>
              )}
            </div>
          )}
        </>
      )
    }

    // 라우트 funnel 이 없을 때의 폴백 — §4.1 끝 (ETF 는 1행·최종만).
    if (strategyId === 'etf_trend') {
      const ss = (info.scan_stats ?? {}) as Dict
      const universe = finiteOrNull(ss.universe)
      const candidates = finiteOrNull(ss.candidates)
      return (
        <div className="space-y-1 text-xs text-gray-600">
          <div data-testid="etf_trend-monitor-funnel-row-1">1. 전체 통과 — {universe ?? '—'}</div>
          <div data-testid="etf_trend-monitor-funnel-row-99">99. 최종 후보 — {candidates ?? '—'}</div>
        </div>
      )
    }
    const fallback = FALLBACK_STAGES[strategyId]
    if (fallback) {
      const ss = (info.scan_stats ?? {}) as Dict
      return (
        <div className="space-y-1 text-xs text-gray-600">
          {fallback.map((stg, i) => (
            <div key={stg.key} data-testid={`${strategyId}-monitor-funnel-row-${i + 1}`}>
              {i + 1}. {stg.label} — {finiteOrNull(ss[stg.key]) ?? 0}
            </div>
          ))}
        </div>
      )
    }
    return <div className="text-xs text-gray-400">아직 스캔 전</div>
  }

  // ───────────────────────────── ② 시간표 ─────────────────────────────
  function renderTimeline() {
    const win = entryWindow(strategyId, params, nowDate)
    if (!win) return <span>시간표 정보 없음(전략별 설정을 확인하세요)</span>
    const stateLabel = win.state === 'before' ? '열리기 전' : win.state === 'open' ? '열림' : '닫힘'
    return (
      <span>
        진입창 {win.start}~{win.end}(KST{win.fixed ? ' · 코드 고정' : ''}) · {stateLabel}
      </span>
    )
  }

  // ───────────────────────────── ⑤ 사유 ─────────────────────────────
  function renderSkipsPanel() {
    if (status!.primary === 'paused') {
      const n = routeEntry?.paused_skips?.length ?? 0
      return (
        <div>멈춤 중 — 엔진은 멈춤 관문에서 돌아가 다른 사유를 남기지 않습니다. 오늘 멈춤으로 건너뛴 종목 {n}</div>
      )
    }
    const skips = routeEntry?.skips
    if (!skips || skips.known === false) {
      return <div>이 전략은 종목별 거르기 사유를 기록하지 않습니다.</div>
    }
    const counts = skips.counts ?? {}
    const entries = Object.entries(counts).filter(([, v]) => Number.isFinite(v) && v > 0)
    if (entries.length === 0) return <div>오늘 거르기 사유 없음</div>
    return (
      <ul className="space-y-0.5">
        {entries.map(([reason, count]) => (
          <li key={reason}>{SKIP_REASON_LABELS[reason] ?? reason} — {count}종목</li>
        ))}
      </ul>
    )
  }

  // ───────────────────────────── ⑥ 진입 기록 ─────────────────────────────
  function renderEntriesPanel() {
    const buySignals = info.buy_signals ?? []
    const shadowBuys = routeEntry?.shadow_buys ?? []
    const isShadow = status!.primary === 'shadow'
    return (
      <div className="space-y-2 text-xs">
        <div className="text-gray-600">
          매수 신호 {buySignals.length}
          {isShadow && buySignals.length === 0 && (
            <span className="ml-1 text-gray-400">(섀도 BUY 는 매수 신호에 남지 않습니다 — 「매수 신호 0」이 「섀도가 안 돈다」가 아닙니다)</span>
          )}
        </div>
        {buySignals.length > 0 && (
          <ul className="space-y-0.5">
            {buySignals.slice().reverse().map((sig, i) => {
              const sb = signalBaseline(strategyId, sig as unknown as Dict)
              return (
                <li key={`${sig.ticker}-${i}`} className="text-gray-700">
                  {sig.time} {sig.name || sig.ticker} 매수 {won(sig.price)}
                  {sb.baseline != null && <> · 기준선 {won(sb.baseline)}</>}
                  {sb.changeRate != null && <> · {sb.changeRate >= 0 ? '+' : ''}{sb.changeRate}%</>}
                </li>
              )
            })}
          </ul>
        )}
        {shadowBuys.length > 0 && (
          <div className="text-violet-700">
            섀도 기록 {shadowBuys.length}(실전이었으면 샀을 종목 {shadowBuys.length}): {shadowBuys.join(', ')}
          </div>
        )}
      </div>
    )
  }

  // ── LTV 류 — 보유 손절선이 모드에 따라 달라 화면이 하나로 고르지 않는 경우(§4.8) ──
  const modeDependentTicker = [...exitLineMap.values()].find((it) => it.stop_source === 'mode_dependent')

  // ───────────────────────────── ④ 후보 (full 전용) ─────────────────────────────
  function etfCandidateStatus(ticker: string, includePause: boolean): string {
    const age = tickAgeSec(routeEntry?.ticks?.[ticker]?.last_tick_at, nowDate)
    if (!subscribedSet.has(ticker) || age === null || age > 60) return '시세 없음'
    if ((info.position_tickers ?? []).includes(ticker)) return '보유 중'
    if ((info.pending_buy_tickers ?? []).includes(ticker)) return '주문 중'
    const byTicker = (routeEntry?.skips?.by_ticker?.[ticker] ?? []) as string[]
    if (byTicker.length > 0) {
      if (byTicker.includes('gap_up') || byTicker.includes('gap_over_line')) return '오늘 갭 스킵'
      return '오늘 시도함'
    }
    if (includePause && status!.primary === 'paused') return '멈춤'
    if (info.buy_disabled) return '매수 중단'
    const maxPositions = Number(params.max_positions)
    if (Number.isFinite(maxPositions) && maxPositions > 0 && (info.positions ?? 0) >= maxPositions) return '보유 한도'
    const win = entryWindow('etf_trend', params, nowDate)
    if (win?.state === 'before') return `${win.start} 부터`
    if (win?.state === 'after') return '진입창 지남 — 다음 거래일'
    const target = targets[ticker] ?? {}
    const prevClose = finiteOrNull(target.prev_close)
    const price = prices[ticker]
    const openPrice = finiteOrNull(price?.open_price)
    if (openPrice === null || openPrice <= 0) return '시가 미확정'
    const gapSkipPct = finiteOrNull(params.gap_skip_threshold)
    if (gapSkipPct !== null && prevClose !== null && prevClose > 0) {
      const gapPct = ((openPrice - prevClose) / prevClose) * 100
      if (gapPct >= gapSkipPct) return '갭 초과'
    }
    const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
    const line = finiteOrNull(cand.line)
    const gapOverLinePct = finiteOrNull(params.gap_over_line_pct)
    if (line !== null && line > 0 && gapOverLinePct !== null) {
      const overPct = ((openPrice - line) / line) * 100
      if (overPct > gapOverLinePct) return '돌파선 위 과다'
    }
    const curPrice = finiteOrNull(price?.current_price)
    if (curPrice !== null && curPrice < openPrice) return '장중 붕괴'
    if (cand.cluster_blocked) return '묶음 보유로 차단'
    const muBlock = marketUnitBlockLabel('etf_trend', marketUnit)
    if (muBlock) return muBlock
    if (status!.primary !== 'shadow' && (info.weight ?? 0) === 0) return '예산 0'
    const qty = finiteOrNull(cand.design_qty)
    if (qty !== null && qty <= 0) return '1주도 안 됨'
    return '진입 가능'
  }

  function donchianCandidateStatus(ticker: string, includePause: boolean): string {
    const age = tickAgeSec(routeEntry?.ticks?.[ticker]?.last_tick_at, nowDate)
    if (!subscribedSet.has(ticker) || age === null || age > 60) return '시세 없음'
    if ((info.position_tickers ?? []).includes(ticker)) return '보유 중'
    if ((info.pending_buy_tickers ?? []).includes(ticker)) return '주문 중'
    if (includePause && status!.primary === 'paused') return '멈춤'
    if (info.buy_disabled) return '매수 중단'
    const maxPositions = Number(params.max_positions)
    if (Number.isFinite(maxPositions) && maxPositions > 0 && (info.positions ?? 0) >= maxPositions) return '보유 한도'
    const win = entryWindow('donchian_swing', params, nowDate)
    if (win?.state === 'before') return `${win.start} 부터`
    if (win?.state === 'after') return '진입창 지남 — 다음 거래일'
    const target = targets[ticker] ?? {}
    const prevClose = finiteOrNull(target.prev_close)
    const price = prices[ticker]
    const openPrice = finiteOrNull(price?.open_price)
    const gapSkipPct = finiteOrNull(params.gap_skip_threshold)
    if (openPrice !== null && prevClose !== null && prevClose > 0 && gapSkipPct !== null) {
      const gapPct = ((openPrice - prevClose) / prevClose) * 100
      if (gapPct >= gapSkipPct) return '갭 초과'
    }
    const donchianHigh = finiteOrNull(target.donchian_high)
    const curPrice = finiteOrNull(price?.current_price)
    const extCap = finiteOrNull(params.max_breakout_extension_pct)
    if (donchianHigh !== null && donchianHigh > 0 && extCap !== null) {
      const hi = Math.max(curPrice ?? 0, openPrice ?? 0)
      const extPct = ((hi - donchianHigh) / donchianHigh) * 100
      if (extPct > extCap) return '추격 상한 초과'
    }
    const muBlock = marketUnitBlockLabel('donchian_swing', marketUnit)
    if (muBlock) return muBlock
    const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
    const designLot = finiteOrNull(cand.design_lot)
    if (designLot !== null && designLot <= 0) return '설계 랏 0'
    const daily = (routeEntry?.extra?.daily_entries ?? {}) as Dict
    const count = finiteOrNull(daily.count)
    const cap = finiteOrNull(daily.cap)
    if (count !== null && cap !== null && count >= cap) return '하루 신규 상한'
    return '진입 가능'
  }

  function breakoutCandidateStatus(ticker: string, isBfb: boolean): string {
    const sid = isBfb ? 'bull_flag_breakout' : 'vcp_breakout'
    const age = tickAgeSec(routeEntry?.ticks?.[ticker]?.last_tick_at, nowDate)
    if (!subscribedSet.has(ticker) || age === null || age > 60) return '시세 없음'
    if ((info.position_tickers ?? []).includes(ticker)) return '보유 중'
    if ((info.pending_buy_tickers ?? []).includes(ticker)) return '주문 중'
    const target = targets[ticker] ?? {}
    if (target.bought_today) return '오늘 매수'
    if (status!.primary === 'paused') return '멈춤'
    if (info.buy_disabled) return '매수 중단'
    const maxPositions = Number(params.max_positions)
    if (Number.isFinite(maxPositions) && maxPositions > 0 && (info.positions ?? 0) >= maxPositions) return '보유 한도'
    const win = entryWindow(sid, params, nowDate)
    if (win?.state === 'before') return `진입창 밖 — ${win.start} 부터`
    if (win?.state === 'after') return '진입창 밖 — 다음 거래일'
    if (target.in_cooldown) return '쿨다운'
    if (isBfb) {
      const retentionMin = finiteOrNull(params.breakout_retention_minutes)
      if (retentionMin !== null && retentionMin > 0 && target.breakout_seen_at) return '유지 대기'
    }
    const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
    if (cand.latch_armed_at) return '래치: 거래량 대기 중'
    const breakoutLine = finiteOrNull(isBfb ? target.flag_high : target.base_high)
    const cur = finiteOrNull(prices[ticker]?.current_price)
    if (breakoutLine !== null && cur !== null && cur < breakoutLine) return '돌파선 아래'
    const acmlVol = routeEntry?.ticks?.[ticker]?.acml_vol
    if (acmlVol === null || acmlVol === undefined) return '거래량 미관측'
    const volThreshold = finiteOrNull(target.volume_threshold)
    if (volThreshold !== null && volThreshold > 0 && acmlVol < volThreshold) {
      return `거래량 부족 ${Math.round((acmlVol / volThreshold) * 100)}%`
    }
    const extCap = finiteOrNull(params.max_breakout_extension_pct)
    if (breakoutLine !== null && breakoutLine > 0 && extCap !== null && cur !== null) {
      const extPct = ((cur - breakoutLine) / breakoutLine) * 100
      if (extPct > extCap) return '추격 상한 초과'
    }
    const muBlock = marketUnitBlockLabel(sid, marketUnit)
    if (muBlock) return muBlock
    return '진입 가능'
  }

  function renderEtfCandidatesTable() {
    const tickers = Object.keys(targets)
    return (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-left py-1 pr-2">상태</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">돌파선</th>
            <th className="text-right py-1 px-2">예상 수량</th>
            <th className="text-left py-1 pl-2">묶음</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => {
            const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
            const actual = etfCandidateStatus(ticker, true)
            const hint = actual === '멈춤' ? etfCandidateStatus(ticker, false) : null
            const qty = finiteOrNull(cand.design_qty)
            const qtyText = qty === null ? '—' : qty <= 0 ? '1주도 안 됨 — 사지 않음' : `최대 ${qty}주`
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const line = finiteOrNull(cand.line)
            return (
              <tr key={ticker} data-testid={`etf_trend-monitor-candidate-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{nameOf(ticker)}({ticker})</td>
                <td className="py-1 pr-2">
                  <span data-testid={`etf_trend-monitor-status-${ticker}`} className="text-gray-700">{actual}</span>
                  {hint && (
                    <div data-testid={`etf_trend-monitor-unpaused-${ticker}`} className="text-[10px] text-gray-400">
                      풀리면: {hint}
                    </div>
                  )}
                </td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right text-indigo-600">{line !== null ? line.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">
                  <span data-testid={`etf_trend-monitor-qty-${ticker}`} className={qty !== null && qty <= 0 ? 'text-rose-600 font-medium' : 'text-gray-700'}>
                    {qtyText}
                  </span>
                </td>
                <td className="py-1 pl-2 text-gray-500">
                  {cand.cluster_blocked ? `묶음 보유로 차단(상대: ${((cand.cluster_partners as string[]) ?? []).join(', ')})` : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  function renderDonchianCandidatesTable() {
    const tickers = Object.keys(targets)
    return (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-left py-1 pr-2">상태</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">20일 신고가</th>
            <th className="text-right py-1 px-2">1R / R%</th>
            <th className="text-right py-1 pl-2">설계 랏</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => {
            const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
            const statusText = donchianCandidateStatus(ticker, true)
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const dh = finiteOrNull(targets[ticker]?.donchian_high)
            const rWon = finiteOrNull(cand.r_won)
            const rPct = finiteOrNull(cand.r_pct)
            const designLot = finiteOrNull(cand.design_lot)
            return (
              <tr key={ticker} data-testid={`donchian_swing-monitor-candidate-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{nameOf(ticker)}({ticker})</td>
                <td className="py-1 pr-2">
                  <span data-testid={`donchian_swing-monitor-status-${ticker}`} className="text-gray-700">{statusText}</span>
                </td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right text-indigo-600">{dh !== null ? dh.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">
                  {rWon !== null ? rWon.toLocaleString() : '—'} {rPct !== null ? `(${rPct.toFixed(1)}%)` : ''}
                </td>
                <td className="py-1 pl-2 text-right">
                  {designLot !== null && designLot <= 0
                    ? <span className="text-rose-600 font-medium">사지 않음</span>
                    : (designLot !== null ? `${designLot}랏` : '—')}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  function renderBreakoutCandidatesTable(isBfb: boolean) {
    const sid = isBfb ? 'bull_flag_breakout' : 'vcp_breakout'
    const tickers = Object.keys(targets)
    return (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-left py-1 pr-2">상태</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">돌파선</th>
            <th className="text-right py-1 px-2">거래량</th>
            {isBfb && <th className="text-right py-1 px-2">측정목표</th>}
            <th className="text-right py-1 pl-2">래치</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => {
            const target = targets[ticker] ?? {}
            const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
            const statusText = breakoutCandidateStatus(ticker, isBfb)
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const breakoutLine = finiteOrNull(isBfb ? target.flag_high : target.base_high)
            const acmlVol = routeEntry?.ticks?.[ticker]?.acml_vol
            const volThreshold = finiteOrNull(target.volume_threshold)
            const volPct = typeof acmlVol === 'number' && volThreshold !== null && volThreshold > 0
              ? Math.round((acmlVol / volThreshold) * 100)
              : null
            const latchAt = typeof cand.latch_armed_at === 'string' ? cand.latch_armed_at : null
            const retentionMin = finiteOrNull(params.breakout_retention_minutes)
            const showRetention = isBfb && retentionMin !== null && retentionMin > 0
            return (
              <tr key={ticker} data-testid={`${sid}-monitor-candidate-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{nameOf(ticker)}({ticker})</td>
                <td className="py-1 pr-2">
                  <span data-testid={`${sid}-monitor-status-${ticker}`} className="text-gray-700">{statusText}</span>
                  {showRetention && (
                    <div data-testid={`${sid}-monitor-retention-${ticker}`} className="text-[10px] text-amber-600">유지 대기</div>
                  )}
                </td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right text-indigo-600">{breakoutLine !== null ? breakoutLine.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">
                  <span data-testid={`${sid}-monitor-volgauge-${ticker}`} className="text-gray-700">
                    {volPct !== null ? `${volPct}%` : '거래량 미관측'}
                  </span>
                </td>
                {isBfb && (
                  <td className="py-1 px-2 text-right text-gray-600">
                    {finiteOrNull(target.measured_target) !== null ? (finiteOrNull(target.measured_target) as number).toLocaleString() : '—'}
                  </td>
                )}
                <td className="py-1 pl-2 text-right">
                  {!isBfb && (
                    <span data-testid={`vcp_breakout-monitor-latch-${ticker}`} className="text-gray-600">
                      {latchAt ? formatKstHHMM(latchAt) : '—'}
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  // ───────────────────────────── ⑦ 보유 방어선 (full 전용) ─────────────────────────────
  function renderEtfHoldingsTable() {
    const entries = Object.entries(info.positions_detail ?? {})
    if (entries.length === 0) return <div className="text-xs text-gray-400">보유 종목 없음</div>
    const breakoutFailMinBars = params.breakout_fail_min_bars
    const maxAge = finiteOrNull(params.breakout_fail_price_max_age_secs)
    return (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-right py-1 px-2">매수가</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">실효 손절선</th>
            <th className="text-right py-1 px-2">손절까지</th>
            <th className="text-left py-1 pl-2">15:20 판정</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([ticker, pos]) => {
            const holding = (routeEntry?.holdings?.[ticker] ?? {}) as Dict
            const lines = (holding.lines ?? {}) as Dict
            const exitItem = exitLineMap.get(ticker)
            const effectiveStop = exitItem ? exitItem.stop_price : (typeof holding.effective_stop === 'number' ? holding.effective_stop : null)
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const distPct = cur !== null && cur > 0 && effectiveStop != null ? ((cur - effectiveStop) / cur) * 100 : null
            const tone: 'normal' | 'orange' | 'red' = distPct === null ? 'normal' : distPct < 1 ? 'red' : distPct < 3 ? 'orange' : 'normal'
            const breakoutFail = (holding.breakout_fail ?? {}) as Dict
            const tickAge = tickAgeSec(routeEntry?.ticks?.[ticker]?.last_tick_at, nowDate)
            let countdown: string
            if (tickAge === null || (maxAge !== null && tickAge > maxAge)) {
              countdown = '시세 낡음 — 15:20 판정 건너뜀 위험'
            } else if (breakoutFail.active) {
              const bLine = finiteOrNull(breakoutFail.line)
              countdown = (cur !== null && bLine !== null && cur < bLine)
                ? '15:20 정리(돌파 실패)'
                : '15:20 판정 대상'
            } else {
              countdown = `${breakoutFailMinBars ?? '—'}봉째부터 15:20 판정`
            }
            return (
              <tr key={ticker} data-testid={`etf_trend-monitor-holding-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                <td className="py-1 px-2 text-right">{won(pos.buy_price)}</td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right" data-testid={`etf_trend-monitor-stop-${ticker}`}>
                  {effectiveStop != null ? effectiveStop.toLocaleString() : '—'}
                </td>
                <td className="py-1 px-2 text-right" data-testid={`etf_trend-monitor-stopdist-${ticker}`} data-tone={tone}>
                  {distPct !== null ? `${distPct.toFixed(1)}%` : '—'}
                </td>
                <td className="py-1 pl-2" data-testid={`etf_trend-monitor-countdown-${ticker}`}>{countdown}</td>
                <td className="hidden">
                  {(['hard', 'breakeven', 'trail', 'channel'] as const).map((k) => {
                    const v = typeof lines[k] === 'number' ? (lines[k] as number) : null
                    const active = v != null && effectiveStop != null && Math.abs(v - effectiveStop) <= 1
                    return (
                      <span key={k} data-testid={`etf_trend-monitor-line-${ticker}-${k}`} data-active={active ? 'true' : 'false'}>
                        {v != null ? v.toLocaleString() : '—'}
                      </span>
                    )
                  })}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  function renderDonchianHoldingsTable() {
    const entries = Object.entries(info.positions_detail ?? {})
    if (entries.length === 0) return <div className="text-xs text-gray-400">보유 종목 없음</div>
    const channelExitPeriod = pnum(params.channel_exit_period)
    return (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-right py-1 px-2">매수가</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">손절선</th>
            <th className="text-left py-1 px-2">사다리</th>
            <th className="text-left py-1 pl-2">시간청산</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([ticker, pos]) => {
            const holding = (routeEntry?.holdings?.[ticker] ?? {}) as Dict
            const exitItem = exitLineMap.get(ticker)
            const effectiveStop = exitItem ? exitItem.stop_price : (typeof holding.stop === 'number' ? holding.stop : null)
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const armed = holding.armed === true
            const channelVal = finiteOrNull(holding.channel)
            const armPrice = finiteOrNull(holding.arm_price)
            const daysHeld = finiteOrNull(holding.days_held)
            const reachedR1 = holding.reached_1r === true
            const timeExitBars = finiteOrNull(holding.time_exit_bars)
            const maxHoldBars = finiteOrNull(holding.max_hold_bars)
            const target1r = finiteOrNull(holding.target_1r)
            const due = timeExitBars !== null && daysHeld !== null ? timeExitBars - 1 - daysHeld : null
            let countdownClause: string
            if (reachedR1) countdownClause = `+1R 넘음 — 시간청산 면제(최대 ${maxHoldBars ?? '—'}봉)`
            else if (due !== null && due > 0) countdownClause = `${due}영업일 뒤 15:20 시간청산 판정 — +1R(${target1r !== null ? target1r.toLocaleString() : '—'}원) 못 넘으면 정리`
            else countdownClause = '오늘 15:20 시간청산 대상(+1R 미도달)'
            const barsLabel = daysHeld !== null ? `보유 ${daysHeld + 1}봉째` : ''
            const fallbackNote = holding.days_fallback === true ? ' (보유일 근사)' : ''
            const ladderText = armed
              ? `무장 ✓ 손절선 본전 · ${channelExitPeriod}일 채널 ${channelVal !== null ? channelVal.toLocaleString() : '—'}`
              : `무장가 ${armPrice !== null ? armPrice.toLocaleString() : '—'}`
            return (
              <tr key={ticker} data-testid={`donchian_swing-monitor-holding-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                <td className="py-1 px-2 text-right">{won(pos.buy_price)}</td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">{effectiveStop != null ? effectiveStop.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-gray-600">{ladderText}</td>
                <td className="py-1 pl-2 text-gray-600" data-testid={`donchian_swing-monitor-countdown-${ticker}`}>
                  {barsLabel} · {countdownClause}{fallbackNote}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  function renderGenericHoldingsTable(sid: string) {
    const entries = Object.entries(info.positions_detail ?? {})
    if (entries.length === 0) return <div className="text-xs text-gray-400">보유 종목 없음</div>
    return (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-right py-1 px-2">매수가</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">손절선</th>
            <th className="text-right py-1 pl-2">손절까지</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([ticker, pos]) => {
            const exitItem = exitLineMap.get(ticker)
            const stop = exitItem ? exitItem.stop_price : null
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const distPct = cur !== null && cur > 0 && stop != null ? ((cur - stop) / cur) * 100 : null
            return (
              <tr key={ticker} data-testid={`${sid}-monitor-holding-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                <td className="py-1 px-2 text-right">{won(pos.buy_price)}</td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">{stop != null ? stop.toLocaleString() : '—'}</td>
                <td className="py-1 pl-2 text-right">{distPct !== null ? `${distPct.toFixed(1)}%` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  const prepare = prepareHeader(routeEntry?.prepare)
  const dailyEntries = (routeEntry?.extra?.daily_entries ?? null) as { count?: number; cap?: number } | null

  return (
    <div data-testid={`${strategyId}-monitor`} className="space-y-3">
      {/* ① 상태 */}
      <div data-testid={`${strategyId}-monitor-status`} className="rounded border border-gray-200 p-3 text-xs">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            data-testid={`${strategyId}-monitor-badge`}
            className={`whitespace-nowrap px-2 py-0.5 rounded font-semibold ${PRIMARY_CLS[status.primary]}`}
          >
            {status.label}
          </span>
          <span className="text-gray-500">
            비중 {weightPct}% · 예산 {won(info.total_investment)}원
            {status.primary === 'shadow' && weightPct === 0 && ' (섀도는 비중 0 이 정상)'}
          </span>
          {status.chips.map((c) => (
            <span
              key={c.kind}
              data-testid={`${strategyId}-monitor-chip-${c.kind}`}
              className={`text-[11px] px-1.5 py-0.5 rounded ${CHIP_CLS[c.tone]}`}
            >
              {c.label}
            </span>
          ))}
        </div>
      </div>

      {/* 기준일 머리말 */}
      <div data-testid={`${strategyId}-monitor-asof`} className={`text-xs ${prepare.fail ? 'text-rose-600' : 'text-gray-500'}`}>
        {prepare.text}
      </div>

      {/* ② 시간표 */}
      <div data-testid={`${strategyId}-monitor-timeline`} className="text-xs text-gray-600">
        {renderTimeline()}
      </div>

      {/* ③ 깔때기 */}
      <div data-testid={`${strategyId}-monitor-funnel`} className="rounded border border-gray-200 p-3">
        {renderFunnelPanel()}
      </div>

      {isFull && (
        <>
          {strategyId === 'donchian_swing' && dailyEntries && (
            <div data-testid="donchian_swing-monitor-daily-entries" className="text-xs text-gray-600">
              오늘 신규 진입 {dailyEntries.count ?? 0} / {dailyEntries.cap ?? '—'}
            </div>
          )}

          {/* ④ 후보 */}
          <div data-testid={`${strategyId}-monitor-candidates`} className="rounded border border-gray-200 p-3">
            <ScrollPane>
              {strategyId === 'etf_trend' && renderEtfCandidatesTable()}
              {strategyId === 'donchian_swing' && renderDonchianCandidatesTable()}
              {strategyId === 'vcp_breakout' && renderBreakoutCandidatesTable(false)}
              {strategyId === 'bull_flag_breakout' && renderBreakoutCandidatesTable(true)}
            </ScrollPane>
          </div>

          {/* ⑤ 사유 */}
          <div data-testid={`${strategyId}-monitor-skips`} className="text-xs text-gray-600">
            {renderSkipsPanel()}
          </div>
        </>
      )}

      {/* ⑥ 진입 기록 */}
      <div data-testid={`${strategyId}-monitor-entries`} className="rounded border border-gray-200 p-3">
        {renderEntriesPanel()}
        {modeDependentTicker && (
          <div className="mt-2 text-[11px] text-gray-500">
            보유 {modeDependentTicker.ticker} 손절선은 상한가 모드에 따라 달라 화면이 하나로 고르지 않습니다.
          </div>
        )}
      </div>

      {/* ⑦ 보유 방어선 */}
      {isFull && (
        <div data-testid={`${strategyId}-monitor-holdings`} className="rounded border border-gray-200 p-3">
          <ScrollPane>
            {strategyId === 'etf_trend' && renderEtfHoldingsTable()}
            {strategyId === 'donchian_swing' && renderDonchianHoldingsTable()}
            {strategyId === 'vcp_breakout' && renderGenericHoldingsTable('vcp_breakout')}
            {strategyId === 'bull_flag_breakout' && renderGenericHoldingsTable('bull_flag_breakout')}
          </ScrollPane>
          {strategyId === 'donchian_swing' && (
            <div data-testid="donchian_swing-monitor-exit-rules" className="mt-2 text-[11px] text-gray-500">
              손절 = 매수가 − 1R(1R = max(매수가×{pnum(params.kk_r_floor_pct)}%, {pnum(params.kk_r_atr_mult)}×진입 ATR)) ·
              고점이 매수가+{pnum(params.kk_breakeven_r)}R 에 닿으면 무장: 손절선이 본전으로 올라가고{' '}
              {pnum(params.channel_exit_period)}일 저가 채널 이탈도 청산 · 매수 뒤 {pnum(params.kk_time_exit_bars)}봉째 15:20 에{' '}
              +{pnum(params.kk_time_exit_min_r)}R 를 못 넘었으면 정리 · 최대 {pnum(params.kk_max_hold_bars)}봉 · 하루 신규 진입 최대{' '}
              {pnum(params.max_daily_entries)}종목
            </div>
          )}
        </div>
      )}
    </div>
  )
}
