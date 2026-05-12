import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listRecommendations, applyRecommendation, rejectRecommendation } from '../api/recommendations'
import { getStrategies } from '../api/trading'
import { getStrategyColor } from '../types/strategy'
import { PARAM_LABELS, formatParamValue } from '../utils/paramLabels'
import InfoTooltip from '../components/InfoTooltip'
import ConfirmModal from '../components/ConfirmModal'
import type { RecommendationItem, RecommendationStatus, RecommendationMetrics } from '../types/recommendations'

const STATUS_LABEL: Record<RecommendationStatus, string> = {
  pending: '대기',
  applied: '적용됨',
  partial: '일부 적용',
  rejected: '거절됨',
  expired: '만료',
}

const STATUS_BADGE_CLASS: Record<RecommendationStatus, string> = {
  pending: 'bg-blue-100 text-blue-700',
  applied: 'bg-green-100 text-green-700',
  partial: 'bg-yellow-100 text-yellow-700',
  rejected: 'bg-gray-100 text-gray-600',
  expired: 'bg-gray-100 text-gray-500',
}

// 색상 컨벤션: 이익=빨강, 손실=파랑
const PROFIT_COLOR = '#FF3333'
const LOSS_COLOR = '#3366FF'

function formatPct(value: number | undefined, fractionDigits = 2): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '-'
  return `${value.toFixed(fractionDigits)}%`
}

function formatRatioPct(value: number | undefined, fractionDigits = 1): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '-'
  return `${(value * 100).toFixed(fractionDigits)}%`
}

function formatNumber(value: number | undefined): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '-'
  return value.toLocaleString()
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('ko-KR', { hour12: false })
  } catch {
    return iso
  }
}

interface MetricFieldDef {
  key: keyof RecommendationMetrics
  label: string
  format: (m: RecommendationMetrics) => string
}

const METRIC_FIELDS: MetricFieldDef[] = [
  { key: 'trades_count', label: '거래 건수', format: (m) => formatNumber(m.trades_count) },
  { key: 'win_rate', label: '승률', format: (m) => formatRatioPct(m.win_rate, 1) },
  { key: 'avg_profit_pct', label: '평균 수익률', format: (m) => formatPct(m.avg_profit_pct) },
  { key: 'avg_loss_pct', label: '평균 손실률', format: (m) => formatPct(m.avg_loss_pct) },
  { key: 'stop_loss_hits', label: '손절 도달', format: (m) => formatNumber(m.stop_loss_hits) },
  { key: 'cumulative_return', label: '누적 수익률', format: (m) => formatPct(m.cumulative_return) },
  { key: 'analyzed_days', label: '분석 일수', format: (m) => formatNumber(m.analyzed_days) },
]

type TabKey = 'pending' | 'history'

