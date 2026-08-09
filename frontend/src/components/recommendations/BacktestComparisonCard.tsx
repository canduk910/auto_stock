/**
 * Phase 4 (2026-05-16) — Recommendations 페이지의 백테스트 비교 카드.
 * Phase 6.1 (2026-05-17) — MDD 양수(절대값) 컨벤션 확정 (외부 MCP 실측 검증 산출).
 *
 * 백엔드 `parameter_recommendations.backtest_summary` JSONB 를 렌더.
 * 8개 메트릭을 좌(current) / 우(recommended) / diff 칩 형태로 표시.
 *
 * 컬러 컨벤션 (frontend/CLAUDE.md):
 * - 이익(개선) = #FF3333 빨강 / 손실(악화) = #3366FF 파랑 / 보합 = #333333
 * - max_drawdown 은 외부 MCP 서버가 **양수 절대값**(예: 8.5, 16.1) 으로 반환 (Phase 6 실측 확정).
 *   diff = recommended - current. 양수 diff = MDD 절대값 증가 = 손실 악화 → 파랑 (signInverted: true).
 *   음수 diff = MDD 절대값 감소 = 손실 완화 → 빨강.
 *
 * null 가드:
 * - props.summary == null → placeholder (백테스트 미실행/진행중 안내)
 * - 자기 전략의 current/recommended 모두 null → (b) 로컬 폴백 안내
 */

import { useMemo } from 'react'
import type { BacktestMetrics, BacktestSummary } from '../../types/backtest'
import { BACKTEST_METRIC_KEYS } from '../../types/backtest'
import { getStrategyColor } from '../../types/strategy'
import { PROFIT_HEX as PROFIT_COLOR, LOSS_HEX as LOSS_COLOR } from '../../utils/pnlColor'

const NEUTRAL_COLOR = '#333333'

interface MetricFormatSpec {
  label: string
  /** 메트릭 값 절대값 표시 포맷 */
  formatValue: (v: number | null | undefined) => string
  /** diff 값 표시 포맷 (부호 포함) */
  formatDiff: (v: number | null | undefined) => string
  /** diff 부호 → 색상 결정. 기본 양수=이익 음수=손실, 일부 메트릭은 역전 */
  diffSignInverted: boolean
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return `${v.toFixed(2)}%`
}

function fmtPctSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function fmtRatio2(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return v.toFixed(2)
}

function fmtRatio2Signed(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}

function fmtRatePct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return `${(v * 100).toFixed(2)}%`
}

function fmtRatePctSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}

function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return Math.round(v).toLocaleString()
}

function fmtIntSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v > 0 ? '+' : ''
  return `${sign}${Math.round(v).toLocaleString()}`
}

const METRIC_SPECS: Record<keyof BacktestMetrics, MetricFormatSpec> = {
  total_return_pct: {
    label: '총수익률',
    formatValue: fmtPct,
    formatDiff: fmtPctSigned,
    diffSignInverted: false,
  },
  cagr: {
    label: 'CAGR',
    formatValue: fmtPct,
    formatDiff: fmtPctSigned,
    diffSignInverted: false,
  },
  sharpe_ratio: {
    label: 'Sharpe',
    formatValue: fmtRatio2,
    formatDiff: fmtRatio2Signed,
    diffSignInverted: false,
  },
  sortino_ratio: {
    label: 'Sortino',
    formatValue: fmtRatio2,
    formatDiff: fmtRatio2Signed,
    diffSignInverted: false,
  },
  max_drawdown: {
    // Phase 6.1: 외부 MCP 양수 절대값 컨벤션 확정 (예: 8.5%, 16.1%).
    // diff = recommended - current. 양수 diff = MDD 증가 = 손실 악화 → 파랑.
    // 음수 diff = MDD 감소 = 손실 완화 → 빨강. signInverted=true 로 부호 해석 역전.
    label: 'MDD',
    formatValue: fmtPct,
    formatDiff: fmtPctSigned,
    diffSignInverted: true,
  },
  win_rate: {
    label: '승률',
    formatValue: fmtRatePct,
    formatDiff: fmtRatePctSigned,
    diffSignInverted: false,
  },
  profit_factor: {
    label: 'Profit Factor',
    formatValue: fmtRatio2,
    formatDiff: fmtRatio2Signed,
    diffSignInverted: false,
  },
  total_trades: {
    label: '거래 건수',
    formatValue: fmtInt,
    formatDiff: fmtIntSigned,
    diffSignInverted: false,
  },
}

