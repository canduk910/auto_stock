/**
 * cycle414 — 대시보드 「전체」 탭 전략 요약표(명세 `_workspace/red/cycle414/monitor_spec.md` §5).
 * 보완 1차 — 1차 검수 verdict(H3·M1·M3·M6·M7·M11·M12·L5) 반영.
 *
 * 행 = 전략 하나(주 배지 실매매→멈춤→섀도→꺼짐 순서, 같은 묶음은 비중 내림차순). 행을 누르면
 * 그 전략 탭으로 간다(`onSelect`). 「왜 안 사나」 한 줄은 §5.2 12단계 우선순위(처음 맞는 하나) —
 * 보완 1차에서 「엔진 정지」를 꺼짐 다음 우선순위로 더했다(H3).
 */
import type { ExitLineItem, StrategyInfo, StrategyMonitorResponse, TickerPrice } from '../types/trading'
import {
  strategyStatus, funnelBottleneck, finalFunnelStep, entryWindow, marketUnitBlockLabel, topSkipReason,
  type StrategyStatusResult,
} from '../utils/strategyMonitor'
import { strategyLabel } from '../utils/strategyMeta'
import { formatKstHHMM } from '../utils/kst'

type Dict = Record<string, unknown>

const PRIMARY_ORDER: Record<StrategyStatusResult['primary'], number> = { live: 0, paused: 1, shadow: 2, off: 3 }

const PRIMARY_CLS: Record<StrategyStatusResult['primary'], string> = {
  off: 'bg-gray-100 text-gray-600',
  paused: 'bg-amber-100 text-amber-800',
  shadow: 'bg-violet-100 text-violet-800',
  live: 'bg-emerald-100 text-emerald-800',
}

/** M6 — 손절 여유 근접은 색 클래스로(data-tone 속성만으로는 안 보인다). */
const STOP_TONE_CLS: Record<'normal' | 'orange' | 'red', string> = {
  normal: '',
  orange: 'text-amber-600 font-semibold',
  red: 'text-rose-600 font-semibold',
}

