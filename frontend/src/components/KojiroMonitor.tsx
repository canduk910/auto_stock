// 고지로(kojiro) 대순환 스윙 전용 모니터링 패널 (대시보드 kojiro 탭).
// 운영 활성 전략 — 상태 배지는 공통 판정(strategyStatus, §2.2)을 쓴다. 보유 방어선의 실효
// 손절선은 엔진 값(exit-lines `stop_price`)이 정본이고, 구성 선(하드/트레일)은 exit-lines
// `entry_atr` 로 그린다(후보 ATR 로 화면이 다시 계산하지 않는다 — cycle414 §4.5).
import { useMemo } from 'react'
import type { StrategyInfo, KojiroTarget, TickerPrice, ExitLineItem, StrategyMonitorResponse } from '../types/trading'
import { formatKstDateTime } from '../utils/kst'
import { strategyStatus, type MonitorTone } from '../utils/strategyMonitor'
import ScrollPane from './ScrollPane'

// 대순환 6 스테이지 (EMA 5/20/40 배열). 1→2→3→4→5→6→1 순환.
const STAGE_META: Record<number, { arrange: string; role: string; tone: string }> = {
  1: { arrange: '단기>중기>장기', role: '완전 정배열 · 진입', tone: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  2: { arrange: '중기>단기>장기', role: '상승 후반', tone: 'bg-lime-100 text-lime-800 border-lime-300' },
  3: { arrange: '중기>장기>단기', role: '추세 종료 · 청산', tone: 'bg-rose-100 text-rose-800 border-rose-300' },
  4: { arrange: '장기>중기>단기', role: '완전 역배열', tone: 'bg-gray-100 text-gray-700 border-gray-300' },
  5: { arrange: '장기>단기>중기', role: '하락 후반', tone: 'bg-sky-100 text-sky-800 border-sky-300' },
  6: { arrange: '단기>장기>중기', role: '바닥 반등 초입', tone: 'bg-amber-100 text-amber-700 border-amber-300' },
}

// 유니버스 깔때기 9단계(폴백 — 라우트 `/strategies/monitor` 가 없을 때만) — kojiro `_empty_scan_stats` 키와 정합.
// 🔴 숫자 문턱(밴드 범위·신선도)은 라벨에 박지 않는다 — params 에서 읽어 게이지/캡션에 따로 보인다(cycle414 §4.5 C1).
const KOJIRO_STAGES: Array<{ key: string; label: string }> = [
  { key: 'universe_union', label: '전체 상장 유니버스 (필터 전)' },
  { key: 'universe_candidates', label: '시총+거래대금 컷 통과' },
  { key: 'universe_filtered', label: '유니버스 확정 (ETF/6자리 제외)' },
  { key: 'candle_fetch_ok', label: '일봉 fetch + 전일종가>0 + 워밍업' },
  { key: 'band_pass', label: 'ATR/종가 변동성 밴드' },
  { key: 'stage_valid_pass', label: '스테이지 판별 가능 (EMA 동가 제외)' },
  { key: 'stage1_uptrend_pass', label: '스테이지1 + EMA 3선 우상향' },
  { key: 'strict_entry_pass', label: '6→1 전환 인접 + 종가>EMA5' },
  { key: 'final_prepared', label: '최종 후보' },
]

const TONE_BADGE_CLS: Record<'off' | 'paused' | 'shadow' | 'live', string> = {
  off: 'border-gray-200 bg-gray-50 text-gray-600',
  paused: 'border-amber-300 bg-amber-50 text-amber-800',
  shadow: 'border-violet-200 bg-violet-50 text-violet-800',
  live: 'border-emerald-200 bg-emerald-50 text-emerald-800',
}

const CHIP_TONE_CLS: Record<MonitorTone, string> = {
  red: 'bg-rose-100 text-rose-700 font-semibold',
  orange: 'bg-amber-100 text-amber-700',
  gray: 'bg-gray-100 text-gray-600',
  violet: 'bg-violet-100 text-violet-700',
}

function num(v: unknown, dflt: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : dflt
}

function finiteOrNull(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

function StageBadge({ stage }: { stage: number }) {
  const meta = STAGE_META[stage]
  if (!meta) {
    return <span className="inline-block px-1.5 py-0.5 rounded text-xs border bg-gray-50 text-gray-400 border-gray-200">-</span>
  }
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-xs font-semibold border ${meta.tone}`}
      title={`스테이지 ${stage} (${meta.arrange}) — ${meta.role}`}
    >
      {stage}
    </span>
  )
}

export default function KojiroMonitor({
  strategies,
  tickerPrices,
  exitLines,
  monitor,
  running,
}: {
  strategies: Record<string, StrategyInfo>
  tickerPrices?: Record<string, TickerPrice>
  exitLines?: ExitLineItem[] | null
  monitor?: StrategyMonitorResponse | null
  /** cycle414 보완 2차(N5 screens/screens-H3 잔여) — `/api/trading/status` 의 `running`. 모니터
   * 라우트가 실패해도(=null) 엔진 정지를 안다. `=== false` 일 때만 「모름」으로 낮춘다. */
  running?: boolean | null
}) {
  const kojiro = strategies['kojiro']
  const engineStopped = running === false

  const scanStats = kojiro?.scan_stats ?? null
  const targets = (kojiro?.targets ?? {}) as Record<string, KojiroTarget>
  const params = (kojiro?.params ?? {}) as Record<string, unknown>
  const positions = kojiro?.positions_detail ?? {}
  const buySignals = kojiro?.buy_signals ?? []
  const prices = tickerPrices ?? {}
  const routeEntry = monitor?.strategies?.kojiro ?? null
  const routeFunnel = routeEntry?.funnel ?? []

  const stopAtr = num(params.stop_atr, 2.0)
  const trailAtr = num(params.trail_atr, 2.5)
  const hardStopPct = num(params.hard_stop_pct, -8.0)
  const bandMinRaw = finiteOrNull(params.atr_ratio_min)
  const bandMaxRaw = finiteOrNull(params.atr_ratio_max)
  const hasBand = bandMinRaw !== null && bandMaxRaw !== null && bandMaxRaw > bandMinRaw
  const bandMin = hasBand ? (bandMinRaw as number) : 0
  const bandMax = hasBand ? (bandMaxRaw as number) : 0
  const freshness = finiteOrNull(params.stage1_freshness)
  const gapUpPct = finiteOrNull(params.gap_up_skip_pct)
  const gapDownPct = finiteOrNull(params.gap_down_skip_pct)

  const status = useMemo(
    () => (kojiro ? strategyStatus('kojiro', kojiro, routeEntry?.market_unit) : null),
    [kojiro, routeEntry],
  )

  const exitLineMap = useMemo(() => {
    const m = new Map<string, ExitLineItem>()
    for (const item of exitLines ?? []) if (item.strategy_id === 'kojiro') m.set(item.ticker, item)
    return m
  }, [exitLines])

  // 스테이지 분포 히스토그램 (후보 targets 기준)
  const stageDist = useMemo(() => {
    const d: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 }
    for (const t of Object.values(targets)) {
      const s = Number(t?.stage ?? 0)
      if (s >= 1 && s <= 6) d[s] += 1
    }
    return d
  }, [targets])

  const candidateEntries = useMemo(
    () => Object.entries(targets).sort((a, b) => (a[1]?.stage ?? 0) - (b[1]?.stage ?? 0)),
    [targets],
  )

  if (!kojiro || !status) {
    return (
      <div data-testid="kojiro-monitor-empty" className="text-sm text-gray-400 py-4 text-center">
        고지로 전략 데이터가 아직 없습니다.
      </div>
    )
  }

  return (
    <div data-testid="kojiro-monitor" className="space-y-4">
      {/* 1. 상태 배너 — 공통 상태 배지(§2.2: 꺼짐·멈춤·섀도·실매매) + 보조 칩. */}
      <div
        data-testid="kojiro-darklaunch-banner"
        className={`rounded border px-3 py-2 text-xs ${TONE_BADGE_CLS[status.primary]}`}
      >
        <div className="flex items-center justify-between flex-wrap gap-1">
          <span className="font-semibold whitespace-nowrap">{status.label}</span>
          <span className="text-gray-500">
            비중 {Math.round((kojiro.weight ?? 0) * 100)}% · 마지막 스캔 {formatKstDateTime(scanStats?.last_run_at)}
          </span>
        </div>
        {status.chips.length > 0 && (
          <div className="mt-1 flex items-center gap-1 flex-wrap">
            {status.chips.map((c) => (
              <span key={c.kind} className={`inline-block px-1.5 py-0.5 rounded text-[11px] ${CHIP_TONE_CLS[c.tone]}`}>
                {c.label}
              </span>
            ))}
          </div>
        )}
        {engineStopped && (
          <div data-testid="kojiro-engine-stopped" className="mt-1.5 inline-block px-2 py-0.5 rounded bg-gray-100 text-gray-600 text-[11px]">
            장 마감/엔진 정지 — 값이 최신이 아닐 수 있습니다(정산 뒤 · 부팅 전 · 휴일)
          </div>
        )}
      </div>

      {/* 2. 대순환 사이클 + 스테이지 분포 */}
      <div data-testid="kojiro-stage-cycle" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-2">
          대순환 스테이지 <span className="text-xs text-gray-400">(1→2→…→6→1 순환 · 후보 분포)</span>
        </h4>
        <div className="flex items-stretch gap-1 overflow-x-auto pb-1">
          {[1, 2, 3, 4, 5, 6].map((s, i) => {
            const meta = STAGE_META[s]
            return (
              <div key={s} className="flex items-center">
                <div className={`min-w-[92px] rounded border px-2 py-1.5 text-center ${meta.tone}`}>
                  <div className="text-sm font-bold">
                    스테이지 {s}
                    <span
                      data-testid={`kojiro-stage-count-${s}`}
                      className="ml-1 inline-block rounded-full bg-white/70 px-1.5 text-xs"
                    >
                      {stageDist[s]}
                    </span>
                  </div>
                  <div className="text-[10px] leading-tight mt-0.5">{meta.arrange}</div>
                  <div className="text-[10px] leading-tight font-medium">{meta.role}</div>
                </div>
                {i < 5 && <span className="px-0.5 text-gray-300">→</span>}
                {i === 5 && <span className="px-0.5 text-amber-500 font-bold" title="6→1 전환 = 신선한 진입">↩</span>}
              </div>
            )
          })}
        </div>
        <div className="mt-1.5 text-[11px] text-gray-500">
          진입 = <b className="text-emerald-700">스테이지 1</b> + 최근{' '}
          <b className="text-amber-700">{freshness !== null ? `${freshness}영업일` : '—'} 6→1 전환</b> ·
          청산 = <b className="text-rose-700">스테이지 3</b> 진입
        </div>
      </div>

      {/* 3. 유니버스 깔때기 — 라우트가 있으면 엔진 단계 이름·조건을 쓴다(폴백 = scan_stats 9단계). */}
      <div data-testid="kojiro-scan-funnel" className="rounded border border-gray-200 p-3">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-gray-700">유니버스 깔때기</h4>
          <span className="text-xs text-violet-600">{scanStats ? `마지막 ${formatKstDateTime(scanStats.last_run_at)}` : '아직 스캔 전'}</span>
        </div>
        {routeFunnel.length > 0 ? (
          <div className="space-y-1">
            {(() => {
              const maxVal = Math.max(1, ...routeFunnel.map((r) => r.survived_count))
              return [...routeFunnel]
                .sort((a, b) => a.step_no - b.step_no)
                .map((row) => {
                  const widthPct = Math.round((row.survived_count / maxVal) * 100)
                  const zero = row.survived_count === 0
                  const isFinal = row.step_no === 99
                  return (
                    <div key={row.step_no} data-testid={`kojiro-funnel-row-${row.step_no}`} className="flex items-center gap-2 text-xs">
                      <span className="w-56 shrink-0 text-gray-600">
                        {row.step_no}. {row.step_name}
                        {row.step_conditions && (
                          <span className="ml-1 text-[10px] text-gray-400">{row.step_conditions}</span>
                        )}
                      </span>
                      <div className="flex-1 bg-gray-100 rounded h-4 relative overflow-hidden">
                        <div
                          className={`h-4 rounded ${zero ? 'bg-rose-200' : isFinal ? 'bg-violet-400' : 'bg-violet-200'}`}
                          style={{ width: `${widthPct}%` }}
                        />
                      </div>
                      <span className={`w-10 text-right font-medium ${zero ? 'text-rose-500' : 'text-gray-700'}`}>{row.survived_count}</span>
                    </div>
                  )
                })
            })()}
          </div>
        ) : scanStats ? (
          <div className="space-y-1">
            {(() => {
              const counts = KOJIRO_STAGES.map((stg) => ({
                ...stg,
                value: num((scanStats as Record<string, unknown>)[stg.key], 0),
              }))
              const maxVal = Math.max(1, ...counts.map((c) => c.value))
              return counts.map((stg, i) => {
                const widthPct = Math.round((stg.value / maxVal) * 100)
                const zero = stg.value === 0
                const isFinal = stg.key === 'final_prepared'
                return (
                  <div key={stg.key} data-testid={`kojiro-funnel-row-${i}`} className="flex items-center gap-2 text-xs">
                    <span className="w-52 shrink-0 text-gray-600">{i + 1}. {stg.label}</span>
                    <div className="flex-1 bg-gray-100 rounded h-4 relative overflow-hidden">
                      <div
                        className={`h-4 rounded ${zero ? 'bg-rose-200' : isFinal ? 'bg-violet-400' : 'bg-violet-200'}`}
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                    <span className={`w-10 text-right font-medium ${zero ? 'text-rose-500' : 'text-gray-700'}`}>{stg.value}</span>
                  </div>
                )
              })
            })()}
          </div>
        ) : (
          <div className="text-xs text-gray-400">아직 스캔 전 — 매일 저녁 21:00 이후 표시</div>
        )}
      </div>

      {/* 4. 후보 종목 그리드 */}
      <div data-testid="kojiro-candidate-grid" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-2">
          후보 종목 <span className="text-xs text-gray-400">({candidateEntries.length}종목 · 스테이지/EMA/ATR밴드)</span>
        </h4>
        {candidateEntries.length === 0 ? (
          <div className="text-xs text-gray-400">후보 없음 (조건 통과 종목 0 또는 스캔 전)</div>
        ) : (
          <ScrollPane>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="text-left py-1 pr-2">종목</th>
                  <th className="text-center py-1 px-1">스테이지</th>
                  <th className="text-left py-1 px-2">EMA 5 / 20 / 40</th>
                  <th className="text-left py-1 px-2 w-40">ATR 변동성 밴드</th>
                  <th className="text-right py-1 pl-2">전일종가</th>
                </tr>
              </thead>
              <tbody>
                {candidateEntries.map(([ticker, t]) => {
                  const prevClose = num(t.prev_close, 0)
                  const atr = num(t.atr, 0)
                  const ratio = t.atr_ratio != null ? num(t.atr_ratio, 0) : (prevClose > 0 ? atr / prevClose : 0)
                  const posPct = hasBand
                    ? Math.min(100, Math.max(0, ((ratio - bandMin) / (bandMax - bandMin)) * 100))
                    : 0
                  const nearEdge = hasBand && (ratio >= bandMax * 0.9 || ratio <= bandMin * 1.1)
                  const aligned = num(t.ema_s, 0) > num(t.ema_m, 0) && num(t.ema_m, 0) > num(t.ema_l, 0)
                  const name = t.name || ticker
                  return (
                    <tr key={ticker} data-testid={`kojiro-candidate-${ticker}`} className="border-b border-gray-100">
                      <td className="py-1 pr-2 font-medium text-gray-800">{name}</td>
                      <td className="py-1 px-1 text-center"><StageBadge stage={num(t.stage, 0)} /></td>
                      <td className="py-1 px-2">
                        <span className={aligned ? 'text-emerald-700' : 'text-gray-500'}>
                          {num(t.ema_s, 0).toLocaleString()} / {num(t.ema_m, 0).toLocaleString()} / {num(t.ema_l, 0).toLocaleString()}
                          {aligned && <span className="ml-1 text-[10px]">정배열</span>}
                        </span>
                      </td>
                      <td className="py-1 px-2">
                        {hasBand ? (
                          <div className="flex items-center gap-1">
                            <div className="flex-1 h-2.5 bg-gray-100 rounded relative">
                              <div className="absolute inset-y-0 left-0 bg-violet-100 rounded" style={{ width: '100%' }} />
                              <div
                                data-testid={`kojiro-band-marker-${ticker}`}
                                className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3 w-1.5 rounded ${nearEdge ? 'bg-amber-500' : 'bg-violet-600'}`}
                                style={{ left: `${posPct}%` }}
                              />
                            </div>
                            <span className={`w-12 text-right ${nearEdge ? 'text-amber-600' : 'text-gray-600'}`}>
                              {(ratio * 100).toFixed(1)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-1 pl-2 text-right text-gray-600">{prevClose.toLocaleString()}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="mt-1 text-[10px] text-gray-400">
              밴드 게이지: {hasBand ? `${(bandMin * 100).toFixed(1)}% ~ ${(bandMax * 100).toFixed(1)}%` : '—'} (양 끝 근접 시 amber)
            </div>
          </ScrollPane>
        )}
      </div>

      {/* 5. 진입 이벤트 / 게이트 */}
      <div data-testid="kojiro-entry-feed" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-1">진입 이벤트</h4>
        <div className="text-[11px] text-gray-500 mb-2">
          매수 창 09:05~09:30 · 갭업 ≥{gapUpPct !== null ? `${gapUpPct}%` : '—'} / 갭다운 ≤{gapDownPct !== null ? `${gapDownPct}%` : '—'} / 장중 붕괴(현재가&lt;시가) 스킵 · 종목당 1회
        </div>
        {buySignals.length === 0 ? (
          <div className="text-xs text-gray-400">{engineStopped ? '엔진 정지 — 매수 신호 모름' : '매수 신호 없음'}</div>
        ) : (
          <ul className="space-y-1">
            {buySignals.slice().reverse().map((sig, i) => {
              const s = sig as unknown as Record<string, unknown>
              return (
                <li key={`${sig.ticker}-${i}`} className="flex items-center gap-2 text-xs">
                  <span className="text-gray-400 w-16">{sig.time}</span>
                  <span className="font-medium text-gray-800">{sig.name || sig.ticker}</span>
                  <StageBadge stage={num(s.stage, 0)} />
                  <span className="text-gray-500">현재가 {num(sig.price, 0).toLocaleString()}</span>
                  <span className="text-gray-400">ATR {num(s.atr, 0).toLocaleString()}</span>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* 6. 보유 종목 방어선 — 실효선 = exit-lines stop_price, 구성 선은 exit-lines entry_atr. */}
      <div data-testid="kojiro-defense-panel" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-1">보유 종목 방어선</h4>
        <div className="text-[11px] text-gray-500 mb-2">
          4중 청산: 고정 {hardStopPct}% backstop · {stopAtr}ATR 하드손절 · 스테이지3 진입 · {trailAtr}ATR 샹들리에 트레일링
        </div>
        {Object.keys(positions).length === 0 ? (
          <div className="text-xs text-gray-400">{engineStopped ? '엔진 정지 — 보유 정보 모름' : '보유 종목 없음'}</div>
        ) : (
          <ScrollPane>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="text-left py-1 pr-2">종목</th>
                  <th className="text-center py-1 px-1">스테이지</th>
                  <th className="text-right py-1 px-2">매수가</th>
                  <th className="text-right py-1 px-2">현재가</th>
                  <th className="text-right py-1 px-2">2ATR 하드</th>
                  <th className="text-right py-1 px-2">2.5ATR 트레일</th>
                  <th className="text-right py-1 px-2">{hardStopPct}% backstop</th>
                  <th className="text-right py-1 pl-2">실효 손절선</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(positions).map(([ticker, pos]) => {
                  const t = targets[ticker]
                  const stage = num(t?.stage, 0)
                  const exitLine = exitLineMap.get(ticker)
                  const entryAtr = exitLine != null ? finiteOrNull(exitLine.entry_atr) : null
                  const buy = num(pos.buy_price, 0)
                  const high = num(pos.high_since_buy, 0) || buy
                  const cur = num(prices[ticker]?.current_price, 0)
                  const hard2 = entryAtr !== null && entryAtr > 0 ? Math.round(buy - stopAtr * entryAtr) : null
                  const trail = entryAtr !== null && entryAtr > 0 ? Math.round(high - trailAtr * entryAtr) : null
                  const backstop = Math.round(buy * (1 + hardStopPct / 100))
                  const effective = exitLine != null ? finiteOrNull(exitLine.stop_price) : null
                  const isActive = (v: number | null) => effective !== null && v !== null && Math.abs(v - effective) <= 1
                  const distPct = cur > 0 && effective !== null ? ((cur - effective) / cur) * 100 : null
                  const stage3 = stage === 3
                  return (
                    <tr key={ticker} data-testid={`kojiro-defense-${ticker}`} className="border-b border-gray-100">
                      <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                      <td className="py-1 px-1 text-center">
                        <StageBadge stage={stage} />
                        {stage3 && <span className="ml-1 text-[10px] text-rose-600 font-semibold">청산</span>}
                      </td>
                      <td className="py-1 px-2 text-right text-gray-600">{buy.toLocaleString()}</td>
                      <td className="py-1 px-2 text-right text-gray-800">{cur > 0 ? cur.toLocaleString() : '—'}</td>
                      <td className={`py-1 px-2 text-right ${isActive(hard2) ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{hard2 !== null ? hard2.toLocaleString() : '—'}</td>
                      <td className={`py-1 px-2 text-right ${isActive(trail) ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{trail !== null ? trail.toLocaleString() : '—'}</td>
                      <td className={`py-1 px-2 text-right ${isActive(backstop) ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{backstop.toLocaleString()}</td>
                      <td className="py-1 pl-2 text-right text-gray-700">
                        {effective !== null ? effective.toLocaleString() : '—'}
                        {distPct != null && <span className="ml-1 text-[10px] text-gray-400">({distPct.toFixed(1)}%)</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="mt-1 text-[10px] text-gray-400">실효 손절선 = 엔진 값(balance/exit-lines). 같은 값의 구성 선만 강조. 스테이지3 = 추세종료 청산.</div>
          </ScrollPane>
        )}
      </div>
    </div>
  )
}
