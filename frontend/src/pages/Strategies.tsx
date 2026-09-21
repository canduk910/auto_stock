/**
 * 사이클 103 영역 1 — 전략별 손절 임계 가시화 페이지.
 *
 * GET /api/strategies 영역 활용 (params JSONB 포함 영속 확인 완료).
 *
 * 4 임계 표시:
 *   - stop_loss_rate:      손절 임계
 *   - daily_loss_limit:    일일 손실 한도
 *   - trailing_stop_rate:  트레일링 임계
 *   - position_ratio:      종목당 포지션 비율
 *
 * 영속 의무:
 *   - 사이클 65 H3 useQuery retry:1 영속
 *   - 사이클 68 KST 영속 (Intl.DateTimeFormat)
 *   - 사이클 89 한글 친숙 용어 + 사이클 언급 0 영속
 *   - 데이터 부재 시 graceful (params={} → "—")
 *   - 모바일 viewport 375px 정합
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import StrategyParamsEditor from '../components/StrategyParamsEditor'
import type { ApiResponse } from '../types/common'
import { getStrategyColor } from '../types/strategy'
import type { TeRrMetrics } from '../types/strategy'
import { getStrategyTeRr } from '../api/strategies'
import { pnlColorClass as profitColorClass } from '../utils/pnlColor'
import ScrollPane from '../components/ScrollPane'

// 전략 응답 타입 — GET /api/strategies 영역 정합
interface StrategyStatus {
  key?: string         // strategies dict의 키 (route 응답 형식에 따라 다름)
  name: string
  enabled: boolean
  weight: number
  params: Record<string, number | string | string[] | null | undefined>
  total_investment: number
  invested_amount?: number
  min_weight?: number
  positions?: number
  pending_buys?: number
}

interface StrategiesResponse {
  strategies: Record<string, StrategyStatus> | StrategyStatus[]
}

// 백분율 포맷 헬퍼
function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  const n = Number(val)
  if (isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

// 임계 색상 — 손절/손실은 파랑(손실색), 포지션비율은 중립
function thresholdColor(key: string, val: number | null | undefined): string {
  if (val === null || val === undefined) return 'text-gray-400'
  const n = Number(val)
  if (isNaN(n)) return 'text-gray-400'
  if (key === 'position_ratio') return 'text-gray-700'
  // 손절/손실 임계 — 음수면 손실색(파랑), 양수면 이익색(빨강)
  return n < 0 ? 'text-blue-600' : 'text-red-600'
}

const PARAM_LABELS: Record<string, string> = {
  stop_loss_rate: '손절 임계',
  daily_loss_limit: '일일 손실 한도',
  trailing_stop_rate: '트레일링 임계',
  position_ratio: '종목당 비율',
}

const THRESHOLD_KEYS = [
  'stop_loss_rate',
  'daily_loss_limit',
  'trailing_stop_rate',
  'position_ratio',
] as const

export type ThresholdKey = typeof THRESHOLD_KEYS[number]

// ── 사이클 F — TE(트레이딩 예지치)/RR(손익비) 성과 섹션 ──────────────────
// 명세: _workspace/red/_behaviors_cycleF_te_rr_20260802.md §F-FE1~F-FE6
// 자문: _workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md §209-234
// 관찰 전용 — 매매 hot path 무접촉.

function formatSignedPercent(val: number | null | undefined, digits = 1): string {
  if (val === null || val === undefined || isNaN(val)) return '—'
  return `${val > 0 ? '+' : ''}${val.toFixed(digits)}%`
}

function formatKrwSigned(val: number): string {
  const sign = val > 0 ? '+' : ''
  return `${sign}${Math.round(val).toLocaleString('ko-KR')}원`
}

const VERDICT_LABELS: Record<TeRrMetrics['verdict'], string> = {
  superior: '우위',
  inferior: '열위',
  undecided: '판정 유보',
  flat: '보합',
}

function verdictBadgeClass(verdict: TeRrMetrics['verdict']): string {
  switch (verdict) {
    case 'superior':
      return 'bg-red-50 text-pnl-profit'
    case 'inferior':
      return 'bg-blue-50 text-pnl-loss'
    default:
      return 'bg-gray-100 text-gray-500'
  }
}

// 구조 태그 — 사분면 *형태 설명* 을 앞세우고 라벨은 괄호로 보조 표기.
// "견고형" 단독 표기는 긍정 어감이라 verdict=열위(inferior) 인데 structure_tag=robust 인
// 실측 케이스(VB)에서 "우량 전략"으로 오독될 위험 — team-lead 지적 반영.
// 색상은 항상 중립 회색(TeRrBody D행) — verdict 색을 따라가지 않는다.
const STRUCTURE_LABELS: Record<NonNullable<TeRrMetrics['structure_tag']>, string> = {
  robust: '저승률·고손익비형(견고형)',
  fragile: '고승률·저손익비형(취약형)',
  balanced: '균형형',
}

// 표본 캡션 (자문 §226 표 4행 규칙)
function sampleCaption(m: TeRrMetrics): { text: string; className: string } | null {
  if (m.sample_tier === 'insufficient') {
    return { text: `표본 부족 (${m.n}건) — 참고 불가`, className: 'text-gray-500' }
  }
  if (m.sample_tier === 'low') {
    if (m.rr_available) {
      return { text: '표본 적음 — 추세 참고용', className: 'text-amber-700' }
    }
    return { text: '손실 표본 부족', className: 'text-gray-500' }
  }
  // normal
  if (m.single_trade_dominant) {
    return { text: 'RR 과대 가능 (단일 대박 의존)', className: 'text-amber-700' }
  }
  return null
}

// RR 게이지 — 실제RR 채움 + 필요RR 마커(세로선). 채움≥마커=우위(이익색)/미만=열위(손실색)
function RrGauge({
  strategyKey,
  rr,
  requiredRr,
}: {
  strategyKey: string
  rr: number
  requiredRr: number
}) {
  const scaleMax = Math.max(rr, requiredRr, 1) * 1.15
  const fillPct = Math.min(100, Math.max(0, (rr / scaleMax) * 100))
  const markerPct = Math.min(100, Math.max(0, (requiredRr / scaleMax) * 100))
  const superior = rr >= requiredRr
  const fillColorClass = superior ? 'bg-pnl-profit' : 'bg-pnl-loss'

  return (
    <div data-testid={`rr-gauge-${strategyKey}`}>
      <div className="relative h-2 bg-gray-100 rounded overflow-hidden">
        <div
          data-testid={`rr-gauge-fill-${strategyKey}`}
          className={`h-full ${fillColorClass}`}
          style={{ width: `${fillPct}%` }}
        />
        <div
          data-testid={`rr-gauge-marker-${strategyKey}`}
          className="absolute top-0 h-full w-0.5 bg-gray-700"
          style={{ left: `${markerPct}%` }}
        />
      </div>
      <p className="text-[11px] text-gray-500 mt-0.5">
        RR {rr.toFixed(2)} ⏐필요 {requiredRr.toFixed(2)} 여유{' '}
        <span className={profitColorClass(rr - requiredRr)}>
          {rr - requiredRr > 0 ? '+' : ''}
          {(rr - requiredRr).toFixed(2)}
        </span>
      </p>
    </div>
  )
}

function TeRrSection({
  strategyKey,
  metrics,
  isLoading,
  isError,
}: {
  strategyKey: string
  metrics: TeRrMetrics | undefined
  isLoading: boolean
  isError: boolean
}) {
  return (
    <div
      data-testid={`te-section-${strategyKey}`}
      className="mt-3 pt-3 border-t border-gray-100"
    >
      <p className="text-xs font-semibold text-gray-700 mb-2">성과 (최근 3개월)</p>

      {isLoading && <p className="text-xs text-gray-400">성과 데이터 로딩 중...</p>}

      {!isLoading && isError && (
        <p className="text-xs text-red-500">서버 연결 끊김 — 성과 데이터 조회 실패</p>
      )}

      {!isLoading && !isError && !metrics && (
        <p className="text-xs text-gray-400">성과 데이터 없음</p>
      )}

      {!isLoading && !isError && metrics && (
        <TeRrBody strategyKey={strategyKey} metrics={metrics} />
      )}
    </div>
  )
}

function TeRrBody({ strategyKey, metrics: m }: { strategyKey: string; metrics: TeRrMetrics }) {
  const isInsufficient = m.sample_tier === 'insufficient'
  const showGauge = !isInsufficient && m.rr_available && m.rr !== null && m.required_rr !== null
  const showStructure = !isInsufficient && m.structure_tag !== null
  const caption = sampleCaption(m)

  return (
    <div className="space-y-1.5">
      {/* A: 배지 + TE 헤드라인 + 3개월 실현 ₩ */}
      <div className="flex items-center justify-between flex-wrap gap-1">
        <div className="flex items-center gap-2">
          {/* verdict 배지 = 카드에서 가장 지배적인 신호 (team-lead 지적 — structure_tag 는 보조) */}
          <span
            data-testid={`te-verdict-${strategyKey}`}
            className={`inline-flex items-center px-2.5 py-1 rounded-md text-sm font-bold ${verdictBadgeClass(m.verdict)}`}
          >
            {VERDICT_LABELS[m.verdict]}
          </span>
          <span
            data-testid={`te-value-${strategyKey}`}
            className={`text-sm font-semibold ${isInsufficient ? 'text-gray-400' : profitColorClass(m.te_pct)}`}
          >
            TE {formatSignedPercent(m.te_pct)}
          </span>
        </div>
        <span data-testid={`te-realized-${strategyKey}`} className="text-xs text-gray-500">
          3개월 실현 {formatKrwSigned(m.realized_sum_krw)}
        </span>
      </div>

      {/* B: RR 게이지 (표본 게이트) */}
      {!isInsufficient &&
        (showGauge ? (
          <RrGauge strategyKey={strategyKey} rr={m.rr as number} requiredRr={m.required_rr as number} />
        ) : (
          <p data-testid={`rr-gauge-${strategyKey}`} className="text-xs text-gray-400">
            RR 참고 불가 — 손실/이익 표본 부족
          </p>
        ))}

      {/* C: 분해 (승/패/N + 평균수익/평균손실) */}
      {isInsufficient ? (
        <p data-testid={`te-decomposition-${strategyKey}`} className="text-xs text-gray-500">
          승 {m.win} · 패 {m.loss} · 거래 {m.n}건
        </p>
      ) : (
        <p data-testid={`te-decomposition-${strategyKey}`} className="text-xs text-gray-600">
          승률 {(m.win_rate * 100).toFixed(0)}% (승{m.win}/패{m.loss}) · 평균수익{' '}
          <span className={profitColorClass(m.avg_win_pct ?? 0)}>
            {formatSignedPercent(m.avg_win_pct)}
          </span>{' '}
          · 평균손실{' '}
          <span className={profitColorClass(m.avg_loss_pct ?? 0)}>
            {formatSignedPercent(m.avg_loss_pct)}
          </span>{' '}
          · 거래 {m.n}건
        </p>
      )}

      {/* D: 구조 태그 */}
      {showStructure && (
        <p data-testid={`te-structure-${strategyKey}`} className="text-xs text-gray-600">
          구조: {STRUCTURE_LABELS[m.structure_tag as NonNullable<TeRrMetrics['structure_tag']>]}
        </p>
      )}

      {/* E: 표본 캡션 (조건부) */}
      {caption && (
        <p data-testid={`te-sample-caption-${strategyKey}`} className={`text-xs ${caption.className}`}>
          {caption.text}
        </p>
      )}
    </div>
  )
}

