/**
 * cycle414 — 전략별 진행상황 상세 패널(명세 `_workspace/red/cycle414/monitor_spec.md` §2·§4).
 * 보완 1차 — 1차 검수 verdict(H1~H3·M1~M13·L1·L2·L6·L7) 반영.
 *
 * 공통 7칸(①상태 ②시간표 ③깔때기 ④후보 ⑤사유 ⑥진입기록 ⑦보유방어선) 틀로 전략별 진행상황을
 * 그린다. 가벼운 패널(VB·momentum·LTV)은 ①②③⑥만, 고지로는 기존 `KojiroMonitor` 로 그린다.
 *
 * 화면 원칙(보완 1차) — 「모름」 을 「없음」·「차단」·「경보」 로 그리지 않는다(데이터 결손·라우트
 * 실패·엔진 정지·정산 뒤·휴일은 회색 「모름/장 마감」 계열로), 엔진 판정과 다른 판정을 화면이
 * 만들지 않는다(엔진 코드와 같은 조건만 「진입 가능」, 아니면 「참고」), 추정값은 「추정」으로.
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
import { formatKstHHMM, kstMinutesOfDay } from '../utils/kst'
import {
  strategyStatus, funnelBottleneck, finalFunnelStep, entryWindow, signalBaseline, marketUnitBlockLabel,
  SKIP_REASON_LABELS, type MonitorTone, type StrategyStatusResult,
} from '../utils/strategyMonitor'
import { computeZeroStreak } from '../utils/strategyFunnelTrend'
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

/** M6 — 손절(여유) 근접은 색 클래스로(data-tone 속성만으로는 안 보인다). KojiroMonitor 와 같은 팔레트. */
const STOP_TONE_CLS: Record<'normal' | 'orange' | 'red', string> = {
  normal: '',
  orange: 'text-amber-600 font-semibold',
  red: 'text-rose-600 font-semibold',
}

