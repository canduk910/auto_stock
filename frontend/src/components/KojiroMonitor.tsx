// 고지로(kojiro) 대순환 스윙 전용 모니터링 패널 (대시보드 kojiro 탭).
// kojiro 는 enabled=False 다크런치 — 데이터는 매일 저녁 16:20 스캔 기준(실시간 아님).
// 대부분 API 노출값을 렌더하며, ATR 밴드·청산선·스테이지 분포는 클라이언트 계산.
import { useMemo } from 'react'
import type { StrategyInfo, KojiroTarget, TickerPrice } from '../types/trading'

// 대순환 6 스테이지 (EMA 5/20/40 배열). 1→2→3→4→5→6→1 순환.
const STAGE_META: Record<number, { arrange: string; role: string; tone: string }> = {
  1: { arrange: '단기>중기>장기', role: '완전 정배열 · 진입', tone: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  2: { arrange: '중기>단기>장기', role: '상승 후반', tone: 'bg-lime-100 text-lime-800 border-lime-300' },
  3: { arrange: '중기>장기>단기', role: '추세 종료 · 청산', tone: 'bg-rose-100 text-rose-800 border-rose-300' },
  4: { arrange: '장기>중기>단기', role: '완전 역배열', tone: 'bg-gray-100 text-gray-700 border-gray-300' },
  5: { arrange: '장기>단기>중기', role: '하락 후반', tone: 'bg-sky-100 text-sky-800 border-sky-300' },
  6: { arrange: '단기>장기>중기', role: '바닥 반등 초입', tone: 'bg-amber-100 text-amber-800 border-amber-300' },
}

// 유니버스 깔때기 9단계 — kojiro `_empty_scan_stats` 키와 정합.
const KOJIRO_STAGES: Array<{ key: string; label: string }> = [
  { key: 'universe_union', label: '코스피200+코스닥150 합집합' },
  { key: 'universe_candidates', label: '시총+거래대금 컷 통과' },
  { key: 'universe_filtered', label: '유니버스 확정 (ETF/6자리 제외)' },
  { key: 'candle_fetch_ok', label: '일봉 fetch + 전일종가>0 + 워밍업' },
  { key: 'band_pass', label: 'ATR/종가 변동성 밴드 (1.0~4.5%)' },
  { key: 'stage_valid_pass', label: '스테이지 판별 가능 (EMA 동가 제외)' },
  { key: 'stage1_uptrend_pass', label: '스테이지1 + EMA 3선 우상향' },
  { key: 'strict_entry_pass', label: '6→1 전환 인접 + 종가>EMA5' },
  { key: 'final_prepared', label: '최종 후보' },
]

function num(v: unknown, dflt: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : dflt
}

function formatKst(iso?: string | null): string {
  if (!iso) return '-'
  try {
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(new Date(iso))
  } catch {
    return iso
  }
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
}: {
  strategies: Record<string, StrategyInfo>
  tickerPrices?: Record<string, TickerPrice>
}) {
  const kojiro = strategies['kojiro']

  const scanStats = kojiro?.scan_stats ?? null
  const targets = (kojiro?.targets ?? {}) as Record<string, KojiroTarget>
  const params = (kojiro?.params ?? {}) as Record<string, unknown>
  const positions = kojiro?.positions_detail ?? {}
  const buySignals = kojiro?.buy_signals ?? []
  const prices = tickerPrices ?? {}

  const stopAtr = num(params.stop_atr, 2.0)
  const trailAtr = num(params.trail_atr, 2.5)
  const hardStopPct = num(params.hard_stop_pct, -8.0)
  const bandMin = num(params.atr_ratio_min, 0.01)
  const bandMax = num(params.atr_ratio_max, 0.045)

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

  if (!kojiro) {
    return (
      <div data-testid="kojiro-monitor-empty" className="text-sm text-gray-400 py-4 text-center">
        고지로 전략 데이터가 아직 없습니다 (매일 저녁 16:20 스캔 후 표시).
      </div>
    )
  }

  return (
    <div data-testid="kojiro-monitor" className="space-y-4">
      {/* 1. 상태 배너 — enabled 조건부(진실 반영). 활성 시 amber 경고. */}
      <div
        data-testid="kojiro-darklaunch-banner"
        className={`rounded border px-3 py-2 text-xs ${
          kojiro.enabled
            ? 'border-amber-300 bg-amber-50 text-amber-800'
            : 'border-violet-200 bg-violet-50 text-violet-800'
        }`}
      >
        <div className="flex items-center justify-between">
          <span className="font-semibold">
            {kojiro.enabled ? '⚠️ 고지로 대순환 — 활성 (실매매 진행)' : '🔄 고지로 대순환 — 관찰(다크런치) 모드'}
          </span>
          <span className={kojiro.enabled ? 'text-amber-600' : 'text-violet-500'}>
            마지막 스캔 {formatKst(scanStats?.last_run_at)}
          </span>
        </div>
        <div className={`mt-1 ${kojiro.enabled ? 'text-amber-700' : 'text-violet-600'}`}>
          {kojiro.enabled
            ? `실매매 진행 (enabled=true · 비중 ${Math.round((kojiro.weight ?? 0) * 100)}%). 다음 영업일 09:05~09:30 스캔·매수 발생. 데이터는 스캔 시점 기준.`
            : `실매매 없음 (enabled=false · 비중 ${Math.round((kojiro.weight ?? 0) * 100)}%). 데이터는 매일 저녁 16:20 스캔 기준 — 장중 실시간 갱신 아님.`}
        </div>
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
          진입 = <b className="text-emerald-700">스테이지 1</b> + 최근 3영업일 <b className="text-amber-700">6→1 전환</b> ·
          청산 = <b className="text-rose-700">스테이지 3</b> 진입
        </div>
      </div>

      {/* 3. 유니버스 깔때기 */}
      <div data-testid="kojiro-scan-funnel" className="rounded border border-gray-200 p-3">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-gray-700">유니버스 깔때기 (9단계)</h4>
          <span className="text-xs text-violet-600">{scanStats ? `마지막 ${formatKst(scanStats.last_run_at)}` : '아직 스캔 전'}</span>
        </div>
        {scanStats ? (
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
          <div className="text-xs text-gray-400">아직 스캔 전 — 매일 저녁 16:20 이후 표시</div>
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
          <div className="overflow-x-auto">
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
                  const posPct = bandMax > bandMin
                    ? Math.min(100, Math.max(0, ((ratio - bandMin) / (bandMax - bandMin)) * 100))
                    : 0
                  const nearEdge = ratio >= bandMax * 0.9 || ratio <= bandMin * 1.1
                  const aligned = num(t.ema_s, 0) > num(t.ema_m, 0) && num(t.ema_m, 0) > num(t.ema_l, 0)
                  const name = prices[ticker] ? ticker : ticker
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
                      </td>
                      <td className="py-1 pl-2 text-right text-gray-600">{prevClose.toLocaleString()}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="mt-1 text-[10px] text-gray-400">
              밴드 게이지: {(bandMin * 100).toFixed(1)}% ~ {(bandMax * 100).toFixed(1)}% (양 끝 근접 시 amber)
            </div>
          </div>
        )}
      </div>

      {/* 5. 진입 이벤트 / 게이트 */}
      <div data-testid="kojiro-entry-feed" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-1">진입 이벤트</h4>
        <div className="text-[11px] text-gray-500 mb-2">
          매수 창 09:05~09:30 · 갭업 ≥5% / 갭다운 ≤-4% / 장중 붕괴(현재가&lt;시가) 스킵 · 종목당 1회
        </div>
        {buySignals.length === 0 ? (
          <div className="text-xs text-gray-400">매수 신호 없음 (관찰 모드 — 실매매 미발생)</div>
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

      {/* 6. 보유 종목 방어선 */}
      <div data-testid="kojiro-defense-panel" className="rounded border border-gray-200 p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-1">보유 종목 방어선</h4>
        <div className="text-[11px] text-gray-500 mb-2">
          4중 청산: 고정 {hardStopPct}% backstop · {stopAtr}ATR 하드손절 · 스테이지3 진입 · {trailAtr}ATR 샹들리에 트레일링
        </div>
        {Object.keys(positions).length === 0 ? (
          <div className="text-xs text-gray-400">보유 종목 없음 · 관찰 모드</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="text-left py-1 pr-2">종목</th>
                  <th className="text-center py-1 px-1">스테이지</th>
                  <th className="text-right py-1 px-2">매수가</th>
                  <th className="text-right py-1 px-2">현재가</th>
                  <th className="text-right py-1 px-2">2ATR 하드</th>
                  <th className="text-right py-1 px-2">2.5ATR 트레일</th>
                  <th className="text-right py-1 px-2">-8% backstop</th>
                  <th className="text-right py-1 pl-2">활성 방어선</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(positions).map(([ticker, pos]) => {
                  const t = targets[ticker]
                  const atr = num(t?.atr, 0)
                  const stage = num(t?.stage, 0)
                  const buy = num(pos.buy_price, 0)
                  const high = num(pos.high_since_buy, 0) || buy
                  const cur = num(prices[ticker]?.current_price, 0)
                  const hard2 = atr > 0 ? Math.round(buy - stopAtr * atr) : 0
                  const trail = atr > 0 ? Math.round(high - trailAtr * atr) : 0
                  const backstop = Math.round(buy * (1 + hardStopPct / 100))
                  // 활성(binding) = 현재가 아래 방어선 중 가장 높은 값 (가장 먼저 닿음)
                  const lines = [hard2, trail, backstop].filter((v) => v > 0)
                  const effective = lines.length ? Math.max(...lines) : 0
                  const distPct = cur > 0 && effective > 0 ? ((cur - effective) / cur) * 100 : null
                  const stage3 = stage === 3
                  return (
                    <tr key={ticker} data-testid={`kojiro-defense-${ticker}`} className="border-b border-gray-100">
                      <td className="py-1 pr-2 font-medium text-gray-800">{pos.name || ticker}</td>
                      <td className="py-1 px-1 text-center">
                        <StageBadge stage={stage} />
                        {stage3 && <span className="ml-1 text-[10px] text-rose-600 font-semibold">청산</span>}
                      </td>
                      <td className="py-1 px-2 text-right text-gray-600">{buy.toLocaleString()}</td>
                      <td className="py-1 px-2 text-right text-gray-800">{cur > 0 ? cur.toLocaleString() : '-'}</td>
                      <td className={`py-1 px-2 text-right ${effective === hard2 && hard2 > 0 ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{hard2 ? hard2.toLocaleString() : '-'}</td>
                      <td className={`py-1 px-2 text-right ${effective === trail && trail > 0 ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{trail ? trail.toLocaleString() : '-'}</td>
                      <td className={`py-1 px-2 text-right ${effective === backstop ? 'font-semibold text-rose-600' : 'text-gray-500'}`}>{backstop.toLocaleString()}</td>
                      <td className="py-1 pl-2 text-right text-gray-700">
                        {effective > 0 ? effective.toLocaleString() : '-'}
                        {distPct != null && <span className="ml-1 text-[10px] text-gray-400">({distPct >= 0 ? '' : ''}{distPct.toFixed(1)}%)</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="mt-1 text-[10px] text-gray-400">활성 방어선 = 현재가 아래 3선(2ATR/2.5ATR/backstop) 중 가장 높은(먼저 닿는) 값. 스테이지3 = 추세종료 청산.</div>
          </div>
        )}
      </div>
    </div>
  )
}