// 표 1-2 참조표 — 승률 10~90% → 필요RR = (100-승률)/승률
const TE_REFERENCE_ROWS = [10, 20, 30, 40, 50, 60, 70, 80, 90].map((winRatePct) => ({
  winRatePct,
  requiredRr: (100 - winRatePct) / winRatePct,
}))

const TE_EDUCATION_CAPTION =
  'TE는 거래당 기대손익(크기), RR비율은 손익비(구조)입니다. RR > 필요RR 이면 우위(TE 양수와 동일 판정). ' +
  '승률이 낮아도 RR이 크면 우위일 수 있습니다(터틀 전략). 최근 3개월 실현 청산 기준이며 미실현은 제외, ' +
  '표본·기간이 짧아 시장 국면에 좌우되는 모니터링 지표입니다.'

function TeRrReferenceFooter() {
  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">승률 → 필요RR 참조표</h3>
        <ScrollPane>
          <table data-testid="te-reference-table" className="text-xs w-full text-left">
            <thead>
              <tr className="text-gray-500">
                <th className="pr-4 py-1">승률</th>
                {TE_REFERENCE_ROWS.map((row) => (
                  <th key={row.winRatePct} className="px-2 py-1 text-center">
                    {row.winRatePct}%
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="text-gray-700 font-medium">
                <td className="pr-4 py-1">필요RR</td>
                {TE_REFERENCE_ROWS.map((row) => (
                  <td key={row.winRatePct} className="px-2 py-1 text-center">
                    {row.requiredRr.toFixed(2)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </ScrollPane>
      </div>
      <p data-testid="te-education-caption" className="text-xs text-gray-500 leading-relaxed">
        {TE_EDUCATION_CAPTION}
      </p>
    </div>
  )
}
// ── 사이클 F 끝 ──────────────────────────────────────────────────────────

function StrategyCard({
  strategyKey,
  strategy,
  teMetrics,
  teLoading,
  teError,
  onOpenParams,
}: {
  strategyKey: string
  strategy: StrategyStatus
  teMetrics: TeRrMetrics | undefined
  teLoading: boolean
  teError: boolean
  onOpenParams: (strategyKey: string) => void
}) {
  const color = getStrategyColor(strategyKey)

  return (
    <div
      data-testid={`strategy-card-${strategyKey}`}
      className={`bg-white rounded-lg shadow p-4 border-l-4 ${color.bg}`}
      style={{ borderLeftColor: color.hex }}
    >
      {/* 카드 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{strategy.name}</h3>
          <p className="text-xs text-gray-500">
            비중 {(strategy.weight * 100).toFixed(0)}%
            {strategy.total_investment > 0 &&
              ` · 배정 ${(strategy.total_investment / 10000).toFixed(0)}만원`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              strategy.enabled
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {strategy.enabled ? '활성' : '비활성'}
          </span>
          {/* cycle278 — 카탈로그 기반 편집기 진입점. 이 카드의 4 임계는 읽기 전용 요약으로 남고,
              설정 가능한 전 항목은 편집기가 스키마 응답으로 렌더한다. */}
          <button
            data-testid={`strategy-params-open-${strategyKey}`}
            onClick={() => onOpenParams(strategyKey)}
            className="px-2 py-0.5 text-xs font-medium text-blue-600 border border-blue-200 rounded hover:bg-blue-50"
          >
            파라미터
          </button>
        </div>
      </div>

      {/* 4 임계 그리드 */}
      <div className="grid grid-cols-2 gap-2">
        {THRESHOLD_KEYS.map((key) => {
          const val = strategy.params[key] as number | null | undefined
          const testId = `strategy-${strategyKey}-${key.replace(/_/g, '-')}`
          return (
            <div
              key={key}
              className="bg-gray-50 rounded p-2"
            >
              <p className="text-xs text-gray-500 mb-0.5">{PARAM_LABELS[key]}</p>
              <p
                data-testid={testId}
                className={`text-sm font-semibold ${thresholdColor(key, val)}`}
              >
                {key === 'position_ratio'
                  ? val !== null && val !== undefined && !isNaN(Number(val))
                    ? `${(Number(val) * 100).toFixed(0)}%`
                    : '—'
                  : formatPercent(val)}
              </p>
            </div>
          )
        })}
      </div>

      {/* 사이클 F — TE/RR 성과 섹션 (관찰 전용) */}
      <TeRrSection
        strategyKey={strategyKey}
        metrics={teMetrics}
        isLoading={teLoading}
        isError={teError}
      />
    </div>
  )
}

export default function Strategies() {
  // cycle278 — 파라미터 편집기를 연 전략 id (null = 닫힘). 스키마는 열 때만 fetch 한다.
  const [paramsStrategy, setParamsStrategy] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const resp = await apiClient.get<ApiResponse<StrategiesResponse>>('/strategies')
      return resp.data.data
    },
    retry: 1, // 사이클 65 H3 영속
    refetchInterval: 60_000,
    staleTime: 15_000,
  })

  // 사이클 F — TE/RR 성과 (최근 3개월, 관찰 전용). 5분 TTL 백엔드 캐시 정합.
  const {
    data: teData,
    isLoading: teIsLoading,
    isError: teIsError,
  } = useQuery({
    queryKey: ['strategy-te', 3],
    queryFn: () => getStrategyTeRr(3),
    retry: 1, // 사이클 65 H3 영속
    staleTime: 5 * 60 * 1000,
  })

  const teMetricsMap: Record<string, TeRrMetrics> = (() => {
    if (!teData) return {}
    return Object.fromEntries(teData.map((m) => [m.strategy_id, m]))
  })()

  // strategies는 dict 또는 배열 양쪽 처리.
  // 백엔드 GET /api/strategies 가 플랫 형식 { momentum: {...}, ... } 반환 시
  // data?.strategies = undefined → data 자체를 플랫 형식으로 fallback.
  const strategiesMap: Record<string, StrategyStatus> = (() => {
    const raw = data?.strategies ?? data
    if (!raw) return {}
    if (Array.isArray(raw)) {
      // 배열 형식 (key 필드 사용)
      return Object.fromEntries(
        raw.map((s) => [s.key ?? String(Math.random()), s])
      )
    }
    return raw as Record<string, StrategyStatus>
  })()

  const strategyKeys = Object.keys(strategiesMap)

  return (
    <div className="space-y-4">
      {/* 페이지 헤더 */}
      <div>
        <h1 className="text-lg font-bold text-gray-900">전략 현황</h1>
        <p className="text-sm text-gray-500">
          전략별 손절·트레일링·포지션 임계 실시간 모니터링
        </p>
      </div>

      {/* 로딩 */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
              <div className="h-5 bg-gray-200 rounded w-1/3 mb-3" />
              <div className="grid grid-cols-2 gap-2">
                {[1, 2, 3, 4].map((j) => (
                  <div key={j} className="bg-gray-50 rounded p-2">
                    <div className="h-3 bg-gray-200 rounded w-2/3 mb-1" />
                    <div className="h-4 bg-gray-100 rounded w-1/2" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 에러 */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">서버 연결 끊김 — 전략 조회 실패</p>
        </div>
      )}

      {/* 데이터 없음 */}
      {!isLoading && !isError && strategyKeys.length === 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-sm text-gray-500">등록된 전략이 없습니다.</p>
        </div>
      )}

      {/* 전략 카드 그리드 */}
      {!isLoading && !isError && strategyKeys.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {strategyKeys.map((key) => (
            <StrategyCard
              key={key}
              strategyKey={key}
              strategy={strategiesMap[key]}
              teMetrics={teMetricsMap[key]}
              teLoading={teIsLoading}
              teError={teIsError}
              onOpenParams={setParamsStrategy}
            />
          ))}
        </div>
      )}

      {/* 사이클 F — TE/RR 참조표 + 교육 캡션 (페이지 하단 1회) */}
      {!isLoading && !isError && strategyKeys.length > 0 && <TeRrReferenceFooter />}

      {/* cycle278 — 파라미터 편집기 (스키마 응답만으로 렌더, 키 하드코딩 0건) */}
      {paramsStrategy && (
        <StrategyParamsEditor
          strategyId={paramsStrategy}
          onClose={() => setParamsStrategy(null)}
        />
      )}

      {/* 안내 */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
        <p className="text-xs text-amber-700">
          손절·일일 손실 한도는 음수(파란색) 표시. 트레일링은 고가 대비 하락 임계.
          종목당 비율 = 전략 배정 자금 대비 단일 종목 매수 비율.
        </p>
      </div>
    </div>
  )
}