/** M11 — ETF 보유 구성 선(하드·본전·트레일·채널) 한글 라벨. */
const CONFIG_LINE_LABEL: Record<'hard' | 'breakeven' | 'trail' | 'channel', string> = {
  hard: '하드', breakeven: '본전', trail: '트레일', channel: '채널',
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
  // 보완 2차(N3 suites·screens / N7 trader) — VB·모멘텀·LTV 도 `ScanMonitor.tsx` 의 VB_STAGES·
  // MOMENTUM_STAGES·LTV_STAGES 와 같은 한글 라벨을 쓴다(scan_stats 영문 키 그대로 노출 금지).
  // 같은 파일에 두면 import 순환 위험이 있어 라벨 목록만 복제한다 — 키·순서는 두 파일이 같게 유지한다.
  volatility_breakout: [
    { key: 'universe_candidates', label: '시총+거래대금 컷 통과' },
    { key: 'universe_filtered', label: '유니버스 확정 (ETF/가격 제외)' },
    { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
    { key: 'k_value_computed', label: 'K값/Target 계산 완료' },
    { key: 'final_prepared', label: '최종 prepared' },
  ],
  long_tail_volatility: [
    { key: 'universe_candidates', label: '시총+거래대금 컷 통과' },
    { key: 'universe_filtered', label: '유니버스 확정 (ETF/가격 제외)' },
    { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
    { key: 'consecutive_limit_pass', label: '연속상한가 제외 통과' },
    { key: 'k_value_computed', label: 'K값/Target 계산' },
    { key: 'final_prepared', label: '최종 prepared' },
  ],
  momentum: [
    { key: 'universe_candidates', label: '등락률 순위 응답 (raw)' },
    { key: 'rate_pass', label: '등락률 ≥ 15% 통과' },
    { key: 'mcap_pass', label: '시총 ≥ 1,000억' },
    { key: 'trade_amount_pass', label: '거래대금 ≥ 200억' },
    { key: 'limit_up_excluded', label: '상한가 (+30%) 제외' },
    { key: 'final_prepared', label: '최종 후보' },
  ],
}

function pnum(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? String(n) : '—'
}

function finiteOrNull(v: unknown): number | null {
  // H1·M3 — 「모름」을 「0」으로 둔갑시키지 않는다. `Number(null) === 0` 이라 명시적
  // null(「값을 모른다」)이 숫자 0(「값이 0 이다」)으로 조용히 바뀌어 거짓 경보를 만든다.
  if (v === null || v === undefined) return null
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

// ─────────────────────────────── M11 시각 요소 — 작은 그림 컴포넌트 ───────────────────────────────

/**
 * §2.6 거리 막대 — 0% 눈금(돌파선) · 상한까지 연초록(살 수 있는 구간) · 상한 밖은 주황(추격 상한
 * 초과) · 현재가 표식. 보완 2차(N3) — ETF 는 엔진 조건이 시가 기준이고 현재가 하한이 없어
 * (`etf_trend.py`, 「현재가≥시가」만 본다) `belowLineOk` 로 초록 구간을 0% 아래까지 늘린다.
 * 보완 3차(N-b) — 돈키언도 같다: 엔진 `donchian_swing.check_buy_signal` 은 갭·추격상한·시장유닛·
 * 랏만 보고 「현재가≥돌파선」을 보지 않으므로 `belowLineOk` 를 쓴다. VCP·BFB 는 돌파선 아래를
 * 명시적으로 거르는 조건(`breakoutCandidateStatus` 의 「돌파선 아래」)이 있어 기본값(0% 위부터)을
 * 유지한다.
 */
function DistanceBar({
  testId, pct, cap, belowLineOk = false,
}: { testId: string; pct: number | null; cap: number | null; belowLineOk?: boolean }) {
  const W = 64
  const H = 12
  if (pct === null) {
    return <svg data-testid={testId} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="매수선 대비 모름" />
  }
  const lo = -10
  const hi = (cap ?? 10) + 3
  const span = hi - lo || 1
  const toX = (v: number) => ((Math.max(lo, Math.min(hi, v)) - lo) / span) * W
  const zeroX = toX(0)
  const capX = cap !== null ? toX(cap) : null
  const curX = toX(pct)
  const greenStartX = belowLineOk ? 0 : zeroX
  const label = `매수선 대비 ${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
  const outLow = pct < lo
  const outHigh = pct > hi
  return (
    <svg data-testid={testId} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <title>{label}</title>
      <rect x={0} y={4} width={W} height={4} fill="#e5e7eb" />
      {capX !== null && capX > greenStartX && <rect x={greenStartX} y={4} width={capX - greenStartX} height={4} fill="#bbf7d0" />}
      {capX !== null && capX < W && <rect x={capX} y={4} width={W - capX} height={4} fill="#fed7aa" />}
      {!belowLineOk && <line x1={zeroX} y1={0} x2={zeroX} y2={H} stroke="#9ca3af" strokeWidth={1} />}
      <circle cx={curX} cy={6} r={2.5} fill={pct >= 0 ? '#ef4444' : '#3b82f6'} />
      {outLow && <text x={1} y={10} fontSize={7} fill="#3b82f6">◀</text>}
      {outHigh && <text x={W - 7} y={10} fontSize={7} fill="#ef4444">▶</text>}
    </svg>
  )
}

interface LadderPoint { label: string; value: number }

/** §2.9 보유 사다리 — 눈금 위에 라벨+값을 글자(SVG text)로 둔다(스크린리더·텍스트 단언 양쪽 호환).
 * 보완 2차(N1) — 값이 같거나 가까운 점(예: 돈키언 무장가=매수가)은 한 그룹으로 합쳐 라벨·숫자가
 * 겹치지 않게 하고, 인접 그룹은 두 줄로 번갈아 배치해 숫자가 서로 겹치지 않게 한다. 전체 라벨·값은
 * `aria-label`·`<title>` 에도 그대로 담아 시각 배치와 무관하게 읽을 수 있다.
 * 보완 3차(N-A) — 합친 그룹도 라벨마다 값을 따로 적는다(첫 점 값만 대표해 다른 점의 값이 가려지는
 * 것을 막는다). 렌더된 글자는 항상 점(circle, 중심 y=H/2) 범위 밖에 둔다(겹침 금지 — 위 줄은
 * 중심에서 더 위로, 아래 줄은 더 아래로 떨어뜬다). */
const LADDER_COLORS: Record<string, string> = {
  손절: '#dc2626', 매수: '#6366f1', 현재: '#0ea5e9', 무장: '#059669', 목표: '#7c3aed',
}

function Ladder({ testId, points }: { testId: string; points: LadderPoint[] }) {
  const valid = points.filter((p) => Number.isFinite(p.value))
  if (valid.length === 0) return <svg data-testid={testId} width={1} height={1} />
  const values = valid.map((p) => p.value)
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const W = 220
  const MARGIN = 26
  const H = 44
  const CY = H / 2
  const toX = (v: number) => MARGIN + ((v - lo) / span) * (W - MARGIN * 2)

  const MIN_GAP = 30 // 라벨·값 글자(최대 7자리 숫자)가 겹치지 않을 최소 간격(px)
  type Group = { x: number; pts: LadderPoint[] }
  const groups: Group[] = []
  for (const p of valid.map((p) => ({ ...p, x: toX(p.value) })).sort((a, b) => a.x - b.x)) {
    const last = groups[groups.length - 1]
    if (last && p.x - last.x < MIN_GAP) last.pts.push(p)
    else groups.push({ x: p.x, pts: [p] })
  }

  const fmt = (v: number) => Math.round(v).toLocaleString()
  const fullLabel = valid.map((p) => `${p.label} ${fmt(p.value)}`).join(' · ')

  // N-A — 위 줄 y=CY-8(점 위 가장자리 CY-3 보다 5px 더 위) · 아래 줄 y=CY+14(점 아래 가장자리
  // CY+3 보다 9px 더 아래, 숫자 아래쪽 여유를 더 둔다) — 둘 다 점 범위와 겹치지 않는다.
  const TEXT_ABOVE_Y = CY - 8
  const TEXT_BELOW_Y = CY + 14

  return (
    <svg data-testid={testId} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={fullLabel}>
      <title>{fullLabel}</title>
      <line x1={MARGIN} y1={CY} x2={W - MARGIN} y2={CY} stroke="#d1d5db" strokeWidth={2} />
      {groups.map((g, i) => {
        const above = i % 2 === 0 // 인접 그룹끼리 겹치지 않게 두 줄로 번갈아
        const textY = above ? TEXT_ABOVE_Y : TEXT_BELOW_Y
        const tickEndY = above ? textY + 3 : textY - 9
        // N-A — 합친 그룹은 "라벨 값"을 점별로 적어 "/" 로 잇는다(모두가 같은 값을 대표하지 않는다).
        const text = g.pts.map((p) => `${p.label} ${fmt(p.value)}`).join(' / ')
        const color = LADDER_COLORS[g.pts[0].label] ?? '#6366f1'
        return (
          <g key={`${g.x}-${i}`}>
            <line x1={g.x} y1={CY} x2={g.x} y2={tickEndY} stroke="#d1d5db" strokeWidth={1} />
            <circle cx={g.x} cy={CY} r={3} fill={color} />
            <text x={g.x} y={textY} fontSize={7} textAnchor="middle" fill="#374151">{text}</text>
          </g>
        )
      })}
    </svg>
  )
}

/** §4.3 VCP·BFB 거래량 게이지 — 0~150% 막대 + 100% 선. */
function VolumeGauge({ testId, pct, text }: { testId: string; pct: number | null; text: string }) {
  const capped = pct !== null ? Math.max(0, Math.min(150, pct)) : 0
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1 text-gray-700">
      <svg width={40} height={10} viewBox="0 0 40 10" role="img" aria-label={text}>
        <rect x={0} y={3} width={40} height={4} fill="#e5e7eb" />
        <rect x={0} y={3} width={(capped / 150) * 40} height={4} fill={pct !== null && pct >= 100 ? '#10b981' : '#f59e0b'} />
        <line x1={(100 / 150) * 40} y1={0} x2={(100 / 150) * 40} y2={10} stroke="#9ca3af" />
      </svg>
      <span>{text}</span>
    </span>
  )
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
  /** H3 — `/api/trading/status` 의 `running`. 모니터 라우트가 실패해도(=null) 엔진 정지를 안다. */
  running?: boolean | null
}

export default function StrategyMonitor({
  strategyId, strategies, monitor, exitLines, tickerPrices, tickerNames, subscribedTickers, funnelTrend, now, running,
}: Props) {
  const info = strategies[strategyId]
  const nowDate = now ?? new Date()
  const routeEntry = monitor?.strategies?.[strategyId] ?? null
  const marketUnit = routeEntry?.market_unit ?? null

  // L1 — 훅은 전부 조기 return(고지로 분기) 보다 앞에 둔다(rules-of-hooks).
  const status = useMemo(() => (info ? strategyStatus(strategyId, info, marketUnit) : null), [strategyId, info, marketUnit])
  const subscribedSet = useMemo(() => new Set(subscribedTickers ?? []), [subscribedTickers])
  const exitLineMap = useMemo(() => {
    const m = new Map<string, ExitLineItem>()
    for (const item of exitLines ?? []) if (item.strategy_id === strategyId) m.set(item.ticker, item)
    return m
  }, [exitLines, strategyId])

  // 고지로는 기존 KojiroMonitor(id 보존)로 그린다 — §4.5.
  if (strategyId === 'kojiro') {
    return (
      <KojiroMonitor
        strategies={strategies}
        tickerPrices={tickerPrices}
        exitLines={exitLines ?? undefined}
        monitor={monitor ?? undefined}
        running={running}
      />
    )
  }

  // H3 — 엔진 정지(정산 뒤·부팅 전·휴일). `running` prop(=/trading/status, 모니터 실패에도 안다)
  // 또는 `monitor.running` 둘 중 하나라도 false 면 멈춘 것으로 본다.
  const engineStopped = running === false || monitor?.running === false

  const params = (info?.params ?? {}) as Dict
  const prices = tickerPrices ?? {}
  const names = tickerNames ?? {}

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
  // M7 — 최종 단계 = 전략별 최종 step_no(step_no===99 우선, 없으면 최대) — donchian·VCP·BFB·kojiro 는 9.
  const finalStep = finalFunnelStep(steps)
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
            <div data-testid={`${strategyId}-monitor-trend`} className="mt-2">
              <div className="text-[10px] text-gray-500 mb-0.5">14일 최종 후보 추이</div>
              <div className="flex items-end gap-0.5 h-8">
                {funnelTrend.map((d) => (
                  <div
                    key={d.date}
                    title={`${mmdd(d.date)}: ${d.count}건`}
                    className={`flex-1 rounded-t ${d.count === 0 ? 'bg-rose-300' : 'bg-blue-300'}`}
                    style={{ height: `${Math.max(4, Math.round((d.count / trendMax) * 100))}%` }}
                  />
                ))}
              </div>
              {/* N-B — 막대와 같은 `flex-1` 폭 분배를 써서 날짜·값 줄이 그 막대 바로 아래에 선다
                  (`flex-wrap` 는 좌측에 몰려 인덱스가 막대와 어긋난다). */}
              <div className="flex gap-0.5 text-[9px] text-gray-400 mt-0.5">
                {funnelTrend.map((d) => (
                  <span key={d.date} className="flex-1 text-center truncate">{mmdd(d.date)}:{d.count}</span>
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
    // M9/N3/N4 — 라우트 funnel 이 없을 때의 폴백. scan_stats 가 있으면 한글 라벨로 그린다
    // (「아직 스캔 전」을 「아침 준비 완료」 머리말과 모순시키지 않는다 · 결측 단계는 0 이 아니라 「모름」).
    const fallback = FALLBACK_STAGES[strategyId]
    if (fallback) {
      const ss = (info.scan_stats ?? {}) as Dict
      return (
        <div className="space-y-1 text-xs text-gray-600">
          {fallback.map((stg, i) => (
            <div key={stg.key} data-testid={`${strategyId}-monitor-funnel-row-${i + 1}`}>
              {i + 1}. {stg.label} — {finiteOrNull(ss[stg.key]) ?? '모름'}
            </div>
          ))}
        </div>
      )
    }
    if (prepareOk) return <div className="text-xs text-gray-400">단계 기록 없음</div>
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
          {/* N6(screens) — 엔진 정지 중에는 정산으로 비워진 0 이 「오늘 신호가 없었다」로 읽히지 않게 「모름」. */}
          {engineStopped ? '매수 신호 모름 — 엔진 정지' : `매수 신호 ${buySignals.length}`}
          {!engineStopped && isShadow && buySignals.length === 0 && (
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

  /** M5 — 라우트 실패는 「모름」(시세 신선도 경보 0) · 자격·시각을 시세 신선도보다 먼저 본다. */
  function etfCandidateStatus(ticker: string, includePause: boolean): string {
    if (engineStopped) return '장 마감/엔진 정지'
    if (!subscribedSet.has(ticker)) return '시세 없음'
    if ((info.position_tickers ?? []).includes(ticker)) return '보유 중'
    if ((info.pending_buy_tickers ?? []).includes(ticker)) return '주문 중'
    // M2 — 「오늘 시도함」은 갭 사유일 때만(엔진은 갭 때만 _bought_today 에 넣는다). 그 밖 사유는
    // 흘려보내 평소 체인을 계속 타게 둔다(⑤ 사유 칸이 그 사유 수를 이미 보여 준다).
    const byTicker = (routeEntry?.skips?.by_ticker?.[ticker] ?? []) as string[]
    if (byTicker.includes('gap_up') || byTicker.includes('gap_over_line')) return '오늘 갭 스킵'
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
    if (!routeEntry) return '모름'
    const cand = (routeEntry.candidates?.[ticker] ?? {}) as Dict
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
    if (engineStopped) return '장 마감/엔진 정지'
    if (!subscribedSet.has(ticker)) return '시세 없음'
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
    if (!routeEntry) return '모름'
    // M1 — 터틀 4전략은 enforce + 오늘 스냅샷 결손이면 엔진 m=1(차단 아님). marketUnitBlockLabel
    // 이 이미 그 식을 담는다(utils/strategyMonitor.ts) — 여기서 따로 판정하지 않는다.
    const muBlock = marketUnitBlockLabel('donchian_swing', marketUnit)
    if (muBlock) return muBlock
    const cand = (routeEntry.candidates?.[ticker] ?? {}) as Dict
    const designLot = finiteOrNull(cand.design_lot)
    if (designLot !== null && designLot <= 0) return '설계 랏 0'
    const daily = (routeEntry.extra?.daily_entries ?? {}) as Dict
    const count = finiteOrNull(daily.count)
    const cap = finiteOrNull(daily.cap)
    if (count !== null && cap !== null && count >= cap) return '하루 신규 상한'
    // N2(trader) — 추격 상한 판정은 당일 고가(장중 최고가)·오늘 매도 여부가 필요하지만 화면은
    // 현재가·시가만 가진다(엔진은 `stck_hgpr`/`high_price` 도 본다 — `donchian_swing.py`). 과소
    // 추정이면 엔진이 거를 종목을 화면이 「진입 가능」으로 단정할 수 있어, 추격 상한 설정이
    // 있을 때는(=그 판정이 실제로 매수를 가를 때) 「참고」로 낮춘다.
    // 보완 3차(N-b) — 엔진 `check_buy_signal` 은 갭·추격상한·시장유닛·랏만 보고 「현재가≥돌파선」을
    // 보지 않는다(여기까지 온 후보가 돌파선 위인지는 화면이 확인한 적이 없다) — 「돌파선 위」를
    // 주장하지 않는다.
    if (extCap !== null) return '참고: 진입 조건 충족(당일 고가 미반영)'
    return '진입 가능'
  }

  /** H2 — 「진입 가능」 은 엔진 조건(아래→위 교차 틱 또는 오늘 무장한 래치)일 때만. 래치 없이
   *  돌파선 위 + 거래량 충족이면 「참고: 돌파선 위」(화면이 「샀을 것」을 단정하지 않는다). */
  function breakoutCandidateStatus(ticker: string, isBfb: boolean): string {
    const sid = isBfb ? 'bull_flag_breakout' : 'vcp_breakout'
    if (engineStopped) return '장 마감/엔진 정지'
    if (!subscribedSet.has(ticker)) return '시세 없음'
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
    if (!routeEntry) return '모름'
    const cand = (routeEntry.candidates?.[ticker] ?? {}) as Dict
    const breakoutLine = finiteOrNull(isBfb ? target.flag_high : target.base_high)
    const cur = finiteOrNull(prices[ticker]?.current_price)
    if (breakoutLine !== null && cur !== null && cur < breakoutLine) return '돌파선 아래'
    const tickEntry = routeEntry.ticks?.[ticker]
    const acmlVol = tickEntry?.acml_vol
    const volThreshold = finiteOrNull(target.volume_threshold)
    const latchAt = typeof cand.latch_armed_at === 'string' ? cand.latch_armed_at : null
    // N10(trader) — 임계가 설정돼 있을 때만 거래량을 본다(엔진은 임계 0 또는 미설정이면 관측 없이
    // 통과시킨다 — 게이트가 꺼진 것과 같다). 임계가 있는데 관측이 없을 때만 「거래량 미관측」.
    if (volThreshold !== null && volThreshold > 0) {
      if (acmlVol === null || acmlVol === undefined) return '거래량 미관측'
      if (acmlVol < volThreshold) {
        if (latchAt) return '래치: 거래량 대기 중'
        return `거래량 부족 ${Math.round((acmlVol / volThreshold) * 100)}%`
      }
    }
    const extCap = finiteOrNull(params.max_breakout_extension_pct)
    if (breakoutLine !== null && breakoutLine > 0 && extCap !== null && cur !== null) {
      const extPct = ((cur - breakoutLine) / breakoutLine) * 100
      if (extPct > extCap) return '추격 상한 초과'
    }
    const muBlock = marketUnitBlockLabel(sid, marketUnit)
    if (muBlock) return muBlock
    // H2 — 오늘 무장한 래치가 있을 때만 「진입 가능」. 래치 없이 돌파선 위인 것은 엔진이 지난
    // 틱에서 이미 거른 상태일 수 있어(지금 막 교차한 증거가 없다) 「참고」로 낮춘다.
    if (!latchAt) return '참고: 돌파선 위'
    return '진입 가능'
  }

  function renderEtfCandidatesTable() {
    const tickers = Object.keys(targets)
    if (tickers.length === 0) return <div className="text-xs text-gray-400">후보 없음</div>
    const capPct = finiteOrNull(params.gap_over_line_pct)
    return (
      <table className="w-full min-w-[720px] text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-left py-1 pr-2">상태</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">돌파선</th>
            <th className="text-right py-1 px-2">거리</th>
            <th className="text-right py-1 px-2">예상 수량</th>
            <th className="text-left py-1 pl-2">묶음</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => {
            const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
            const actual = etfCandidateStatus(ticker, true)
            const hint = actual === '멈춤' ? etfCandidateStatus(ticker, false) : null
            const qty = engineStopped ? null : finiteOrNull(cand.design_qty)
            const qtyText = engineStopped
              ? '모름'
              : qty === null ? '—' : qty <= 0 ? '1주도 안 됨 — 사지 않음' : `최대 ${qty}주(추정)`
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const line = finiteOrNull(cand.line)
            const pct = cur !== null && line !== null && line > 0 ? ((cur - line) / line) * 100 : null
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
                  <div className="flex items-center justify-end gap-1">
                    <span className={pct === null ? 'text-gray-400' : pct >= 0 ? 'text-red-500' : 'text-blue-500'}>
                      {pct !== null ? `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
                    </span>
                    <DistanceBar testId={`etf_trend-monitor-distbar-${ticker}`} pct={pct} cap={capPct} belowLineOk />
                  </div>
                </td>
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
    if (tickers.length === 0) return <div className="text-xs text-gray-400">후보 없음</div>
    const capPct = finiteOrNull(params.max_breakout_extension_pct)
    return (
      <table className="w-full min-w-[760px] text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-left py-1 pr-2">상태</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">20일 신고가</th>
            <th className="text-right py-1 px-2">거리</th>
            <th className="text-right py-1 px-2">1R / R%</th>
            <th className="text-right py-1 pl-2">설계 수량</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => {
            const cand = (routeEntry?.candidates?.[ticker] ?? {}) as Dict
            const statusText = donchianCandidateStatus(ticker, true)
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const dh = finiteOrNull(targets[ticker]?.donchian_high)
            const pct = cur !== null && dh !== null && dh > 0 ? ((cur - dh) / dh) * 100 : null
            const rWon = finiteOrNull(cand.r_won)
            const rPct = finiteOrNull(cand.r_pct)
            const designLot = engineStopped ? null : finiteOrNull(cand.design_lot)
            return (
              <tr key={ticker} data-testid={`donchian_swing-monitor-candidate-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{nameOf(ticker)}({ticker})</td>
                <td className="py-1 pr-2">
                  <span data-testid={`donchian_swing-monitor-status-${ticker}`} className="text-gray-700">{statusText}</span>
                </td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right text-indigo-600">{dh !== null ? dh.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <span className={pct === null ? 'text-gray-400' : pct >= 0 ? 'text-red-500' : 'text-blue-500'}>
                      {pct !== null ? `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
                    </span>
                    <DistanceBar testId={`donchian_swing-monitor-distbar-${ticker}`} pct={pct} cap={capPct} belowLineOk />
                  </div>
                </td>
                <td className="py-1 px-2 text-right">
                  {rWon !== null ? rWon.toLocaleString() : '—'} {rPct !== null ? `(${rPct.toFixed(1)}%)` : ''}
                </td>
                <td className="py-1 pl-2 text-right">
                  {engineStopped
                    ? <span className="text-gray-500">모름</span>
                    : designLot !== null && designLot <= 0
                      ? <span className="text-rose-600 font-medium">사지 않음</span>
                      : (designLot !== null ? `${designLot}주(추정)` : '—')}
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
    if (tickers.length === 0) return <div className="text-xs text-gray-400">후보 없음</div>
    const capPct = finiteOrNull(params.max_breakout_extension_pct)
    return (
      <table className="w-full min-w-[760px] text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-left py-1 pr-2">상태</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">돌파선</th>
            <th className="text-right py-1 px-2">거리</th>
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
            const pct = cur !== null && breakoutLine !== null && breakoutLine > 0 ? ((cur - breakoutLine) / breakoutLine) * 100 : null
            const tickEntry = routeEntry?.ticks?.[ticker]
            const acmlVol = tickEntry?.acml_vol
            const volThreshold = finiteOrNull(target.volume_threshold)
            // N10 — 임계가 없거나 0 이면 게이트가 꺼진 것(엔진은 관측 없이 통과) — 「거래량
            // 미관측」 경보를 내지 않는다.
            const volText = !routeEntry
              ? '모름'
              : volThreshold === null || volThreshold <= 0
                ? '게이트 비활성'
                : (acmlVol === null || acmlVol === undefined)
                  ? '거래량 미관측'
                  : `${Math.round((acmlVol / volThreshold) * 100)}%`
            const volPctNum = typeof acmlVol === 'number' && volThreshold !== null && volThreshold > 0
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
                  <div className="flex items-center justify-end gap-1">
                    <span className={pct === null ? 'text-gray-400' : pct >= 0 ? 'text-red-500' : 'text-blue-500'}>
                      {pct !== null ? `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
                    </span>
                    <DistanceBar testId={`${sid}-monitor-distbar-${ticker}`} pct={pct} cap={capPct} />
                  </div>
                </td>
                <td className="py-1 px-2 text-right">
                  <VolumeGauge testId={`${sid}-monitor-volgauge-${ticker}`} pct={volPctNum} text={volText} />
                </td>
                {isBfb && (
                  <td className="py-1 px-2 text-right text-gray-600">
                    {finiteOrNull(target.measured_target) !== null ? (finiteOrNull(target.measured_target) as number).toLocaleString() : '—'}
                  </td>
                )}
                <td className="py-1 pl-2 text-right">
                  <span data-testid={`${sid}-monitor-latch-${ticker}`} className="text-gray-600">
                    {latchAt ? formatKstHHMM(latchAt) : '—'}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  // ───────────────────────────── ⑦ 보유 방어선 (full 전용) ─────────────────────────────

  const NEAR_1520_START_MIN = 15 * 60 // 15:00 — 15:20 판정이 가까울 때만 틱 신선도를 본다(M5).

  function renderEtfHoldingsTable() {
    const entries = Object.entries(info.positions_detail ?? {})
    if (entries.length === 0) {
      return <div className="text-xs text-gray-400">{engineStopped ? '장 마감/엔진 정지 — 보유 정보 모름' : '보유 종목 없음'}</div>
    }
    const breakoutFailMinBars = params.breakout_fail_min_bars
    const maxAge = finiteOrNull(params.breakout_fail_price_max_age_secs)
    return (
      <table className="w-full min-w-[920px] text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-right py-1 px-2">매수가</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">실효 손절선</th>
            <th className="text-right py-1 px-2">손절까지</th>
            <th className="text-left py-1 px-2">구성 선</th>
            <th className="text-left py-1 px-2">15:20 판정</th>
            <th className="text-left py-1 pl-2">사다리</th>
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
            const hasMonitorData = !!monitor && Object.keys(holding).length > 0
            const breakoutFail = (holding.breakout_fail ?? {}) as Dict
            const tickAge = tickAgeSec(routeEntry?.ticks?.[ticker]?.last_tick_at, nowDate)
            let countdown: string
            if (engineStopped) {
              countdown = '장 마감/엔진 정지 — 모름'
            } else if (!hasMonitorData) {
              countdown = '모름 — 모니터 데이터 없음'
            } else {
              // M3 — 돌파선이 없으면 판정 대상이 아니다(엔진 missing_line).
              const bLine = finiteOrNull(breakoutFail.line)
              if (bLine === null) {
                countdown = '돌파선 모름'
              } else if (!breakoutFail.active) {
                countdown = `${breakoutFailMinBars ?? '—'}봉째부터 15:20 판정`
              } else {
                // M5 — 시세 신선도는 15:20 이 가까울 때만 본다(자격·시각이 먼저).
                const nearClose = kstMinutesOfDay(nowDate) >= NEAR_1520_START_MIN
                const stale = tickAge === null || (maxAge !== null && tickAge > maxAge)
                if (nearClose && stale) {
                  countdown = '시세 낡음 — 15:20 판정 건너뜀 위험'
                } else {
                  countdown = (cur !== null && cur < bLine) ? '15:20 정리(돌파 실패)' : '15:20 판정 대상'
                }
              }
            }
            return (
              <tr key={ticker} data-testid={`etf_trend-monitor-holding-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                <td className="py-1 px-2 text-right">{won(pos.buy_price)}</td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right" data-testid={`etf_trend-monitor-stop-${ticker}`}>
                  {effectiveStop != null ? effectiveStop.toLocaleString() : '—'}
                </td>
                <td
                  className={`py-1 px-2 text-right ${STOP_TONE_CLS[tone]}`}
                  data-testid={`etf_trend-monitor-stopdist-${ticker}`}
                  data-tone={tone}
                >
                  {distPct !== null ? `${distPct.toFixed(1)}%` : '—'}
                </td>
                <td className="py-1 px-2 text-[10px] text-gray-500 whitespace-nowrap">
                  {(['hard', 'breakeven', 'trail', 'channel'] as const).map((k) => {
                    const v = typeof lines[k] === 'number' ? (lines[k] as number) : null
                    const active = v != null && effectiveStop != null && Math.abs(v - effectiveStop) <= 1
                    return (
                      <span
                        key={k}
                        data-testid={`etf_trend-monitor-line-${ticker}-${k}`}
                        data-active={active ? 'true' : 'false'}
                        className={active ? 'font-semibold text-gray-700 mr-1.5' : 'mr-1.5'}
                      >
                        {CONFIG_LINE_LABEL[k]} {v != null ? v.toLocaleString() : '—'}
                      </span>
                    )
                  })}
                </td>
                <td className="py-1 px-2" data-testid={`etf_trend-monitor-countdown-${ticker}`}>{countdown}</td>
                <td className="py-1 pl-2">
                  <Ladder
                    testId={`etf_trend-monitor-ladder-${ticker}`}
                    points={[
                      { label: '손절', value: effectiveStop ?? NaN },
                      { label: '매수', value: finiteOrNull(pos.buy_price) ?? NaN },
                      { label: '현재', value: cur ?? NaN },
                    ]}
                  />
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
    if (entries.length === 0) {
      return <div className="text-xs text-gray-400">{engineStopped ? '장 마감/엔진 정지 — 보유 정보 모름' : '보유 종목 없음'}</div>
    }
    const channelExitPeriod = pnum(params.channel_exit_period)
    return (
      <table className="w-full min-w-[920px] text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-right py-1 px-2">매수가</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">손절선</th>
            <th className="text-right py-1 px-2">손절까지</th>
            <th className="text-left py-1 px-2">사다리</th>
            <th className="text-left py-1 pl-2">시간청산</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([ticker, pos]) => {
            const holding = (routeEntry?.holdings?.[ticker] ?? {}) as Dict
            const hasMonitorData = !!monitor && Object.keys(holding).length > 0
            const exitItem = exitLineMap.get(ticker)
            const effectiveStop = exitItem ? exitItem.stop_price : (typeof holding.stop === 'number' ? holding.stop : null)
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const distPct = cur !== null && cur > 0 && effectiveStop != null ? ((cur - effectiveStop) / cur) * 100 : null
            const stopTone: 'normal' | 'orange' | 'red' = distPct === null ? 'normal' : distPct < 1 ? 'red' : distPct < 3 ? 'orange' : 'normal'
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
            if (engineStopped) countdownClause = '장 마감/엔진 정지 — 판정 모름'
            else if (!hasMonitorData) countdownClause = '모름(시간청산 판정 불가)'
            else if (reachedR1) countdownClause = `+1R 넘음 — 시간청산 면제(최대 ${maxHoldBars ?? '—'}봉)`
            // H1 — due(=time_exit_bars·days_held) 를 모르면 「모름」 — 거짓 「오늘 15:20」 경보 0.
            else if (timeExitBars === null || daysHeld === null) countdownClause = '모름(시간청산 판정 불가)'
            else if (due !== null && due > 0) countdownClause = `${due}영업일 뒤 15:20 시간청산 판정 — +1R(${target1r !== null ? target1r.toLocaleString() : '—'}원) 못 넘으면 정리`
            else countdownClause = '오늘 15:20 시간청산 대상(+1R 미도달)'
            const barsLabel = (!engineStopped && hasMonitorData && daysHeld !== null) ? `보유 ${daysHeld + 1}봉째` : ''
            const fallbackNote = holding.days_fallback === true ? ' (보유일 근사)' : ''
            return (
              <tr key={ticker} data-testid={`donchian_swing-monitor-holding-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                <td className="py-1 px-2 text-right">{won(pos.buy_price)}</td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right">{effectiveStop != null ? effectiveStop.toLocaleString() : '—'}</td>
                <td
                  className={`py-1 px-2 text-right ${STOP_TONE_CLS[stopTone]}`}
                  data-testid={`donchian_swing-monitor-stopdist-${ticker}`}
                  data-tone={stopTone}
                >
                  {distPct !== null ? `${distPct.toFixed(1)}%` : '—'}
                </td>
                <td className="py-1 px-2">
                  <Ladder
                    testId={`donchian_swing-monitor-ladder-${ticker}`}
                    points={[
                      { label: '손절', value: effectiveStop ?? NaN },
                      { label: '매수', value: finiteOrNull(pos.buy_price) ?? NaN },
                      { label: '현재', value: cur ?? NaN },
                      { label: '무장', value: armed ? (finiteOrNull(pos.buy_price) ?? NaN) : (armPrice ?? NaN) },
                    ]}
                  />
                  {armed && (
                    <div className="text-[10px] text-emerald-600 mt-0.5">
                      무장 ✓ 손절선 본전 · {channelExitPeriod}일 채널 {channelVal !== null ? channelVal.toLocaleString() : '—'}
                    </div>
                  )}
                </td>
                <td className="py-1 pl-2 text-gray-600" data-testid={`donchian_swing-monitor-countdown-${ticker}`}>
                  {barsLabel} {barsLabel && '·'} {countdownClause}{fallbackNote}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  function renderBreakoutHoldingsTable(isBfb: boolean) {
    const sid = isBfb ? 'bull_flag_breakout' : 'vcp_breakout'
    const entries = Object.entries(info.positions_detail ?? {})
    if (entries.length === 0) {
      return <div className="text-xs text-gray-400">{engineStopped ? '장 마감/엔진 정지 — 보유 정보 모름' : '보유 종목 없음'}</div>
    }
    return (
      <table className="w-full min-w-[720px] text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">종목</th>
            <th className="text-right py-1 px-2">매수가</th>
            <th className="text-right py-1 px-2">현재가</th>
            <th className="text-right py-1 px-2">손절선</th>
            <th className="text-right py-1 px-2">손절까지</th>
            <th className="text-left py-1 pl-2">사다리</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([ticker, pos]) => {
            const exitItem = exitLineMap.get(ticker)
            const stop = exitItem ? exitItem.stop_price : null
            const target = isBfb && exitItem ? exitItem.target_price : null
            const cur = finiteOrNull(prices[ticker]?.current_price)
            const distPct = cur !== null && cur > 0 && stop != null ? ((cur - stop) / cur) * 100 : null
            const tone: 'normal' | 'orange' | 'red' = distPct === null ? 'normal' : distPct < 1 ? 'red' : distPct < 3 ? 'orange' : 'normal'
            return (
              <tr key={ticker} data-testid={`${sid}-monitor-holding-${ticker}`} className="border-b border-gray-100">
                <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                <td className="py-1 px-2 text-right">{won(pos.buy_price)}</td>
                <td className="py-1 px-2 text-right">{cur !== null ? cur.toLocaleString() : '—'}</td>
                <td className="py-1 px-2 text-right" data-testid={`${sid}-monitor-stop-${ticker}`}>{stop != null ? stop.toLocaleString() : '—'}</td>
                <td
                  className={`py-1 px-2 text-right ${STOP_TONE_CLS[tone]}`}
                  data-testid={`${sid}-monitor-stopdist-${ticker}`}
                  data-tone={tone}
                >
                  {distPct !== null ? `${distPct.toFixed(1)}%` : '—'}
                </td>
                <td className="py-1 pl-2">
                  <Ladder
                    testId={`${sid}-monitor-ladder-${ticker}`}
                    points={[
                      { label: '손절', value: stop ?? NaN },
                      { label: '매수', value: finiteOrNull(pos.buy_price) ?? NaN },
                      { label: '현재', value: cur ?? NaN },
                      ...(isBfb && target !== null ? [{ label: '목표', value: target as number }] : []),
                    ]}
                  />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  const prepare = prepareHeader(routeEntry?.prepare)
  const prepareOk = routeEntry?.prepare?.ok === true
  const dailyEntries = (routeEntry?.extra?.daily_entries ?? null) as { count?: number; cap?: number } | null

  return (
    <div data-testid={`${strategyId}-monitor`} className="space-y-3">
      {/* ① 상태 */}
      <div data-testid={`${strategyId}-monitor-status`} className="rounded border border-gray-200 p-3 text-xs">
        <h4 className="text-xs font-semibold text-gray-600 mb-1.5">상태</h4>
        <div className="flex items-center gap-2 flex-wrap">
          <span
            data-testid={`${strategyId}-monitor-badge`}
            className={`whitespace-nowrap px-2 py-0.5 rounded font-semibold ${PRIMARY_CLS[status.primary]}`}
          >
            {status.label}
          </span>
          <span className="text-gray-500">
            비중 {weightPct}% · {engineStopped ? '예산 모름' : `예산 ${won(info.total_investment)}원`}
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
        {engineStopped && (
          <div data-testid={`${strategyId}-monitor-engine-stopped`} className="mt-1.5 inline-block px-2 py-0.5 rounded bg-gray-100 text-gray-600 text-[11px]">
            장 마감/엔진 정지 — 값이 최신이 아닐 수 있습니다(정산 뒤 · 부팅 전 · 휴일)
          </div>
        )}
      </div>

      {/* 기준일 머리말 */}
      <div data-testid={`${strategyId}-monitor-asof`} className={`text-xs ${prepare.fail ? 'text-rose-600' : 'text-gray-500'}`}>
        {prepare.text}
      </div>

      {/* ② 시간표 */}
      <div data-testid={`${strategyId}-monitor-timeline`} className="text-xs text-gray-600">
        <h4 className="text-xs font-semibold text-gray-600 mb-1">오늘의 시간표</h4>
        {renderTimeline()}
      </div>

      {/* ③ 깔때기 */}
      <div data-testid={`${strategyId}-monitor-funnel`} className="rounded border border-gray-200 p-3">
        <h4 className="text-xs font-semibold text-gray-600 mb-1.5">후보 깔때기</h4>
        {renderFunnelPanel()}
      </div>

      {isFull && (
        <>
          {strategyId === 'donchian_swing' && dailyEntries && (
            <div data-testid="donchian_swing-monitor-daily-entries" className="text-xs text-gray-600">
              {engineStopped
                ? '오늘 신규 진입 모름 — 엔진 정지'
                : <>오늘 신규 진입 {dailyEntries.count ?? '모름'} / {dailyEntries.cap ?? '—'}</>}
            </div>
          )}

          {/* ④ 후보 */}
          <div data-testid={`${strategyId}-monitor-candidates`} className="rounded border border-gray-200 p-3">
            <h4 className="text-xs font-semibold text-gray-600 mb-1.5">후보 종목</h4>
            <ScrollPane>
              {strategyId === 'etf_trend' && renderEtfCandidatesTable()}
              {strategyId === 'donchian_swing' && renderDonchianCandidatesTable()}
              {strategyId === 'vcp_breakout' && renderBreakoutCandidatesTable(false)}
              {strategyId === 'bull_flag_breakout' && renderBreakoutCandidatesTable(true)}
            </ScrollPane>
          </div>

          {/* ⑤ 사유 */}
          <div data-testid={`${strategyId}-monitor-skips`} className="text-xs text-gray-600">
            <h4 className="text-xs font-semibold text-gray-600 mb-1">오늘 거르기 사유</h4>
            {renderSkipsPanel()}
          </div>
        </>
      )}

      {/* ⑥ 진입 기록 */}
      <div data-testid={`${strategyId}-monitor-entries`} className="rounded border border-gray-200 p-3">
        <h4 className="text-xs font-semibold text-gray-600 mb-1.5">진입 기록</h4>
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
          <h4 className="text-xs font-semibold text-gray-600 mb-1.5">보유 방어선</h4>
          <ScrollPane>
            {strategyId === 'etf_trend' && renderEtfHoldingsTable()}
            {strategyId === 'donchian_swing' && renderDonchianHoldingsTable()}
            {strategyId === 'vcp_breakout' && renderBreakoutHoldingsTable(false)}
            {strategyId === 'bull_flag_breakout' && renderBreakoutHoldingsTable(true)}
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
