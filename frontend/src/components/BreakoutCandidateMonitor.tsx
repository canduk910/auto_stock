// VCP(vcp_breakout)/BFB(bull_flag_breakout) 전용 후보 진단 그리드 (2026-08-06).
// 두 전략 모두 VB 타겟표를 재사용하던 기존 화면이 "K값 0.000 · 시가 -"만 보여줘
// "왜 안 사는가"에 답하지 못했다 (VCP 후보 0 / BFB 후보 18 중 33% WebSocket 미구독).
// get_targets_status 진단 필드(손절선/거래량컷/상태)와 구독 커버리지를 전용 패널로 노출.
import { useMemo } from 'react'
import type { BreakoutDiagTarget, StrategyInfo, TickerPrice } from '../types/trading'

const STRATEGY_LABEL: Record<'vcp_breakout' | 'bull_flag_breakout', string> = {
  vcp_breakout: 'VCP 변동성 수축',
  bull_flag_breakout: '눌림목 돌파',
}

function num(v: unknown, dflt: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : dflt
}

// 거리%/손익 부호 컬러 — 이익 빨강/손실 파랑 관례 (TradePnLGrid.pnlClass 패턴 답습).
function signColor(v: number | null): string {
  if (v === null || !Number.isFinite(v) || v === 0) return 'text-gray-500'
  return v > 0 ? 'text-red-600 font-medium' : 'text-blue-600 font-medium'
}

// KST 기준 오늘 날짜 문자열 (YYYY-MM-DD) — cooldown_until(date) 비교용.
function kstTodayStr(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())
}

// cooldown_until 까지 남은 일수. 파싱 실패 시 null (배지는 "쿨다운" 로 폴백).
function daysUntil(cooldownUntil?: string | null): number | null {
  if (!cooldownUntil) return null
  const todayMs = Date.parse(`${kstTodayStr()}T00:00:00Z`)
  const untilMs = Date.parse(`${cooldownUntil}T00:00:00Z`)
  if (Number.isNaN(todayMs) || Number.isNaN(untilMs)) return null
  return Math.max(0, Math.round((untilMs - todayMs) / 86_400_000))
}

// BFB breakout_seen_at(첫 돌파 감지 KST ISO) 경과 → retention_minutes 잔여 초.
function retentionRemainSec(seenAt: string, retentionMinutes?: number): number | null {
  const seenMs = Date.parse(seenAt)
  if (Number.isNaN(seenMs)) return null
  const totalSec = num(retentionMinutes, 0) * 60
  const elapsedSec = Math.floor((Date.now() - seenMs) / 1000)
  return totalSec - elapsedSec
}

interface StatusBadge {
  label: string
  cls: string
}

// 상태 배지 우선순위: 매수완료 > 쿨다운 D-n > 미구독 > retention 대기(BFB) > 대기.
function computeStatus(t: BreakoutDiagTarget, subscribed: boolean, isBfb: boolean): StatusBadge {
  if (t.bought_today) {
    return { label: '매수완료', cls: 'bg-emerald-100 text-emerald-700' }
  }
  if (t.in_cooldown) {
    const days = daysUntil(t.cooldown_until)
    return { label: days != null ? `쿨다운 D-${days}` : '쿨다운', cls: 'bg-slate-200 text-slate-600' }
  }
  if (!subscribed) {
    return { label: '📵 미구독', cls: 'bg-red-100 text-red-700' }
  }
  if (isBfb && t.breakout_seen_at) {
    const remain = retentionRemainSec(t.breakout_seen_at, t.retention_minutes)
    if (remain !== null && remain > 0) {
      const m = Math.floor(remain / 60)
      const s = remain % 60
      return { label: `⏱ ${m}:${String(s).padStart(2, '0')} 대기`, cls: 'bg-amber-100 text-amber-700' }
    }
  }
  return { label: '대기', cls: 'bg-gray-100 text-gray-500' }
}

