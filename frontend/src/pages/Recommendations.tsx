import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listRecommendations, applyRecommendation, rejectRecommendation } from '../api/recommendations'
import { getStrategies } from '../api/trading'
import { getStrategyColor } from '../types/strategy'
import { PARAM_LABELS, formatParamValue } from '../utils/paramLabels'
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

export default function Recommendations() {
  const queryClient = useQueryClient()
  const [selectedKeys, setSelectedKeys] = useState<Record<string, Set<string>>>({})
  const [applyTarget, setApplyTarget] = useState<RecommendationItem | null>(null)
  const [rejectTarget, setRejectTarget] = useState<RecommendationItem | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})

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
    mutationFn: ({ id, keys }: { id: string; keys: string[] }) => applyRecommendation(id, keys),
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

  // target_date 데스크 정렬 + strategy_id 정렬
  const grouped = useMemo(() => {
    const list = items ?? []
    const byDate: Record<string, RecommendationItem[]> = {}
    for (const it of list) {
      if (!byDate[it.target_date]) byDate[it.target_date] = []
      byDate[it.target_date].push(it)
    }
    const dates = Object.keys(byDate).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0))
    return dates.map((d) => ({
      date: d,
      items: byDate[d].slice().sort((a, b) => a.strategy_id.localeCompare(b.strategy_id)),
    }))
  }, [items])

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
        <h1 className="text-2xl font-bold text-gray-900 mb-6">파라미터 추천</h1>
        <div className="p-6 text-gray-500">추천 정보를 불러오는 중...</div>
      </div>
    )
  }

  if (isError) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">파라미터 추천</h1>
        <div className="p-6 text-red-500">추천 정보를 불러올 수 없습니다.</div>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">파라미터 추천</h1>

      {/* 안내 */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <p className="text-sm text-blue-800">
          매일 장마감 후 16:00에 자동 생성됩니다. 전략별로 권고된 파라미터 중 원하는 항목만 선택해 적용할 수 있습니다.
        </p>
      </div>

      {grouped.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          아직 생성된 추천이 없습니다.
          <br />
          <span className="text-sm">오늘 16:00에 첫 추천이 생성됩니다.</span>
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
                                          <span className="text-gray-800">{label}</span>
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

                      {/* 버튼 */}
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
                          disabled={
                            !actionable ||
                            checkedSelectable.length === 0 ||
                            applyMutation.isPending
                          }
                          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          선택 항목 적용
                          {checkedSelectable.length > 0 && ` (${checkedSelectable.length})`}
                        </button>
                      </div>
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
        title="파라미터 추천 적용"
        message={
          applyTarget
            ? `선택한 ${(selectedKeys[applyTarget.id]?.size ?? 0)}개 파라미터를 적용하시겠습니까? 다음 스캔부터 반영됩니다.`
            : ''
        }
        onConfirm={() => {
          if (!applyTarget) return
          const keys = Array.from(selectedKeys[applyTarget.id] ?? [])
          if (keys.length === 0) {
            setApplyTarget(null)
            return
          }
          applyMutation.mutate({ id: applyTarget.id, keys })
        }}
        onCancel={() => setApplyTarget(null)}
        loading={applyMutation.isPending}
      />

      <ConfirmModal
        open={rejectTarget !== null}
        title="추천 거절"
        message={
          rejectTarget
            ? `${strategyNameMap[rejectTarget.strategy_id] ?? rejectTarget.strategy_id} 전략의 추천을 모두 거절하시겠습니까?`
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