export default function Recommendations() {
  const queryClient = useQueryClient()
  const [selectedKeys, setSelectedKeys] = useState<Record<string, Set<string>>>({})
  // Phase J4 — recommended_weight 적용 토글 (rec_id 별)
  const [weightApplyMap, setWeightApplyMap] = useState<Record<string, boolean>>({})
  const [applyTarget, setApplyTarget] = useState<RecommendationItem | null>(null)
  const [rejectTarget, setRejectTarget] = useState<RecommendationItem | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [tab, setTab] = useState<TabKey>('pending')
  const [historyStatusFilter, setHistoryStatusFilter] = useState<RecommendationStatus | 'all'>('all')
  const [historyStrategyFilter, setHistoryStrategyFilter] = useState<string>('all')

  const { data: items, isLoading, isError } = useQuery({
    queryKey: ['recommendations'],
    queryFn: listRecommendations,
  })

  const { data: strategiesData } = useQuery({
    queryKey: ['strategies'],
    queryFn: getStrategies,
  })

  const strategyNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const s of strategiesData?.strategies ?? []) {
      map[s.key] = s.name
    }
    return map
  }, [strategiesData])

  const applyMutation = useMutation({
    mutationFn: ({ id, keys, applyWeight }: { id: string; keys: string[]; applyWeight?: boolean }) =>
      applyRecommendation(id, keys, { applyWeight }),
    onSuccess: (result, variables) => {
      if (!result.success) {
        setErrors((prev) => ({ ...prev, [variables.id]: result.message || '적용에 실패했습니다.' }))
      } else {
        setErrors((prev) => {
          const next = { ...prev }
          delete next[variables.id]
          return next
        })
        setSelectedKeys((prev) => {
          const next = { ...prev }
          delete next[variables.id]
          return next
        })
        setWeightApplyMap((prev) => {
          const next = { ...prev }
          delete next[variables.id]
          return next
        })
      }
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setApplyTarget(null)
    },
    onError: (err: Error, variables) => {
      setErrors((prev) => ({ ...prev, [variables.id]: err.message || '적용에 실패했습니다.' }))
      setApplyTarget(null)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => rejectRecommendation(id),
    onSuccess: (result, id) => {
      if (!result.success) {
        setErrors((prev) => ({ ...prev, [id]: result.message || '거절에 실패했습니다.' }))
      } else {
        setErrors((prev) => {
          const next = { ...prev }
          delete next[id]
          return next
        })
      }
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      setRejectTarget(null)
    },
    onError: (err: Error, id) => {
      setErrors((prev) => ({ ...prev, [id]: err.message || '거절에 실패했습니다.' }))
      setRejectTarget(null)
    },
  })

  // 가장 최근 target_date — 신규 탭 기준
  const latestTargetDate = useMemo(() => {
    const list = items ?? []
    if (list.length === 0) return null
    return list.reduce<string>((acc, it) => (it.target_date > acc ? it.target_date : acc), list[0].target_date)
  }, [items])

  // 탭별 + 필터 적용
  const filteredItems = useMemo(() => {
    const list = items ?? []
    if (tab === 'pending') {
      // 신규 탭: 가장 최근 target_date의 자문 (status 무관)
      if (!latestTargetDate) return []
      return list.filter((it) => it.target_date === latestTargetDate)
    }
    // 이력 탭: 그 이전 + 상태/전략 필터
    return list.filter((it) => {
      if (latestTargetDate && it.target_date === latestTargetDate) return false
      if (historyStatusFilter !== 'all' && it.status !== historyStatusFilter) return false
      if (historyStrategyFilter !== 'all' && it.strategy_id !== historyStrategyFilter) return false
      return true
    })
  }, [items, tab, latestTargetDate, historyStatusFilter, historyStrategyFilter])

  // target_date 데스크 정렬 + strategy_id 정렬
  const grouped = useMemo(() => {
    const byDate: Record<string, RecommendationItem[]> = {}
    for (const it of filteredItems) {
      if (!byDate[it.target_date]) byDate[it.target_date] = []
      byDate[it.target_date].push(it)
    }
    const dates = Object.keys(byDate).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0))
    return dates.map((d) => ({
      date: d,
      items: byDate[d].slice().sort((a, b) => a.strategy_id.localeCompare(b.strategy_id)),
    }))
  }, [filteredItems])

  const pendingCount = useMemo(() => {
    const list = items ?? []
    if (!latestTargetDate) return 0
    return list.filter((it) => it.target_date === latestTargetDate).length
  }, [items, latestTargetDate])
  const historyCount = useMemo(() => {
    const list = items ?? []
    if (!latestTargetDate) return list.length
    return list.filter((it) => it.target_date !== latestTargetDate).length
  }, [items, latestTargetDate])

  const toggleKey = (recId: string, key: string) => {
    setSelectedKeys((prev) => {
      const cur = new Set(prev[recId] ?? [])
      if (cur.has(key)) cur.delete(key)
      else cur.add(key)
      return { ...prev, [recId]: cur }
    })
  }

  const isActionable = (status: RecommendationStatus) => status === 'pending' || status === 'partial'

  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">전략수정 AI자문</h1>
        <div className="p-6 text-gray-500">자문 정보를 불러오는 중...</div>
      </div>
    )
  }

  if (isError) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">전략수정 AI자문</h1>
        <div className="p-6 text-red-500">자문 정보를 불러올 수 없습니다.</div>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">전략수정 AI자문</h1>

      {/* 안내 */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <p className="text-sm text-blue-800">
          매일 NXT 애프터 종료 직전(19:50) OpenAI가 전략 성과를 분석해 파라미터 수정안을 자동 생성합니다. 전략별로 원하는 항목만 선택해 적용할 수 있고, 처리된 자문은 이력 탭에서 확인할 수 있습니다.
        </p>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 border-b border-gray-200 mb-4">
        <button
          onClick={() => setTab('pending')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'pending'
              ? 'border-blue-600 text-blue-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          신규 자문 {pendingCount > 0 && <span className="ml-1 px-1.5 py-0.5 text-xs bg-blue-100 text-blue-700 rounded">{pendingCount}</span>}
        </button>
        <button
          onClick={() => setTab('history')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'history'
              ? 'border-blue-600 text-blue-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          이력 {historyCount > 0 && <span className="ml-1 px-1.5 py-0.5 text-xs bg-gray-100 text-gray-600 rounded">{historyCount}</span>}
        </button>
      </div>

      {/* 이력 탭 필터 */}
      {tab === 'history' && (
        <div className="flex flex-wrap gap-3 mb-4 items-center">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600">상태</label>
            <select
              value={historyStatusFilter}
              onChange={(e) => setHistoryStatusFilter(e.target.value as RecommendationStatus | 'all')}
              className="text-sm border border-gray-300 rounded px-2 py-1"
            >
              <option value="all">전체</option>
              <option value="applied">적용됨</option>
              <option value="partial">일부 적용</option>
              <option value="rejected">거절됨</option>
              <option value="expired">만료</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600">전략</label>
            <select
              value={historyStrategyFilter}
              onChange={(e) => setHistoryStrategyFilter(e.target.value)}
              className="text-sm border border-gray-300 rounded px-2 py-1"
            >
              <option value="all">전체</option>
              {(strategiesData?.strategies ?? []).map((s) => (
                <option key={s.key} value={s.key}>{s.name}</option>
              ))}
            </select>
          </div>
          <span className="text-xs text-gray-400 ml-auto">{filteredItems.length}건</span>
        </div>
      )}

      {grouped.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          {tab === 'pending' ? (
            <>
              표시할 신규 자문이 없습니다.
              <br />
              <span className="text-sm">매일 NXT 애프터 종료 직전(19:50)에 자문이 생성됩니다.</span>
            </>
          ) : (
            <>이력에 표시할 자문이 없습니다.</>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map(({ date, items: dayItems }) => (
            <section key={date}>
              <h2 className="text-base font-semibold text-gray-700 mb-3">{date}</h2>
              <div className="space-y-4">
                {dayItems.map((rec) => {
                  const color = getStrategyColor(rec.strategy_id)
                  const strategyName = strategyNameMap[rec.strategy_id] ?? rec.strategy_id
                  const recommendedKeys = Object.keys(rec.recommended_params ?? {})
                  const appliedParams = rec.applied_params ?? {}
                  const selected = selectedKeys[rec.id] ?? new Set<string>()
                  const actionable = isActionable(rec.status)
                  const error = errors[rec.id]

                  // 선택 가능한 (이미 적용된 키 제외, 추천된 키 중) 갯수
                  const selectableKeys = recommendedKeys.filter((k) => !(k in appliedParams))
                  const checkedSelectable = selectableKeys.filter((k) => selected.has(k))

                  return (
                    <div key={rec.id} className="bg-white rounded-lg shadow p-6">
                      {/* 헤더 */}
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color.hex }} />
                          <h3 className="text-lg font-semibold text-gray-900">{strategyName}</h3>
                          <span className="text-xs text-gray-400 ml-2">
                            생성 {formatDateTime(rec.created_at)}
                          </span>
                        </div>
                        <span
                          className={`px-2 py-1 text-xs font-medium rounded ${STATUS_BADGE_CLASS[rec.status]}`}
                        >
                          {STATUS_LABEL[rec.status]}
                        </span>
                      </div>

                      {/* 분석 통계 */}
                      {rec.metrics && (
                        <div className="bg-gray-50 rounded-lg p-4 mb-4">
                          <h4 className="text-sm font-medium text-gray-700 mb-2">분석 통계</h4>
                          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-4 gap-y-2">
                            {METRIC_FIELDS.map((f) => (
                              <div key={f.key as string} className="flex justify-between text-sm">
                                <span className="text-gray-500">{f.label}</span>
                                <span className="font-medium text-gray-900">
                                  {rec.metrics ? f.format(rec.metrics) : '-'}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* 추천 근거 */}
                      {rec.reasoning && (
                        <div className="mb-4">
                          <h4 className="text-sm font-medium text-gray-700 mb-1">추천 근거</h4>
                          <p className="text-sm text-gray-600 whitespace-pre-line leading-relaxed">
                            {rec.reasoning}
                          </p>
                        </div>
                      )}

                      {/* Phase J4 — 자산 배정 카드 (recommended_weight 있을 때만) */}
                      {rec.recommended_weight !== null && rec.recommended_weight !== undefined && (
                        <div
                          data-testid={`weight-card-${rec.id}`}
                          className="mb-4 rounded-lg border border-blue-200 bg-blue-50/40 p-4"
                        >
                          <h4 className="text-sm font-medium text-blue-900 mb-2">자산 배정 자문</h4>
                          {(() => {
                            const cur = strategiesData?.strategies?.find((s) => s.key === rec.strategy_id)
                            const curWeightPct = cur ? Math.round(cur.weight * 100) : null
                            const recWeightPct = Math.round((rec.recommended_weight ?? 0) * 100)
                            const diffPct =
                              curWeightPct !== null ? recWeightPct - curWeightPct : null
                            const appliedPct =
                              rec.applied_weight !== null && rec.applied_weight !== undefined
                                ? Math.round(rec.applied_weight * 100)
                                : null
                            return (
                              <div className="space-y-2 text-sm">
                                <div className="flex items-center gap-3">
                                  <span className="text-gray-600">현재 weight</span>
                                  <span className="font-mono font-medium text-gray-900">
                                    {curWeightPct !== null ? `${curWeightPct}%` : '-'}
                                  </span>
                                  <span className="text-gray-400">→</span>
                                  <span className="text-gray-600">추천 weight</span>
                                  <span className="font-mono font-medium text-blue-700">
                                    {recWeightPct}%
                                  </span>
                                  {diffPct !== null && diffPct !== 0 && (
                                    <span
                                      className="font-mono text-xs"
                                      style={{ color: diffPct > 0 ? PROFIT_COLOR : LOSS_COLOR }}
                                    >
                                      ({diffPct > 0 ? '+' : ''}{diffPct}%p)
                                    </span>
                                  )}
                                </div>
                                {appliedPct !== null && (
                                  <div className="text-xs text-green-700">
                                    적용됨: {appliedPct}%
                                  </div>
                                )}
                                {actionable && appliedPct === null && (
                                  <label className="inline-flex items-center gap-2 cursor-pointer mt-1">
                                    <input
                                      type="checkbox"
                                      data-testid={`weight-apply-checkbox-${rec.id}`}
                                      checked={!!weightApplyMap[rec.id]}
                                      onChange={(e) =>
                                        setWeightApplyMap((prev) => ({
                                          ...prev,
                                          [rec.id]: e.target.checked,
                                        }))
                                      }
                                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                    />
                                    <span className="text-sm text-gray-700">weight 적용</span>
                                  </label>
                                )}
                                <div className="text-xs text-amber-700">
                                  weight 변경은 다음 영업일부터 반영됩니다 (운영자 수동 적용).
                                </div>
                              </div>
                            )
                          })()}
                        </div>
                      )}

                      {/* Phase J4 — 로직/파라미터 자문 카드 (code_review_notes 있을 때만) */}
                      {rec.code_review_notes && (
                        <div
                          data-testid={`code-review-card-${rec.id}`}
                          className="mb-4 rounded-lg border border-purple-200 bg-purple-50/40 p-4"
                        >
                          <h4 className="text-sm font-medium text-purple-900 mb-2">
                            로직/파라미터 자문
                            <span className="ml-2 text-xs font-normal text-purple-700">
                              (자동 적용 없음 — 운영자 수동 검토용)
                            </span>
                          </h4>
                          <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                            {rec.code_review_notes}
                          </p>
                        </div>
                      )}

                      {/* 파라미터 변경 표 */}
                      <div className="mb-4">
                        <h4 className="text-sm font-medium text-gray-700 mb-2">권고 파라미터</h4>
                        {recommendedKeys.length === 0 ? (
                          <p className="text-sm text-gray-500">변경 권고 사항이 없습니다.</p>
                        ) : (
                          <div className="overflow-hidden border border-gray-200 rounded-md">
                            <table className="w-full text-sm">
                              <thead className="bg-gray-50">
                                <tr>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600 w-10"></th>
                                  <th className="px-3 py-2 text-left font-medium text-gray-600">파라미터</th>
                                  <th className="px-3 py-2 text-right font-medium text-gray-600">현재값</th>
                                  <th className="px-3 py-2 text-center font-medium text-gray-400 w-8"></th>
                                  <th className="px-3 py-2 text-right font-medium text-gray-600">추천값</th>
                                  <th className="px-3 py-2 text-right font-medium text-gray-600">차이</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100">
                                {recommendedKeys.map((key) => {
                                  const meta = PARAM_LABELS[key]
                                  const label = meta?.label ?? key
                                  const currentValue = rec.current_params?.[key]
                                  const recommendedValue = rec.recommended_params[key]
                                  const isAlreadyApplied = key in appliedParams
                                  const checkboxDisabled = !actionable || isAlreadyApplied
                                  const isChecked = selected.has(key)

                                  const hasCurrent =
                                    typeof currentValue === 'number' && Number.isFinite(currentValue)
                                  const diff = hasCurrent ? recommendedValue - (currentValue as number) : null
                                  const diffColor =
                                    diff === null || diff === 0
                                      ? '#333333'
                                      : diff > 0
                                        ? PROFIT_COLOR
                                        : LOSS_COLOR
                                  const diffText =
                                    diff === null
                                      ? '-'
                                      : `${diff > 0 ? '+' : ''}${formatParamValue(key, diff)}`

                                  return (
                                    <tr key={key} className={isAlreadyApplied ? 'bg-green-50/40' : ''}>
                                      <td className="px-3 py-2">
                                        <input
                                          type="checkbox"
                                          checked={!checkboxDisabled && isChecked}
                                          disabled={checkboxDisabled}
                                          onChange={() => toggleKey(rec.id, key)}
                                          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                                        />
                                      </td>
                                      <td className="px-3 py-2">
                                        <div className="flex items-center gap-2">
                                          <span className="text-gray-800 inline-flex items-center">
                                            {label}
                                            {meta?.description && (
                                              <InfoTooltip content={meta.description} ariaLabel={`${label} 설명`} />
                                            )}
                                          </span>
                                          {isAlreadyApplied && (
                                            <span className="px-1.5 py-0.5 text-[10px] bg-green-100 text-green-700 rounded">
                                              적용됨
                                            </span>
                                          )}
                                        </div>
                                      </td>
                                      <td className="px-3 py-2 text-right font-mono text-gray-700">
                                        {hasCurrent ? formatParamValue(key, currentValue as number) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-center text-gray-400">→</td>
                                      <td className="px-3 py-2 text-right font-mono font-medium text-gray-900">
                                        {formatParamValue(key, recommendedValue)}
                                      </td>
                                      <td
                                        className="px-3 py-2 text-right font-mono text-xs"
                                        style={{ color: diffColor }}
                                      >
                                        {diffText}
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>

                      {/* 적용/거절 시각 */}
                      {(rec.applied_at || rec.rejected_at) && (
                        <div className="text-xs text-gray-400 mb-3">
                          {rec.applied_at && <span>적용 시각: {formatDateTime(rec.applied_at)}</span>}
                          {rec.applied_at && rec.rejected_at && <span className="mx-2">·</span>}
                          {rec.rejected_at && <span>거절 시각: {formatDateTime(rec.rejected_at)}</span>}
                        </div>
                      )}

                      {/* 에러 */}
                      {error && (
                        <div className="p-3 mb-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                          {error}
                        </div>
                      )}

                      {/* 버튼 — 액션 가능 자문에서만 노출 */}
                      {actionable && (() => {
                        const weightCheck = !!weightApplyMap[rec.id]
                        const applyDisabled =
                          checkedSelectable.length === 0 && !weightCheck || applyMutation.isPending
                        return (
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => setRejectTarget(rec)}
                              disabled={rec.status !== 'pending' || rejectMutation.isPending}
                              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              전체 거절
                            </button>
                            <button
                              onClick={() => setApplyTarget(rec)}
                              disabled={applyDisabled}
                              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              선택 항목 적용
                              {(checkedSelectable.length > 0 || weightCheck) && (
                                <>
                                  {' '}({checkedSelectable.length}
                                  {weightCheck && '+w'})
                                </>
                              )}
                            </button>
                          </div>
                        )
                      })()}
                    </div>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}

      <ConfirmModal
        open={applyTarget !== null}
        title="AI 자문 적용"
        message={(() => {
          if (!applyTarget) return ''
          const paramCount = selectedKeys[applyTarget.id]?.size ?? 0
          const weightOn = !!weightApplyMap[applyTarget.id]
          const parts: string[] = []
          if (paramCount > 0) parts.push(`${paramCount}개 파라미터`)
          if (weightOn) parts.push('weight')
          if (parts.length === 0) return '적용할 항목이 없습니다.'
          return `${parts.join(' + ')}을(를) 적용하시겠습니까? 파라미터는 다음 스캔, weight 는 다음 영업일부터 반영됩니다.`
        })()}
        onConfirm={() => {
          if (!applyTarget) return
          const keys = Array.from(selectedKeys[applyTarget.id] ?? [])
          const applyWeight = !!weightApplyMap[applyTarget.id]
          if (keys.length === 0 && !applyWeight) {
            setApplyTarget(null)
            return
          }
          applyMutation.mutate({ id: applyTarget.id, keys, applyWeight })
        }}
        onCancel={() => setApplyTarget(null)}
        loading={applyMutation.isPending}
      />

      <ConfirmModal
        open={rejectTarget !== null}
        title="AI 자문 거절"
        message={
          rejectTarget
            ? `${strategyNameMap[rejectTarget.strategy_id] ?? rejectTarget.strategy_id} 전략의 자문을 모두 거절하시겠습니까?`
            : ''
        }
        onConfirm={() => {
          if (!rejectTarget) return
          rejectMutation.mutate(rejectTarget.id)
        }}
        onCancel={() => setRejectTarget(null)}
        loading={rejectMutation.isPending}
      />
    </div>
  )
}