/** 현재 KST 시각을 `HH:MM` 로. 브라우저 로컬타임 추출 금지 규약 — `Intl` 명시. */
export function kstNowHhmm(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(now)
}

/**
 * 진입 시간창 배지 — "지금 매수가 가능한가"를 먼저 답한다.
 *
 * 후보가 아무리 좋아도 `entry_start ~ entry_end` 밖이면 `check_buy_signal` 이
 * `Signal.NONE` 을 돌려준다. 체결 0건 진단에서 가장 먼저 배제해야 할 사유다.
 * 파라미터가 없으면(구버전 응답) 아무것도 렌더하지 않는다 — 추측하지 않는다.
 */
export function EntryWindowBadge({
  params, now,
}: { params?: Record<string, unknown>; now?: Date }) {
  const start = typeof params?.entry_start === 'string' ? params.entry_start : ''
  const end = typeof params?.entry_end === 'string' ? params.entry_end : ''
  if (!start || !end) return null
  const cur = kstNowHhmm(now)
  const open = cur >= start && cur <= end
  return (
    <div
      data-testid="breakout-entry-window"
      className={`rounded border px-3 py-2 text-xs ${
        open
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
          : 'border-gray-200 bg-gray-50 text-gray-600'
      }`}
    >
      <span className="font-semibold tabular-nums">진입창 {start}~{end} (KST)</span>
      <span className="ml-2">
        {open
          ? `· 현재 ${cur} — 진입 가능`
          : `· 현재 ${cur} — 시간창 밖이라 매수 신호가 발생하지 않습니다`}
      </span>
    </div>
  )
}