function finiteOrNull(v: unknown): number | null {
  // 「모름」을 「0」으로 둔갑시키지 않는다 — `Number(null) === 0`.
  if (v === null || v === undefined) return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

/** `mmdd` — `StrategyMonitor.tsx` 와 같은 포맷("MM-DD"). 이 파일은 별도 로컬 복사본을 둔다
 * (공유 모듈로 올릴 만큼 쓰는 곳이 늘기 전까지는 분리 비용이 더 크다). */
function mmdd(dateStr: string | undefined | null): string {
  if (!dateStr) return '—'
  return dateStr.length >= 10 ? dateStr.slice(5, 10) : dateStr
}

/** M11 — 14일 최종 후보 수 선(svg). 요약표 한 칸용으로 작게.
 * 보완 3차(N-C) — `<title>`·`aria-label` 에 날짜·값을 담는다(정적 문구만으로는 스크린리더가 값을
 * 읽을 수 없다 — 사다리(Ladder)·14일 추이(StrategyMonitor) 와 같은 규약). */
function MiniTrend({ data }: { data: Array<{ date: string; count: number }> | null | undefined }) {
  if (!data || data.length === 0) return <span className="text-gray-300 text-[10px]">—</span>
  const max = Math.max(1, ...data.map((d) => d.count))
  const w = 56
  const h = 18
  const points = data
    .map((d, i) => {
      const x = data.length > 1 ? (i / (data.length - 1)) * w : w / 2
      const y = h - (d.count / max) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const fullLabel = `14일 최종 후보 추이 — ${data.map((d) => `${mmdd(d.date)}:${d.count}`).join(' · ')}`
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={fullLabel}>
      <title>{fullLabel}</title>
      <polyline points={points} fill="none" stroke="#6366f1" strokeWidth={1.5} />
    </svg>
  )
}

/** 「왜 안 사나」 한 줄 — §5.2, 처음 맞는 것 하나(H3 — 엔진 정지를 꺼짐 다음 최우선으로 더했다). */
function summaryWhy(
  sid: string,
  info: StrategyInfo,
  status: StrategyStatusResult,
  routeEntry: Dict | null | undefined,
  now: Date,
  engineStopped: boolean,
): string {
  if (status.primary === 'off') {
    const positions = info.positions ?? 0
    return positions > 0 ? `꺼짐 — 보유 ${positions} 손절 정지!` : '꺼짐'
  }
  // H3 — 엔진이 안 돌면(정산 뒤·부팅 전·휴일) 그 밖 어떤 판정도 지금 값으로는 믈 수 없다.
  if (engineStopped) return '장 마감/엔진 정지'
  if (status.primary === 'paused') return '신규 매수 멈춤(운영자 설정)'

  const prepare = routeEntry?.prepare as Dict | null | undefined
  if (prepare) {
    if (prepare.ok === false) {
      const hhmm = formatKstHHMM((prepare.finished_at as string | null) ?? (prepare.started_at as string | null))
      return `후보 준비 실패 ${hhmm}`
    }
    if (prepare.ok === null || prepare.ok === undefined) return '준비 중'
  }

  const steps = (routeEntry?.funnel as Array<{ step_no: number; step_name: string; survived_count: number }> | undefined) ?? []
  // M7 — 최종 단계 = 전략별 최종 step_no(donchian·VCP·BFB·kojiro = 9, 고정 99 매칭 금지).
  const finalStep = finalFunnelStep(steps)
  if (finalStep && finalStep.survived_count === 0) {
    const bn = funnelBottleneck(steps)
    const bStep = bn != null ? steps.find((s) => s.step_no === bn) : null
    return `후보 0 — 병목: ${bStep?.step_name ?? '모름'}`
  }

  if (info.buy_disabled === true) return '매수 중단(일일 손실 한도 또는 19:50 이후)'

  const maxPositions = Number((info.params as Dict | undefined)?.max_positions)
  if (Number.isFinite(maxPositions) && maxPositions > 0 && (info.positions ?? 0) >= maxPositions) {
    return `보유 한도 ${info.positions}/${maxPositions}`
  }

  const params = (info.params ?? {}) as Dict
  const win = entryWindow(sid, params, now)
  if (win && win.state === 'before') return `진입창 밖 — ${win.start} 부터`
  if (win && win.state === 'after') return `진입창 밖 — 다음 ${win.start}`

  const marketUnit = routeEntry?.market_unit as Dict | null | undefined
  const muBlock = marketUnitBlockLabel(sid, marketUnit as never)
  if (muBlock) return muBlock

  if (status.primary !== 'shadow' && (info.weight ?? 0) === 0) return '예산 0'

  const skips = routeEntry?.skips as Dict | undefined
  if (skips?.known) {
    const top = topSkipReason(skips.counts as Record<string, number> | undefined)
    if (top) return `오늘 주 사유: ${top.label} · ${top.count}종목`
  }

  if (status.primary === 'shadow') {
    // N8(screens) — 모니터 라우트가 실패하면(routeEntry 없음) 섀도 기록 수를 모른다 — 0 단정 금지.
    if (!routeEntry) return '섀도 기록 모름(모니터 라우트 실패)'
    const shadowBuys = (routeEntry.shadow_buys as string[] | undefined) ?? []
    return `섀도 기록 ${shadowBuys.length}`
  }

  const candidateCount = finalStep ? finalStep.survived_count : Object.keys(info.targets ?? {}).length
  return `대기 중 — 후보 ${candidateCount}`
}

interface Props {
  strategies: Record<string, StrategyInfo>
  monitor?: StrategyMonitorResponse | null
  exitLines?: ExitLineItem[] | null
  tickerPrices?: Record<string, TickerPrice>
  /** M11 — 전략별 14일 최종 후보 추이(`/api/strategy-funnel/recent`). */
  funnelTrends?: Record<string, Array<{ date: string; count: number }>> | null
  now?: Date
  /** N4(screens)·N1(suites) — `/api/trading/status` 의 `running`. 모니터 라우트가 실패해도(=null)
   * 엔진 정지를 안다. 이게 없으면 「정산 뒤 라우트 실패」 조합에서 「왜 안 사나」가 평소 판정으로
   * 되돌아간다. */
  running?: boolean | null
  onSelect: (sid: string) => void
}

export default function StrategySummaryTable({ strategies, monitor, exitLines, tickerPrices, funnelTrends, now, running, onSelect }: Props) {
  const nowDate = now ?? new Date()
  const prices = tickerPrices ?? {}
  // H3/N4 — running(=/trading/status) 또는 monitor.running 둘 중 하나라도 false 면 멈춘 것으로 본다
  // (모니터 라우트가 실패해도(monitor=null) running prop 으로 엔진 정지를 안다).
  const engineStopped = running === false || monitor?.running === false
  const rows = Object.entries(strategies)
    .map(([sid, info]) => {
      const routeEntry = (monitor?.strategies?.[sid] ?? null) as unknown as Dict | null
      const status = strategyStatus(sid, info, (routeEntry?.market_unit ?? null) as never)
      return { sid, info, routeEntry, status }
    })
    .sort((a, b) => {
      const byPrimary = PRIMARY_ORDER[a.status.primary] - PRIMARY_ORDER[b.status.primary]
      if (byPrimary !== 0) return byPrimary
      return (b.info.weight ?? 0) - (a.info.weight ?? 0)
    })

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">전략 진행상황 요약</h3>
      <div data-testid="strategy-summary-table">
        {/* M12 — 요약표는 높이 상한 상자(ScrollPane maxHeight)에 가두지 않는다. 가로 스크롤만. */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-xs">
          <thead>
            <tr className="text-gray-500 border-b text-left">
              <th className="py-1 pr-2">전략</th>
              <th className="py-1 pr-2">상태</th>
              <th className="py-1 pr-2">왜 안 사나</th>
              <th className="py-1 px-2 text-right">후보</th>
              <th className="py-1 px-2 text-right">14일</th>
              <th className="py-1 px-2 text-right">보유</th>
              <th className="py-1 px-2 text-right">예산</th>
              <th className="py-1 px-2 text-right">손절 여유</th>
              <th className="py-1 px-2 text-right">청산 예정</th>
              <th className="py-1 pl-2 text-right">오늘 신호</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ sid, info, routeEntry, status }) => {
              const positions = info.positions ?? 0
              const maxPositions = finiteOrNull((info.params as Dict | undefined)?.max_positions)
              const invested = finiteOrNull(info.invested_amount)
              const total = finiteOrNull(info.total_investment)
              const budgetPct = invested !== null && total !== null && total > 0 ? Math.round((invested / total) * 100) : null

              const myExitLines = (exitLines ?? []).filter((it) => it.strategy_id === sid)
              let stopMarginPct: number | null = null
              for (const item of myExitLines) {
                const cur = finiteOrNull(prices[item.ticker]?.current_price)
                if (cur === null || cur <= 0 || item.stop_price == null) continue
                const d = ((cur - item.stop_price) / cur) * 100
                if (stopMarginPct === null || d < stopMarginPct) stopMarginPct = d
              }
              const stopTone: 'normal' | 'orange' | 'red' = stopMarginPct === null
                ? 'normal'
                : stopMarginPct < 1 ? 'red' : stopMarginPct < 3 ? 'orange' : 'normal'

              let exitDue = 0
              const exitDueApplies = sid === 'etf_trend' || sid === 'donchian_swing'
              if (sid === 'etf_trend') {
                // M3 — ETF 「청산 예정」은 가격이 돌파선 아래일 때만(엔진은 missing_line 이면 판정 안 함).
                for (const [ticker, t] of Object.entries((routeEntry?.holdings ?? {}) as Record<string, Dict>)) {
                  const bf = (t.breakout_fail ?? {}) as Dict
                  if (bf.active !== true) continue
                  const bLine = finiteOrNull(bf.line)
                  if (bLine === null) continue
                  const cur = finiteOrNull(prices[ticker]?.current_price)
                  if (cur !== null && cur < bLine) exitDue += 1
                }
              } else if (sid === 'donchian_swing') {
                for (const t of Object.values((routeEntry?.holdings ?? {}) as Record<string, Dict>)) {
                  if (t.reached_1r === true) continue
                  const timeExitBars = finiteOrNull(t.time_exit_bars)
                  const daysHeld = finiteOrNull(t.days_held)
                  if (timeExitBars === null || daysHeld === null) continue
                  if (timeExitBars - 1 - daysHeld <= 0) exitDue += 1
                }
              }
              // N4(screens)·N1(suites) — 엔진 정지 중에는 「0」이 「청산 대상 없음」으로 읽히면
              // 안 된다(정산이 비운 값일 수 있다). 모니터 라우트가 실패하면(routeEntry 없음)
              // 애초에 이 계산에 쓸 holdings 자체가 없어 0 이 「모른다」의 둔갑일 수 있다.
              const exitDueUnknown = engineStopped || (exitDueApplies && !routeEntry)

              const shadowBuys = (routeEntry?.shadow_buys as string[] | undefined) ?? []
              const signalsUnknown = engineStopped || (status.primary === 'shadow' && !routeEntry)
              const signalsText = status.primary === 'shadow' ? `섀도 ${shadowBuys.length}` : `${(info.buy_signals ?? []).length}`

              const redChips = status.chips.filter((c) => c.tone === 'red')

              const steps = (routeEntry?.funnel as Array<{ step_no: number; step_name: string; survived_count: number }> | undefined) ?? []
              const finalStep = finalFunnelStep(steps)
              const candidateCount = finalStep ? finalStep.survived_count : Object.keys(info.targets ?? {}).length
              const bottleneckNo = funnelBottleneck(steps)
              const bottleneckStep = bottleneckNo != null ? steps.find((s) => s.step_no === bottleneckNo) : null

              return (
                <tr
                  key={sid}
                  data-testid={`strategy-summary-row-${sid}`}
                  onClick={() => onSelect(sid)}
                  className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                >
                  <td className="py-1 pr-2 font-medium text-gray-800">{strategyLabel(sid, info.name)}</td>
                  <td className="py-1 pr-2">
                    <span
                      data-testid={`strategy-summary-badge-${sid}`}
                      className={`whitespace-nowrap px-1.5 py-0.5 rounded text-[11px] font-semibold ${PRIMARY_CLS[status.primary]}`}
                    >
                      {status.label}
                    </span>
                    {redChips.map((c) => (
                      <span key={c.kind} className="ml-1 text-[11px] text-rose-700 font-semibold">{c.label}</span>
                    ))}
                  </td>
                  <td data-testid={`strategy-summary-why-${sid}`} className="py-1 pr-2 text-gray-600">
                    {summaryWhy(sid, info, status, routeEntry, nowDate, engineStopped)}
                  </td>
                  <td className="py-1 px-2 text-right text-gray-600">
                    {candidateCount}
                    {candidateCount === 0 && bottleneckStep && (
                      <div className="text-[10px] text-rose-500">병목: {bottleneckStep.step_name}</div>
                    )}
                  </td>
                  <td data-testid={`strategy-summary-trend-${sid}`} className="py-1 px-2 text-right">
                    <MiniTrend data={funnelTrends?.[sid] ?? null} />
                  </td>
                  <td data-testid={`strategy-summary-holdings-${sid}`} className="py-1 px-2 text-right">
                    {engineStopped ? (
                      <span className="text-gray-400">모름</span>
                    ) : (
                      <div className="flex items-center justify-end gap-1.5">
                        <span>{positions} / {maxPositions ?? '—'}</span>
                        {maxPositions !== null && maxPositions > 0 && maxPositions <= 20 && (
                          <span className="inline-flex gap-0.5">
                            {Array.from({ length: maxPositions }).map((_, i) => (
                              <span
                                key={i}
                                data-filled={i < positions ? 'true' : 'false'}
                                className={`inline-block w-1.5 h-3 rounded-sm ${i < positions ? 'bg-emerald-400' : 'bg-gray-200'}`}
                              />
                            ))}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td data-testid={`strategy-summary-budget-${sid}`} className="py-1 px-2 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <span>{budgetPct !== null ? `${budgetPct}%` : '—'}</span>
                      {budgetPct !== null && (
                        <span className="inline-block w-10 h-1.5 bg-gray-200 rounded overflow-hidden align-middle">
                          <span style={{ width: `${Math.min(100, Math.max(0, budgetPct))}%` }} className="block h-full bg-blue-400" />
                        </span>
                      )}
                    </div>
                  </td>
                  <td
                    data-testid={`strategy-summary-stopmargin-${sid}`}
                    data-tone={stopTone}
                    className={`py-1 px-2 text-right ${STOP_TONE_CLS[stopTone]}`}
                  >
                    {stopMarginPct !== null ? `${stopMarginPct.toFixed(1)}%` : '—'}
                  </td>
                  <td data-testid={`strategy-summary-exitdue-${sid}`} className="py-1 px-2 text-right">
                    {exitDueUnknown ? <span className="text-gray-400">모름</span> : exitDue}
                  </td>
                  <td data-testid={`strategy-summary-signals-${sid}`} className="py-1 pl-2 text-right">
                    {signalsUnknown ? <span className="text-gray-400">모름</span> : signalsText}
                  </td>
                </tr>
              )
            })}
          </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
