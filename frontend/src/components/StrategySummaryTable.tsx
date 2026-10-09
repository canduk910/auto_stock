/**
 * cycle414 — 대시보드 「전체」 탭 전략 요약표(명세 `_workspace/red/cycle414/monitor_spec.md` §5).
 *
 * 행 = 전략 하나(주 배지 실매매→멈춤→섀도→꺼짐 순서, 같은 묶음은 비중 내림차순). 행을 누르면
 * 그 전략 탭으로 간다(`onSelect`). 「왜 안 사나」 한 줄은 §5.2 12단계 우선순위(처음 맞는 하나).
 */
import type { ExitLineItem, StrategyInfo, StrategyMonitorResponse, TickerPrice } from '../types/trading'
import {
  strategyStatus, funnelBottleneck, entryWindow, marketUnitBlockLabel, topSkipReason,
  type StrategyStatusResult,
} from '../utils/strategyMonitor'
import { formatKstHHMM } from '../utils/kst'
import ScrollPane from './ScrollPane'

type Dict = Record<string, unknown>

const PRIMARY_ORDER: Record<StrategyStatusResult['primary'], number> = { live: 0, paused: 1, shadow: 2, off: 3 }

const PRIMARY_CLS: Record<StrategyStatusResult['primary'], string> = {
  off: 'bg-gray-100 text-gray-600',
  paused: 'bg-amber-100 text-amber-800',
  shadow: 'bg-violet-100 text-violet-800',
  live: 'bg-emerald-100 text-emerald-800',
}

function finiteOrNull(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

/** 「왜 안 사나」 한 줄 — §5.2, 처음 맞는 것 하나. */
function summaryWhy(
  sid: string,
  info: StrategyInfo,
  status: StrategyStatusResult,
  routeEntry: Dict | null | undefined,
  now: Date,
): string {
  if (status.primary === 'off') {
    const positions = info.positions ?? 0
    return positions > 0 ? `꺼짐 — 보유 ${positions} 손절 정지!` : '꺼짐'
  }
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
  const finalStep = steps.find((s) => s.step_no === 99)
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
    const shadowBuys = (routeEntry?.shadow_buys as string[] | undefined) ?? []
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
  now?: Date
  onSelect: (sid: string) => void
}

export default function StrategySummaryTable({ strategies, monitor, exitLines, tickerPrices, now, onSelect }: Props) {
  const nowDate = now ?? new Date()
  const prices = tickerPrices ?? {}
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
        <ScrollPane>
          <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b text-left">
              <th className="py-1 pr-2">전략</th>
              <th className="py-1 pr-2">상태</th>
              <th className="py-1 pr-2">왜 안 사나</th>
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
              if (sid === 'etf_trend') {
                for (const t of Object.values((routeEntry?.holdings ?? {}) as Record<string, Dict>)) {
                  const bf = (t.breakout_fail ?? {}) as Dict
                  if (bf.active === true) exitDue += 1
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

              const shadowBuys = (routeEntry?.shadow_buys as string[] | undefined) ?? []
              const signalsText = status.primary === 'shadow' ? `섀도 ${shadowBuys.length}` : `${(info.buy_signals ?? []).length}`

              const redChips = status.chips.filter((c) => c.tone === 'red')

              return (
                <tr
                  key={sid}
                  data-testid={`strategy-summary-row-${sid}`}
                  onClick={() => onSelect(sid)}
                  className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                >
                  <td className="py-1 pr-2 font-medium text-gray-800">{info.name || sid}</td>
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
                    {summaryWhy(sid, info, status, routeEntry, nowDate)}
                  </td>
                  <td data-testid={`strategy-summary-holdings-${sid}`} className="py-1 px-2 text-right">
                    {positions} / {maxPositions ?? '—'}
                  </td>
                  <td data-testid={`strategy-summary-budget-${sid}`} className="py-1 px-2 text-right">
                    {budgetPct !== null ? `${budgetPct}%` : '—'}
                  </td>
                  <td
                    data-testid={`strategy-summary-stopmargin-${sid}`}
                    data-tone={stopTone}
                    className="py-1 px-2 text-right"
                  >
                    {stopMarginPct !== null ? `${stopMarginPct.toFixed(1)}%` : '—'}
                  </td>
                  <td data-testid={`strategy-summary-exitdue-${sid}`} className="py-1 px-2 text-right">
                    {exitDue}
                  </td>
                  <td data-testid={`strategy-summary-signals-${sid}`} className="py-1 pl-2 text-right">
                    {signalsText}
                  </td>
                </tr>
              )
            })}
          </tbody>
          </table>
        </ScrollPane>
      </div>
    </div>
  )
}