export default function BreakoutCandidateMonitor({
  strategyId,
  strategies,
  tickerPrices,
  subscribedTickers,
}: {
  strategyId: 'vcp_breakout' | 'bull_flag_breakout'
  strategies: Record<string, StrategyInfo>
  tickerPrices?: Record<string, TickerPrice>
  subscribedTickers?: string[]
}) {
  const strat = strategies[strategyId]
  const isBfb = strategyId === 'bull_flag_breakout'
  const label = STRATEGY_LABEL[strategyId]
  const targets = (strat?.targets ?? {}) as Record<string, BreakoutDiagTarget>
  const prices = tickerPrices ?? {}
  const subscribedSet = useMemo(() => new Set(subscribedTickers ?? []), [subscribedTickers])

  const candidateTickers = useMemo(() => Object.keys(targets), [targets])
  const missingTickers = useMemo(
    () => candidateTickers.filter((t) => !subscribedSet.has(t)),
    [candidateTickers, subscribedSet],
  )
  const subscribedCount = candidateTickers.length - missingTickers.length

  // 돌파선 근접순(거리% 내림차순) — 가장 가까운(또는 이미 돌파한) 종목이 위로.
  // 현재가 미수신(distPct=null) 종목은 정렬 최하단.
  const rows = useMemo(() => {
    return candidateTickers
      .map((ticker) => {
        const t = targets[ticker]
        const curPrice = num(prices[ticker]?.current_price, 0)
        const targetPrice = num(t.target_price, 0)
        const distPct =
          curPrice > 0 && targetPrice > 0 ? ((curPrice - targetPrice) / targetPrice) * 100 : null
        return { ticker, t, curPrice, targetPrice, distPct }
      })
      .sort((a, b) => (b.distPct ?? -Infinity) - (a.distPct ?? -Infinity))
  }, [candidateTickers, targets, prices])

  if (!strat) {
    return (
      <div data-testid="breakout-candidate-monitor-empty" className="text-sm text-gray-400 py-4 text-center">
        {label} 전략 데이터가 아직 없습니다.
      </div>
    )
  }

  return (
    <div data-testid="breakout-candidate-monitor" className="space-y-3 mb-4">
      {/* 0. 진입 게이트 — 시간창 밖이면 후보가 아무리 좋아도 매수 신호가 안 난다.
             사이클 18 의 보드 불일치 라벨("돌파 (대기 — 메인)")을 대체·구체화한 것.
             VCP 09:05~14:30 / BFB 09:05~13:00 은 둘 다 MAIN(09:00~15:30) 안이라
             시간창 판정이 보드 판정을 포함한다. */}
      <EntryWindowBadge params={strat.params} />

      {/* 1. 구독 커버리지 배너 */}
      <div
        data-testid="breakout-subscription-coverage"
        className={`rounded border px-3 py-2 text-xs ${
          missingTickers.length > 0
            ? 'border-amber-300 bg-amber-50 text-amber-800'
            : 'border-emerald-200 bg-emerald-50 text-emerald-800'
        }`}
      >
        <div className="font-semibold">
          후보 {candidateTickers.length}종목 중 {subscribedCount}종목 구독 · {missingTickers.length}종목 시세 미수신
        </div>
        {missingTickers.length > 0 && (
          <div className="mt-1">시세 미수신 종목은 매수 신호 평가 자체가 일어나지 않습니다.</div>
        )}
      </div>

      {/* 2. 후보 그리드 */}
      <div data-testid="breakout-candidate-grid" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-2">
          {label} 후보 종목{' '}
          <span className="text-xs text-gray-400">({candidateTickers.length}종목 · 돌파선 근접순)</span>
        </h4>
        {rows.length === 0 ? (
          <div className="text-xs text-gray-400">
            후보 0종목 — 진입 조건에서 전량 탈락. 깔때기 화면에서 병목 단계를 확인하세요.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="text-left py-1 pr-2">종목명</th>
                  <th className="text-right py-1 px-2">현재가</th>
                  <th className="text-right py-1 px-2">돌파선</th>
                  <th className="text-right py-1 px-2">거리%</th>
                  <th className="text-right py-1 px-2">손절선</th>
                  {isBfb && <th className="text-right py-1 px-2">측정목표</th>}
                  <th className="text-right py-1 px-2">거래량컷</th>
                  <th className="text-center py-1 pl-2">상태</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ ticker, t, curPrice, targetPrice, distPct }) => {
                  const name = t.name || ticker
                  const subscribed = subscribedSet.has(ticker)
                  const status = computeStatus(t, subscribed, isBfb)
                  const stopLine = num(t.stop_line, 0)
                  const volumeThreshold = num(t.volume_threshold, 0)
                  const measuredTarget = num(t.measured_target, 0)
                  return (
                    <tr key={ticker} data-testid={`breakout-candidate-row-${ticker}`} className="border-b border-gray-100">
                      <td className="py-1 pr-2 font-medium text-gray-800">{name}</td>
                      <td className="py-1 px-2 text-right text-gray-800">
                        {curPrice > 0 ? curPrice.toLocaleString() : '-'}
                      </td>
                      <td className="py-1 px-2 text-right text-indigo-600">
                        {targetPrice > 0 ? targetPrice.toLocaleString() : '-'}
                      </td>
                      <td className={`py-1 px-2 text-right ${signColor(distPct)}`}>
                        {distPct === null ? '-' : `${distPct >= 0 ? '+' : ''}${distPct.toFixed(2)}%`}
                      </td>
                      <td className="py-1 px-2 text-right text-gray-600">
                        {stopLine > 0 ? stopLine.toLocaleString() : '-'}
                      </td>
                      {isBfb && (
                        <td className="py-1 px-2 text-right text-gray-600">
                          {measuredTarget > 0 ? measuredTarget.toLocaleString() : '-'}
                        </td>
                      )}
                      <td className="py-1 px-2 text-right text-gray-600">
                        {volumeThreshold > 0 ? volumeThreshold.toLocaleString() : '-'}
                      </td>
                      <td className="py-1 pl-2 text-center">
                        <span
                          data-testid={`breakout-status-${ticker}`}
                          className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-medium ${status.cls}`}
                        >
                          {status.label}
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
    </div>
  )
}
