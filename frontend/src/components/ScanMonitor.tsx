import { useState } from 'react'
import { useTradingStatus } from '../contexts/TradingStatusContext'
import { getStrategyColor } from '../types/strategy'
import type { BuySignal, ScanStats } from '../types/trading'
import { getKstMinutes } from '../utils/stale-context'

interface BoardTarget {
  open_price: number
  target_price: number
  target_offset: number
  confirmed: boolean
}

interface BreakoutTarget {
  k: number
  // backwards-compat (첫 확정 보드값)
  target_price: number
  open_price: number
  target_offset: number
  // Phase 5 보드별 분리
  boards?: Record<string, BoardTarget>
  open_confirmed?: boolean | Record<string, boolean>
  limit_up_reached?: boolean
}

// 보드별 시각 메타 — chip 색상 + 한글 라벨
const BOARD_META: Record<string, { label: string; chipCls: string }> = {
  main: { label: '메인', chipCls: 'bg-blue-100 text-blue-700' },
  pre_nxt: { label: '프리', chipCls: 'bg-teal-100 text-teal-700' },
  post_nxt: { label: '애프터', chipCls: 'bg-violet-100 text-violet-700' },
  krx_open: { label: '동시호가', chipCls: 'bg-sky-100 text-sky-700' },
  krx_after: { label: '시간외', chipCls: 'bg-purple-100 text-purple-700' },
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

// 사이클 21 (2026-05-20) — VB/LTV/momentum/BFB/VCP 단계별 깔때기.
// donchian 의 SWING_STAGES 와 동일 패턴 — ScanFunnelBars 컴포넌트로 5 전략 재사용.

const VB_STAGES: Array<{ key: string; label: string }> = [
  { key: 'universe_candidates', label: '유니버스 후보 (blng 0/1/3 합집합)' },
  { key: 'price_filtered', label: '가격/상장주식수 필수값 > 0' },
  { key: 'mcap_pass', label: '시총 ≥ 1,000억' },
  { key: 'trade_amount_pass', label: '거래대금 ≥ 200억' },
  { key: 'universe_filtered', label: '유니버스 확정 (시총+거래대금)' },
  { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
  { key: 'k_value_computed', label: 'K값/Target 계산 완료' },
  { key: 'final_prepared', label: '최종 prepared' },
]

const LTV_STAGES: Array<{ key: string; label: string }> = [
  { key: 'universe_candidates', label: '유니버스 후보 (blng 0/1/3 합집합)' },
  { key: 'price_filtered', label: '가격/상장주식수 필수값 > 0' },
  { key: 'mcap_pass', label: '시총 ≥ 1,000억' },
  { key: 'trade_amount_pass', label: '거래대금 ≥ 200억' },
  { key: 'universe_filtered', label: '유니버스 확정' },
  { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
  { key: 'consecutive_limit_pass', label: '연속상한가 제외 통과' },
  { key: 'k_value_computed', label: 'K값/Target 계산' },
  { key: 'final_prepared', label: '최종 prepared' },
]

const MOMENTUM_STAGES: Array<{ key: string; label: string }> = [
  { key: 'universe_candidates', label: '등락률 순위 응답 (raw)' },
  { key: 'rate_pass', label: '등락률 ≥ 15% 통과' },
  { key: 'mcap_pass', label: '시총 ≥ 1,000억' },
  { key: 'trade_amount_pass', label: '거래대금 ≥ 200억' },
  { key: 'limit_up_excluded', label: '상한가 (+30%) 제외' },
  { key: 'final_prepared', label: '최종 후보' },
]

const BFB_STAGES: Array<{ key: string; label: string }> = [
  { key: 'universe_candidates', label: '유니버스 후보' },
  { key: 'universe_filtered', label: '유니버스 필터 통과' },
  { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
  { key: 'pole_pass', label: '폴(Pole) 자동 검출' },
  { key: 'flag_pass', label: '플래그(Flag) 자동 검출' },
  { key: 'volume_contraction_pass', label: '거래량 수축' },
  { key: 'atr_pass', label: 'ATR(14) > 0' },
  { key: 'final_prepared', label: '최종 prepared' },
]

const VCP_STAGES: Array<{ key: string; label: string }> = [
  // 사이클 39 (2026-05-22) — 백엔드 `_scan_stats` 키 매핑 시정.
  // 기존 `trend_pass`/`contraction_pass` 는 백엔드 키와 불일치 → 항상 0 표시 결함.
  // 백엔드 vcp_breakout.py `_empty_scan_stats` 정합: trend_filter_pass / base_pass / pullback_pass.
  // 5/22 사용자 보고 "EMA 0 인데 base 9" 가 단계 순서 결함이 아닌 프론트 키 매핑 결함이었음.
  { key: 'universe_candidates', label: '코스피200+코스닥150 합집합' },
  { key: 'universe_filtered', label: '시총 ≥ 1,000억' },
  { key: 'candle_fetch_ok', label: '일봉 fetch + 추세필터' },
  { key: 'trend_filter_pass', label: '50/150/200 EMA 정렬' },
  { key: 'base_pass', label: '베이스 자동 검출' },
  { key: 'pullback_pass', label: 'Pullback 점진 수축' },
  { key: 'volume_contraction_pass', label: '거래량 수축' },
  { key: 'final_prepared', label: '최종 prepared' },
]

const FUNNEL_THEME = {
  emerald: { bar: 'bg-emerald-200', final: 'bg-emerald-400', accent: 'text-emerald-700' },
  teal: { bar: 'bg-teal-200', final: 'bg-teal-400', accent: 'text-teal-700' },
  indigo: { bar: 'bg-indigo-200', final: 'bg-indigo-400', accent: 'text-indigo-700' },
} as const

type FunnelTheme = keyof typeof FUNNEL_THEME

interface ScanFunnelBarsProps {
  testId: string
  title: string
  stages: ReadonlyArray<{ key: string; label: string }>
  stats: Record<string, unknown> | null | undefined
  theme?: FunnelTheme
}

function ScanFunnelBars({ testId, title, stages, stats, theme = 'teal' }: ScanFunnelBarsProps) {
  const themeMeta = FUNNEL_THEME[theme]
  if (!stats) {
    return (
      <div
        data-testid={testId}
        className="border border-gray-200 rounded p-3 mb-3"
      >
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-gray-700">{title}</h4>
          <span className="text-xs text-gray-400">아직 스캔 전</span>
        </div>
      </div>
    )
  }
  const counts = stages.map((stg) => ({
    ...stg,
    value: typeof stats[stg.key] === 'number' ? (stats[stg.key] as number) : 0,
  }))
  const maxVal = Math.max(1, ...counts.map((c) => c.value))
  const lastRun = (stats.last_run_at as string | undefined) ?? null
  return (
    <div
      data-testid={testId}
      className="border border-gray-200 rounded p-3 mb-3"
    >
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-medium text-gray-700">{title}</h4>
        {lastRun && (
          <span className={`text-xs ${themeMeta.accent}`}>
            마지막 {formatRunAt(lastRun)}
          </span>
        )}
      </div>
      <div className="space-y-1">
        {counts.map((stg, i) => {
          const widthPct = Math.round((stg.value / maxVal) * 100)
          const isZero = stg.value === 0
          const isFinal = stg.key === 'final_prepared'
          const barColor = isZero
            ? 'bg-rose-200'
            : isFinal
              ? themeMeta.final
              : themeMeta.bar
          return (
            <div key={stg.key} className="flex items-center gap-2 text-xs">
              <div className="w-7 text-right text-gray-400 font-mono">{i + 1}.</div>
              <div className="flex-1">
                <div className="flex items-baseline justify-between mb-0.5">
                  <span className={isZero ? 'text-rose-600 font-medium' : 'text-gray-700'}>
                    {stg.label}
                  </span>
                  <span
                    className={`font-mono font-medium ${
                      isZero ? 'text-rose-600' : isFinal ? themeMeta.accent : 'text-gray-700'
                    }`}
                  >
                    {stg.value}
                  </span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${barColor} transition-all`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function formatRunAt(iso?: string | null): string {
  if (!iso) return '-'
  try {
    // 시각 표시 KST 강제 (frontend/CLAUDE.md 컨벤션) — timeZone 누락 시 비-KST 환경
    // (도커 UTC / 해외) 에서 07:48 boot 이 "0:48" 등으로 오표시됨
    return new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })
  } catch {
    return iso
  }
}

// 사이클 21 — getKstMinutes 는 utils/stale-context 로 이전 (재사용).

const SWING_ENTRY_START_MIN = 9 * 60 + 5    // 09:05
const SWING_ENTRY_END_MIN = 9 * 60 + 30     // 09:30 (exclusive)
const SWING_GAP_SKIP_PCT = 3.0              // donchian DEFAULT_PARAMS.gap_skip_threshold

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  idle: { label: '대기', color: 'bg-gray-100 text-gray-700' },
  booting: { label: '기동 중', color: 'bg-yellow-100 text-yellow-700' },
  presubscribe_wait: { label: '사전 구독 대기', color: 'bg-sky-100 text-sky-700' },
  pre_nxt_wait: { label: 'NXT 프리 대기', color: 'bg-sky-100 text-sky-700' },
  next_day_clear: { label: '익일 청산', color: 'bg-orange-100 text-orange-700' },
  pre_nxt_trading: { label: 'NXT 프리 매매', color: 'bg-teal-100 text-teal-700' },
  vb_trading: { label: '돌파 매매 중', color: 'bg-teal-100 text-teal-700' },
  main_trading: { label: 'KRX 메인 매매', color: 'bg-green-100 text-green-700' },
  scanning: { label: '종목 스캔', color: 'bg-blue-100 text-blue-700' },
  trading: { label: '매매 중', color: 'bg-green-100 text-green-700' },
  buy_stopped: { label: '매수 중단', color: 'bg-amber-100 text-amber-700' },
  krx_main_stopped: { label: 'KRX 메인 매수 중단', color: 'bg-amber-100 text-amber-700' },
  post_nxt_trading: { label: 'NXT 애프터 매매', color: 'bg-violet-100 text-violet-700' },
  post_nxt_stopped: { label: 'NXT 애프터 매수 중단', color: 'bg-amber-100 text-amber-700' },
  recommending: { label: 'AI자문 생성', color: 'bg-fuchsia-100 text-fuchsia-700' },
  closing: { label: '장 마감', color: 'bg-purple-100 text-purple-700' },
  settling: { label: '정산 중', color: 'bg-indigo-100 text-indigo-700' },
  log_analysis: { label: '로그 분석', color: 'bg-indigo-100 text-indigo-700' },
}

// 사이클 13 (2026-05-18): BFB / VCP 신규 전략 가시화. 둘 다 MAIN only 단일 보드.
// VB/LTV 와 동일한 isBreakout 분기로 운영시간 안내 + 타겟 가격 테이블 재사용.
const BREAKOUT_KEYS = [
  'volatility_breakout',
  'long_tail_volatility',
  'bull_flag_breakout',
  'vcp_breakout',
] as const
const BREAKOUT_LABELS: Record<string, string> = {
  volatility_breakout: '변동성 돌파',
  long_tail_volatility: '롱테일 변동성',
  bull_flag_breakout: '눌림목 돌파',
  vcp_breakout: 'VCP 변동성 수축',
}

// 사이클 21 — getStaleContextByKstMinutes / STALE_CONTEXT_META 는
// utils/stale-context 로 이전. ScanMonitor 는 더 이상 끊김 영역을 노출하지 않음
// (KisAccountPoolCard 로 통합 — 인프라 상태는 한 곳에서만).

interface Props {
  selectedStrategy: string
}

export default function ScanMonitor({ selectedStrategy }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [swingExpanded, setSwingExpanded] = useState(false)
  const [swingHelpOpen, setSwingHelpOpen] = useState(false)

  const { data: status } = useTradingStatus()

  // 사이클 21 — 구독 인프라 (tick_coverage / stale-context-label / 끊김 종목 펼치기 /
  // 수동 재구독) 영역은 KisAccountPoolCard 로 이전됨. ScanMonitor 는 필터링 가시성에 집중.

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

  // KST 기준 활성 보드 (시각 기반 — SessionTracker와 동일 매핑)
  const activeBoards = (() => {
    const fmt = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
    })
    const parts = fmt.formatToParts(new Date())
    const h = Number(parts.find((p) => p.type === 'hour')?.value ?? '0')
    const m = Number(parts.find((p) => p.type === 'minute')?.value ?? '0')
    const t = h * 60 + m
    const result: { code: string; label: string; color: string }[] = []
    if (t >= 8 * 60 && t < 9 * 60) result.push({ code: 'pre_nxt', label: 'NXT 프리', color: 'bg-teal-100 text-teal-700' })
    if (t >= 8 * 60 + 30 && t < 9 * 60) result.push({ code: 'krx_open', label: 'KRX 동시호가', color: 'bg-sky-100 text-sky-700' })
    if (t >= 9 * 60 && t < 15 * 60 + 30) result.push({ code: 'main', label: 'KRX 메인', color: 'bg-green-100 text-green-700' })
    if (t >= 15 * 60 + 30 && t < 18 * 60) result.push({ code: 'krx_after', label: 'KRX 시간외', color: 'bg-purple-100 text-purple-700' })
    if (t >= 15 * 60 + 30 && t < 20 * 60) result.push({ code: 'post_nxt', label: 'NXT 애프터', color: 'bg-violet-100 text-violet-700' })
    return result
  })()

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold text-gray-900">조건검색 현황</h3>
        <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${phaseInfo.color}`}>
          {phaseInfo.label}
        </span>
      </div>
      {/* 활성 보드 배지 — KRX/NXT 어느 보드가 지금 매매 가능한지 즉시 식별 */}
      <div className="flex items-center gap-1.5 mb-4 flex-wrap">
        <span className="text-xs text-gray-500">활성 보드:</span>
        {activeBoards.length > 0 ? (
          activeBoards.map((b) => (
            <span key={b.code} className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${b.color}`}>
              {b.label}
            </span>
          ))
        ) : (
          <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">
            장 외 (08:00~20:00 외)
          </span>
        )}
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
            <div className="grid grid-cols-3 gap-3 mb-2">
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

            {/* 사이클 21 (2026-05-20) — tick_coverage 인프라 영역 제거.
                stale 카운트/배지/진행바/끊김 종목 펼치기/수동 재구독은 모두
                KisAccountPoolCard 로 통합됨 (Dashboard MarketRegimeCard 직하).
                ScanMonitor 는 필터링 가시성에 집중 — 전략별 깔때기, 보드별 타겟가, 매수 신호. */}

            {/* 전체 탭: 돌파 전략별 카운트 */}
            {isAll && BREAKOUT_KEYS.map((k) => {
              const c = breakoutCounts[k]
              if (!c) return null
              return (
                <div key={k} className="mb-2 px-2 py-1.5 bg-indigo-50 rounded text-xs text-indigo-700">
                  {BREAKOUT_LABELS[k]} 스캔: {c}종목 (NXT 프리 08:00 / KRX 메인 09:00:05 / NXT 애프터 15:30~ 매매)
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

            {/* 돌파 탭(VB/LTV): 운영시각 안내 — NXT 통합 (보드별 분리) */}
            {isBreakout && (
              <div className="mb-3 px-2 py-1.5 bg-teal-50 rounded text-xs text-teal-700 flex items-center justify-between">
                <span>매매 시간: NXT 프리 08:00 / KRX 메인 09:00:05 / NXT 애프터 15:30~19:50 (보드별 K값 분리)</span>
                <span className="text-teal-500">
                  {selectedBreakoutCount > 0 ? `${selectedBreakoutCount}종목 감시 중` : ''}
                </span>
              </div>
            )}

            {/* 사이클 21 — 5 전략 깔때기 시각화 (donchian SWING_STAGES 패턴 동일 적용).
                백엔드 _scan_stats 기반. 미반영 시점 fallback "아직 스캔 전" 표시. */}
            {selectedStrategy === 'volatility_breakout' && (
              <ScanFunnelBars
                testId="vb-scan-funnel"
                title="변동성 돌파 — 조건 통과 단계별 후보 수"
                stages={VB_STAGES}
                stats={strategies['volatility_breakout']?.scan_stats as Record<string, unknown> | null}
                theme="teal"
              />
            )}
            {selectedStrategy === 'long_tail_volatility' && (
              <ScanFunnelBars
                testId="ltv-scan-funnel"
                title="롱테일 변동성 — 조건 통과 단계별 후보 수"
                stages={LTV_STAGES}
                stats={strategies['long_tail_volatility']?.scan_stats as Record<string, unknown> | null}
                theme="teal"
              />
            )}
            {selectedStrategy === 'bull_flag_breakout' && (
              <ScanFunnelBars
                testId="bfb-scan-funnel"
                title="눌림목 돌파 — 조건 통과 단계별 후보 수"
                stages={BFB_STAGES}
                stats={strategies['bull_flag_breakout']?.scan_stats as Record<string, unknown> | null}
                theme="indigo"
              />
            )}
            {selectedStrategy === 'vcp_breakout' && (
              <ScanFunnelBars
                testId="vcp-scan-funnel"
                title="VCP 변동성 수축 — 조건 통과 단계별 후보 수"
                stages={VCP_STAGES}
                stats={strategies['vcp_breakout']?.scan_stats as Record<string, unknown> | null}
                theme="indigo"
              />
            )}
            {selectedStrategy === 'momentum' && (
              <ScanFunnelBars
                testId="momentum-scan-funnel"
                title="상한가 모멘텀 — 조건 통과 단계별 후보 수"
                stages={MOMENTUM_STAGES}
                stats={strategies['momentum']?.scan_stats as Record<string, unknown> | null}
                theme="emerald"
              />
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
                    <div className="flex items-center justify-between mb-1.5 gap-2">
                      <div className="font-medium">진입 케이스 — 다음 영업일 09:05~09:30 KST</div>
                      <button
                        onClick={() => setSwingHelpOpen((v) => !v)}
                        className={
                          swingHelpOpen
                            ? 'shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-white text-emerald-700 border border-emerald-300 hover:bg-emerald-50 transition'
                            : 'shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-600 text-white shadow-sm ring-1 ring-emerald-700/20 hover:bg-emerald-700 transition animate-pulse'
                        }
                        aria-expanded={swingHelpOpen}
                        title={swingHelpOpen ? '도움말 접기' : '전략을 처음 보시나요? 도움말을 확인하세요'}
                      >
                        {swingHelpOpen ? (
                          <>
                            <span aria-hidden>▲</span>
                            <span>도움말 접기</span>
                          </>
                        ) : (
                          <>
                            <span aria-hidden>❓</span>
                            <span>전략 자세히 보기</span>
                          </>
                        )}
                      </button>
                    </div>
                    <ul className="space-y-0.5 text-emerald-700 list-disc pl-4">
                      <li>전일 종가가 <b>20일 신고가 돌파</b> + 60일 EMA 우상향 + 종가&gt;EMA + 거래대금 ≥ 20일평균×1.5 (prepare 단계 통과)</li>
                      <li>익일 09:05~09:30 사이 시장가 매수 — <b>1종목당 1회</b>만 시도</li>
                      <li>시가가 전일 종가 대비 <b>+{gapSkipPct.toFixed(0)}%↑ 갭상승</b>이면 스킵 (추격 방지)</li>
                      <li>청산: ATR(14)×2 트레일링 + 하드 손절 -7% (시간 청산 없음, 멀티데이 보유)</li>
                    </ul>
                    <div className="mt-1 text-emerald-500">마지막 스캔 {formatRunAt(lastRunAt)}</div>
                  </div>

                  {swingHelpOpen && (
                    <div className="mb-3 px-4 py-3 bg-white border border-emerald-200 rounded text-xs text-gray-700 space-y-3 leading-relaxed">
                      <div>
                        <div className="font-semibold text-emerald-700 mb-1">한 줄 요약</div>
                        <p>최근 20일 동안 가장 비싸진 종목을 다음 날 시초가에 사서, 추세가 꺾이거나 너무 떨어지면 파는 추세추종 전략. 며칠~몇 주 들고 가는 멀티데이 보유.</p>
                      </div>

                      <div>
                        <div className="font-semibold text-emerald-700 mb-1">1. 진입 — 왜 매수하는가</div>
                        <p className="mb-1">장 마감 후 다음 3가지를 모두 만족하는 종목만 "내일 살 후보"로 등록합니다.</p>
                        <table className="w-full border border-gray-200 mb-1">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="text-left px-2 py-1 font-medium">조건</th>
                              <th className="text-left px-2 py-1 font-medium">의미 (쉬운 표현)</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            <tr>
                              <td className="px-2 py-1">어제 종가 &gt; 그 이전 20일 최고가</td>
                              <td className="px-2 py-1">20일 통틀어 가장 비싸졌다 = 새 신고가</td>
                            </tr>
                            <tr>
                              <td className="px-2 py-1">60일 평균선이 우상향 + 어제 종가 &gt; 60일 평균</td>
                              <td className="px-2 py-1">장기 추세가 살아있다</td>
                            </tr>
                            <tr>
                              <td className="px-2 py-1">어제 거래대금이 20일 평균의 1.5배↑</td>
                              <td className="px-2 py-1">사람들이 거래에 몰리기 시작했다</td>
                            </tr>
                          </tbody>
                        </table>
                        <p>세 조건 모두 통과한 종목이 다음 날 후보. <b>다음 영업일 09:05~09:30 사이 시장가로 1주문</b> (종목당 1회).</p>
                      </div>

                      <div>
                        <div className="font-semibold text-emerald-700 mb-1">2. 갭률(Gap Rate)이란?</div>
                        <p className="mb-1 font-mono text-emerald-700">
                          갭률 = (오늘 시가 − 어제 종가) ÷ 어제 종가 × 100%
                        </p>
                        <p className="mb-1">쉽게 말해 "어제 종가에서 오늘 시가까지 얼마나 점프했는지" — 시초가에서 미리 띄워서 출발한 비율.</p>
                        <table className="w-full border border-gray-200 mb-1">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="text-left px-2 py-1 font-medium">갭률</th>
                              <th className="text-left px-2 py-1 font-medium">의미</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            <tr><td className="px-2 py-1">+1%</td><td className="px-2 py-1">어제 종가보다 1% 비싸게 시작</td></tr>
                            <tr><td className="px-2 py-1">-2%</td><td className="px-2 py-1">어제 종가보다 2% 싸게 시작</td></tr>
                            <tr className="bg-amber-50">
                              <td className="px-2 py-1 font-medium">+{gapSkipPct.toFixed(0)}%↑</td>
                              <td className="px-2 py-1 font-medium">너무 많이 띄워 출발 → 진입 스킵</td>
                            </tr>
                          </tbody>
                        </table>
                        <p>왜 +{gapSkipPct.toFixed(0)}% 이상이면 스킵? 신고가 돌파 종목이 다음 날 갭상승까지 크면 좋은 진입가가 이미 빠져버린 상태. 그 시점에 추격 매수하면 곧바로 조정 받을 위험이 큼 — "너무 비싸게 사는 위험"을 차단하는 안전장치.</p>
                      </div>

                      <div>
                        <div className="font-semibold text-emerald-700 mb-1">3. 청산 — 언제 파는가</div>
                        <p className="mb-2">donchian은 추세 끝까지 따라가는 전략이라 정해진 청산 시간이 없습니다(VB는 KRX 메인 15:20 강제 청산—POST_NXT 활성 시 19:50까지 보유, momentum은 익일 NXT 프리 08:00 청산이지만 donchian은 모두 해당 없음). 두 가지 중 하나만 맞으면 매도.</p>

                        <div className="mb-2">
                          <div className="font-medium mb-0.5">A. ATR 트레일링 스탑 (= Chandelier Exit)</div>
                          <ul className="list-disc pl-5 space-y-0.5">
                            <li>기준선 = <b>매수 후 최고가 − ATR(14) × 2</b></li>
                            <li>주가가 오르면 기준선도 따라 올라감 (말 그대로 "끌고 가는" stop)</li>
                            <li>주가가 떨어져 기준선 아래로 내려가면 매도 → "추세가 꺾였다" 신호</li>
                            <li><b>ATR(Average True Range)</b>: 그 종목 최근 14일의 일평균 진폭. 변동성 큰 종목은 stop이 멀리, 작은 종목은 가까이 — 종목 특성 자동 반영</li>
                            <li>예: 매수 후 고점 30만원, ATR 5천 → 기준선 = 30만 − 1만 = 29만. 28.9만 찍으면 매도</li>
                          </ul>
                        </div>

                        <div className="mb-2">
                          <div className="font-medium mb-0.5">B. 하드 손절 (-7%)</div>
                          <ul className="list-disc pl-5 space-y-0.5">
                            <li>매수가 대비 7% 손실에 도달하면 트레일링 무관하게 <b>즉시 매도</b></li>
                            <li>최악의 경우 손실을 7%로 한정하는 안전장치</li>
                          </ul>
                        </div>

                        <div>
                          <div className="font-medium mb-0.5">시간 청산 없음</div>
                          <ul className="list-disc pl-5 space-y-0.5">
                            <li>추세가 살아있으면 며칠이든 몇 주든 그대로 보유 (평균 5~15 영업일)</li>
                          </ul>
                        </div>
                      </div>

                      <div>
                        <div className="font-semibold text-emerald-700 mb-1">4. 화면 컬럼이 뜻하는 것</div>
                        <table className="w-full border border-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="text-left px-2 py-1 font-medium">컬럼</th>
                              <th className="text-left px-2 py-1 font-medium">의미</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            <tr><td className="px-2 py-1 font-mono">20일 신고가</td><td className="px-2 py-1">진입 기준이 된 가격 (어제 종가가 이 위로 뚫고 올라온 것)</td></tr>
                            <tr><td className="px-2 py-1 font-mono">EMA60</td><td className="px-2 py-1">60일 지수이동평균선 (장기 추세). 종가가 이 위면 추세 살아있음</td></tr>
                            <tr><td className="px-2 py-1 font-mono">ATR(14)</td><td className="px-2 py-1">14일 평균 진폭. 트레일링 stop 거리(×2) 산정 기준</td></tr>
                            <tr><td className="px-2 py-1 font-mono">갭률</td><td className="px-2 py-1">시초가가 어제 종가 대비 얼마나 점프했는지 (+{gapSkipPct.toFixed(0)}%↑면 스킵)</td></tr>
                            <tr><td className="px-2 py-1 font-mono">진입 상태</td><td className="px-2 py-1">보유 중 / 진입 대기 / 갭 스킵 / 장 시작 전 / 진입 시간 종료</td></tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

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
              // 활성 보드 자동 결정 (PR-G P3, 2026-05-15):
              // 1. 백엔드 응답 boards keys 가 1개면 그 키를 자동 활성 보드로 결정
              //    — 시각 매핑 무관, 백엔드 의도 우선 (서버가 어느 보드 데이터를 보내는지가 진실)
              // 2. boards keys 가 여러 개면 KST 시각 매핑 (기존: main > post_nxt > pre_nxt)
              // 3. boards 빈 dict 또는 fallback 시에도 KST 시각 매핑 (기존 동작 보존)
              // 결함 (사용자 화면 KST 19:40): POST_NXT 활성 시간인데 백엔드는 {post_nxt} 만
              // 응답하는데 UI 가 시각 매핑으로 main 시도 → main 데이터 없어 "시가 대기" 종목 22개.
              // 백엔드 응답 단일 키를 1순위로 인정해 자동 전환.
              const activeBoardCode = (() => {
                // 종목 전체에서 사용된 boards 키 합집합 — 백엔드가 어떤 보드를 보내고 있는지 식별
                const respBoardSet = new Set<string>()
                for (const [, t] of targetEntries) {
                  for (const b of Object.keys(t.boards ?? {})) respBoardSet.add(b)
                }
                // 응답이 단일 보드만 포함 → 자동 그 보드 선택 (시각 무관)
                if (respBoardSet.size === 1) {
                  return Array.from(respBoardSet)[0]
                }
                // 응답이 여러 보드 또는 빈 dict → KST 시각 매핑 fallback
                const codes = activeBoards.map((b) => b.code)
                for (const c of ['main', 'post_nxt', 'pre_nxt']) {
                  if (codes.includes(c)) return c
                }
                return null
              })()
              // 어떤 종목이든 사용된 보드 키 합집합 — 컬럼 헤더용
              const usedBoards = (() => {
                const set = new Set<string>()
                for (const [, t] of targetEntries) {
                  for (const b of Object.keys(t.boards ?? {})) set.add(b)
                }
                if (set.size === 0) set.add('main') // backwards-compat
                return ['main', 'pre_nxt', 'post_nxt'].filter((b) => set.has(b))
              })()
              return (
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-medium text-gray-700">
                      타겟 가격 ({targetEntries.length}종목)
                    </h4>
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <span className="text-gray-500">보드별 시가/타겟가:</span>
                      {usedBoards.map((b) => (
                        <span
                          key={b}
                          className={`px-1.5 py-0.5 rounded ${BOARD_META[b]?.chipCls ?? 'bg-gray-100 text-gray-600'} ${
                            b === activeBoardCode ? 'ring-1 ring-offset-1 ring-current' : ''
                          }`}
                        >
                          {BOARD_META[b]?.label ?? b}
                          {b === activeBoardCode && ' ●'}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-1 pr-2">종목</th>
                          <th className="pb-1 pr-2 text-right">K값</th>
                          <th className="pb-1 pr-2 text-right">시가 (보드별)</th>
                          <th className="pb-1 pr-2 text-right">타겟가 (보드별)</th>
                          <th className="pb-1 pr-2 text-right">현재가</th>
                          <th className="pb-1 text-center">상태</th>
                        </tr>
                      </thead>
                      <tbody>
                        {targetEntries
                          .sort(([, a], [, b]) => {
                            // 활성 보드의 target_price 우선 정렬, 없으면 top-level fallback
                            const aTarget = (activeBoardCode && a.boards?.[activeBoardCode]?.target_price) || a.target_price || 0
                            const bTarget = (activeBoardCode && b.boards?.[activeBoardCode]?.target_price) || b.target_price || 0
                            const aConfirmed = activeBoardCode
                              ? !!a.boards?.[activeBoardCode]?.confirmed
                              : !!a.open_confirmed
                            const bConfirmed = activeBoardCode
                              ? !!b.boards?.[activeBoardCode]?.confirmed
                              : !!b.open_confirmed
                            if (aConfirmed !== bConfirmed) return aConfirmed ? -1 : 1
                            return bTarget - aTarget
                          })
                          .map(([ticker, t]) => {
                            const name = scan?.ticker_names?.[ticker] ?? ''
                            const curPrice = scan?.ticker_prices?.[ticker]?.current_price ?? 0
                            // 활성 보드의 타겟가로 pct 계산 (없으면 top-level)
                            const activeTarget = activeBoardCode
                              ? (t.boards?.[activeBoardCode]?.target_price ?? 0) || t.target_price
                              : t.target_price
                            const pct = activeTarget > 0 && curPrice > 0
                              ? ((curPrice / activeTarget - 1) * 100).toFixed(1)
                              : null
                            const nearTarget = pct !== null && parseFloat(pct) >= -2
                            // 보드별 표시할 셀 컨텐츠 (활성 보드 필터링 — 2026-05-13 작업 1):
                            // - boards 비지 않음 → 그대로 (백엔드가 활성 보드만 보냄)
                            // - boards 빈 dict + activeBoardCode 있음 → backwards-compat 단일 row
                            // - boards 빈 dict + activeBoardCode 없음(장 외) → row 미렌더 (null 반환)
                            const boardRows = (() => {
                              const rows: { board: string; openPrice: number; targetPrice: number; confirmed: boolean }[] = []
                              if (t.boards && Object.keys(t.boards).length > 0) {
                                for (const b of usedBoards) {
                                  const info = t.boards[b]
                                  if (!info) continue
                                  rows.push({
                                    board: b,
                                    openPrice: info.open_price,
                                    targetPrice: info.target_price,
                                    confirmed: info.confirmed,
                                  })
                                }
                                return rows
                              }
                              // boards 빈 dict — backwards-compat 분기
                              if (activeBoardCode) {
                                rows.push({
                                  board: activeBoardCode,
                                  openPrice: t.open_price,
                                  targetPrice: t.target_price,
                                  confirmed: typeof t.open_confirmed === 'boolean' ? t.open_confirmed : false,
                                })
                                return rows
                              }
                              // 활성 보드 없음 + boards 빈 dict → row 미렌더
                              return null
                            })()
                            if (boardRows === null) return null
                            return (
                              <tr key={ticker} className={`border-b border-gray-50 ${nearTarget ? 'bg-yellow-50' : ''}`}>
                                <td className="py-1 pr-2 font-medium align-top">
                                  {name ? `${name}(${ticker})` : ticker}
                                </td>
                                <td className="py-1 pr-2 text-right text-gray-600 align-top">{t.k.toFixed(3)}</td>
                                <td className="py-1 pr-2 text-right align-top">
                                  <div className="flex flex-col items-end gap-0.5">
                                    {boardRows.map((row) => {
                                      const meta = BOARD_META[row.board]
                                      const isActive = row.board === activeBoardCode
                                      return (
                                        <div key={row.board} className="flex items-center gap-1">
                                          <span className={`text-[10px] px-1 rounded ${meta?.chipCls ?? 'bg-gray-100 text-gray-600'}`}>
                                            {meta?.label ?? row.board}
                                          </span>
                                          <span className={`tabular-nums ${isActive ? 'font-semibold' : 'text-gray-500'} ${row.confirmed ? '' : 'opacity-50'}`}>
                                            {row.openPrice > 0 ? row.openPrice.toLocaleString() : '-'}
                                          </span>
                                        </div>
                                      )
                                    })}
                                  </div>
                                </td>
                                <td className="py-1 pr-2 text-right align-top">
                                  <div className="flex flex-col items-end gap-0.5">
                                    {boardRows.map((row) => {
                                      const isActive = row.board === activeBoardCode
                                      return (
                                        <span
                                          key={row.board}
                                          className={`tabular-nums ${isActive ? 'font-semibold text-indigo-600' : 'text-indigo-400'} ${row.confirmed ? '' : 'opacity-50'}`}
                                        >
                                          {row.targetPrice > 0 ? row.targetPrice.toLocaleString() : '-'}
                                        </span>
                                      )
                                    })}
                                  </div>
                                </td>
                                <td className="py-1 pr-2 text-right align-top">
                                  {curPrice > 0 ? curPrice.toLocaleString() : '-'}
                                </td>
                                <td className="py-1 text-center align-top">
                                  {(() => {
                                    // 활성 보드 기준 confirmed/target 판정
                                    const activeRow = activeBoardCode
                                      ? boardRows.find((r) => r.board === activeBoardCode)
                                      : boardRows[0]
                                    const confirmed = activeRow?.confirmed ?? false
                                    const targetPrice = activeRow?.targetPrice ?? 0
                                    if (t.limit_up_reached) {
                                      return <span className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-700 font-medium">상한가 모드</span>
                                    }
                                    if (!confirmed) {
                                      return <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-500">시가 대기</span>
                                    }
                                    if (curPrice >= targetPrice && targetPrice > 0) {
                                      // 사이클 18 (2026-05-19, C-2) — 활성 보드 ∩ 전략 tradable_boards 검사.
                                      // 매매 가능 시간대 (교집합 ∋) → 기존 빨강 "돌파".
                                      // 매매 불가 (교집합 ∅) → 회색 "돌파 (대기 — 보드라벨)" — 운영자가
                                      // *왜 매수 안 했는지* UI 만으로 즉시 이해.
                                      const stratBoards: string[] = Array.isArray(strat?.tradable_boards)
                                        ? (strat.tradable_boards as string[])
                                        : []
                                      const activeBoardCodes = activeBoards.map((b) => b.code)
                                      const tradableNow = stratBoards.filter((b) => activeBoardCodes.includes(b))
                                      // tradable_boards 미존재 (백엔드 미반영) → 기존 빨강 "돌파" fallback (안전 회귀)
                                      if (stratBoards.length === 0 || tradableNow.length > 0) {
                                        return <span className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 font-medium">돌파</span>
                                      }
                                      // 매매 불가 시간대 — 매매 가능 보드 안내
                                      const tradableLabels = stratBoards
                                        .map((b) => BOARD_META[b]?.label ?? b)
                                        .join('/')
                                      return (
                                        <span
                                          className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 font-medium"
                                          title={`이 전략은 ${tradableLabels} 에서만 매매. 현재 활성 보드 외.`}
                                        >
                                          돌파 (대기 — {tradableLabels})
                                        </span>
                                      )
                                    }
                                    if (nearTarget) {
                                      return <span className="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700">근접 {pct}%</span>
                                    }
                                    return <span className="px-1.5 py-0.5 rounded text-xs bg-blue-50 text-blue-600">{pct}%</span>
                                  })()}
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
                  <th className="pb-1 pr-2">보드</th>
                  <th className="pb-1 pr-2">종목</th>
                  <th className="pb-1 pr-2 text-right">타겟가</th>
                  <th className="pb-1 pr-2 text-right">체결가</th>
                  <th className="pb-1 text-right">등락률</th>
                </tr>
              </thead>
              <tbody>
                {[...signals].reverse().map((s, i) => {
                  const color = s.strategyKey ? getStrategyColor(s.strategyKey) : null
                  const boardMeta = s.board ? BOARD_META[s.board] : null
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
                      <td className="py-1 pr-2">
                        {boardMeta ? (
                          <span className={`px-1.5 py-0.5 rounded text-[11px] ${boardMeta.chipCls}`}>
                            {boardMeta.label}
                          </span>
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </td>
                      <td className="py-1 pr-2 font-medium">
                        {s.name ? `${s.name}(${s.ticker})` : s.ticker}
                      </td>
                      <td className="py-1 pr-2 text-right text-indigo-600">
                        {s.target_price ? s.target_price.toLocaleString() : '-'}
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