function diffColor(value: number | null | undefined, inverted: boolean): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value === 0) {
    return NEUTRAL_COLOR
  }
  const isPositive = value > 0
  // inverted = max_drawdown: 양수 diff = 손실 증가 → 파랑
  if (inverted) {
    return isPositive ? LOSS_COLOR : PROFIT_COLOR
  }
  return isPositive ? PROFIT_COLOR : LOSS_COLOR
}

interface BacktestComparisonCardProps {
  strategyId: string
  summary: BacktestSummary | null | undefined
}

export default function BacktestComparisonCard({
  strategyId,
  summary,
}: BacktestComparisonCardProps) {
  const own = useMemo(() => {
    if (!summary) return null
    const current = summary.current?.[strategyId] ?? null
    const recommended = summary.recommended?.[strategyId] ?? null
    const diff = (summary.diff?.[strategyId] ?? {}) as Partial<BacktestMetrics>
    return { current, recommended, diff }
  }, [summary, strategyId])

  const peers = useMemo(() => {
    if (!summary) return []
    const ids = new Set<string>()
    for (const sid of Object.keys(summary.current ?? {})) ids.add(sid)
    for (const sid of Object.keys(summary.recommended ?? {})) ids.add(sid)
    return Array.from(ids)
      .filter((sid) => sid !== strategyId)
      .sort()
  }, [summary, strategyId])

  // 케이스 A — backtest_summary 자체가 null
  if (!summary) {
    return (
      <div
        data-testid={`backtest-comparison-card-${strategyId}`}
        className="mb-4 rounded-lg border border-gray-200 bg-gray-50/60 p-4"
      >
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-sm font-medium text-gray-700">백테스트 검증</h4>
          <span className="text-xs text-gray-400">90일 기준</span>
        </div>
        <p className="text-sm text-gray-500">
          백테스트 미실행 — 진행중이거나 외부 MCP 비활성 상태입니다. 결과가 도착하면 8개 메트릭으로 비교 표시됩니다.
        </p>
      </div>
    )
  }

  // 케이스 B — 자기 전략 current/recommended 모두 null ((b) 로컬 폴백)
  if (own && own.current === null && own.recommended === null) {
    return (
      <div
        data-testid={`backtest-comparison-card-${strategyId}`}
        className="mb-4 rounded-lg border border-amber-200 bg-amber-50/40 p-4"
      >
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-sm font-medium text-amber-800">백테스트 검증</h4>
          <span className="text-xs text-amber-600">로컬 어댑터 대기</span>
        </div>
        <p className="text-sm text-amber-700">
          이 전략은 외부 MCP YAML DSL 미지원으로 로컬 백테스트 어댑터 적용 대기 상태입니다.
        </p>
      </div>
    )
  }

  // 케이스 C — 정상 데이터 (current 또는 recommended 한 쪽 이상 존재)
  const current = own?.current ?? null
  const recommended = own?.recommended ?? null
  const diff = own?.diff ?? {}

  return (
    <div
      data-testid={`backtest-comparison-card-${strategyId}`}
      className="mb-4 rounded-lg border border-gray-200 bg-white p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-gray-800">백테스트 검증 (90일)</h4>
        <span className="text-xs text-gray-400">
          현재 파라미터 vs 추천 파라미터
        </span>
      </div>

      <div className="overflow-hidden border border-gray-200 rounded-md mb-3">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-600">메트릭</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">현재</th>
              <th className="px-3 py-2 text-center font-medium text-gray-400 w-6">→</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">추천</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">차이</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {BACKTEST_METRIC_KEYS.map((key) => {
              const spec = METRIC_SPECS[key]
              const curVal = current ? current[key] : null
              const recVal = recommended ? recommended[key] : null
              const diffVal = diff[key]
              const color = diffColor(diffVal, spec.diffSignInverted)
              return (
                <tr key={key}>
                  <td className="px-3 py-2 text-gray-700">{spec.label}</td>
                  <td
                    className="px-3 py-2 text-right font-mono text-gray-700"
                    data-testid={`metric-current-${key}`}
                  >
                    {spec.formatValue(curVal)}
                  </td>
                  <td className="px-3 py-2 text-center text-gray-300">→</td>
                  <td
                    className="px-3 py-2 text-right font-mono font-medium text-gray-900"
                    data-testid={`metric-recommended-${key}`}
                  >
                    {spec.formatValue(recVal)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-mono text-xs"
                    data-testid={`metric-diff-${key}`}
                    style={{ color }}
                  >
                    {spec.formatDiff(diffVal)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {peers.length > 0 && (
        <details className="mt-2">
          <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
            다른 전략 백테스트 비교 ({peers.length})
          </summary>
          <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {peers.map((sid) => (
              <PeerMiniCard
                key={sid}
                strategyId={sid}
                current={summary.current?.[sid] ?? null}
                recommended={summary.recommended?.[sid] ?? null}
                diff={(summary.diff?.[sid] ?? {}) as Partial<BacktestMetrics>}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

interface PeerMiniCardProps {
  strategyId: string
  current: BacktestMetrics | null
  recommended: BacktestMetrics | null
  diff: Partial<BacktestMetrics>
}

function PeerMiniCard({ strategyId, current, recommended, diff }: PeerMiniCardProps) {
  const color = getStrategyColor(strategyId)
  const isSkipped = current === null && recommended === null

  return (
    <div
      data-testid={`backtest-peer-${strategyId}`}
      className="rounded border border-gray-200 bg-gray-50 p-2"
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color.hex }} />
        <span className="text-xs font-medium text-gray-700">{strategyId}</span>
      </div>
      {isSkipped ? (
        <div className="text-[11px] text-amber-700">로컬 어댑터 대기</div>
      ) : (
        <dl className="space-y-0.5 text-[11px]">
          <PeerRow
            label="총수익률"
            current={current?.total_return_pct ?? null}
            recommended={recommended?.total_return_pct ?? null}
            diffValue={diff.total_return_pct}
            formatValue={fmtPct}
            formatDiff={fmtPctSigned}
            inverted={false}
          />
          <PeerRow
            label="Sharpe"
            current={current?.sharpe_ratio ?? null}
            recommended={recommended?.sharpe_ratio ?? null}
            diffValue={diff.sharpe_ratio}
            formatValue={fmtRatio2}
            formatDiff={fmtRatio2Signed}
            inverted={false}
          />
          <PeerRow
            label="MDD"
            current={current?.max_drawdown ?? null}
            recommended={recommended?.max_drawdown ?? null}
            diffValue={diff.max_drawdown}
            formatValue={fmtPct}
            formatDiff={fmtPctSigned}
            inverted
          />
        </dl>
      )}
    </div>
  )
}

interface PeerRowProps {
  label: string
  current: number | null
  recommended: number | null
  diffValue: number | null | undefined
  formatValue: (v: number | null | undefined) => string
  formatDiff: (v: number | null | undefined) => string
  inverted: boolean
}

function PeerRow({
  label,
  current,
  recommended,
  diffValue,
  formatValue,
  formatDiff,
  inverted,
}: PeerRowProps) {
  const color = diffColor(diffValue, inverted)
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-mono text-gray-700">
        {formatValue(current)}
        <span className="text-gray-300 mx-1">→</span>
        <span className="text-gray-900">{formatValue(recommended)}</span>
        {diffValue !== null && diffValue !== undefined && Number.isFinite(diffValue) && diffValue !== 0 && (
          <span className="ml-1" style={{ color }}>
            ({formatDiff(diffValue)})
          </span>
        )}
      </dd>
    </div>
  )
}
