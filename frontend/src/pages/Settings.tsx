import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getStrategies, updateStrategyWeights, updateStrategyParams } from '../api/trading'
import apiClient from '../api/client'
import { getStrategyColor } from '../types/strategy'
import ConfirmModal from '../components/ConfirmModal'
import InfoTooltip from '../components/InfoTooltip'
import { PARAM_LABELS, formatParamValue } from '../utils/paramLabels'
import { STRATEGY_INFO } from '../utils/strategyInfo'

export default function Settings() {
  const queryClient = useQueryClient()
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [showConfirm, setShowConfirm] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [editingParams, setEditingParams] = useState<string | null>(null) // strategy key
  const [paramEdits, setParamEdits] = useState<Record<string, string>>({})
  const [paramDirty, setParamDirty] = useState(false)
  const [showParamConfirm, setShowParamConfirm] = useState(false)
  const [weightError, setWeightError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['strategies'],
    queryFn: getStrategies,
  })

  const weightMutation = useMutation({
    mutationFn: updateStrategyWeights,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setShowConfirm(false)
      setDirty(false)
      setWeightError(null)
    },
    onError: (err: Error) => {
      setShowConfirm(false)
      setWeightError(err.message)
    },
  })

  const paramMutation = useMutation({
    mutationFn: ({ id, params }: { id: string; params: Record<string, number> }) =>
      updateStrategyParams(id, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setShowParamConfirm(false)
      setParamDirty(false)
      setEditingParams(null)
    },
    onError: () => setShowParamConfirm(false),
  })

  useEffect(() => {
    if (data?.strategies) {
      const w: Record<string, number> = {}
      const totalW = data.strategies.reduce((sum, s) => sum + s.weight, 0)
      for (const s of data.strategies) {
        w[s.key] = totalW <= 1.01 ? Math.round(s.weight * 100) : Math.round(s.weight)
      }
      setWeights(w)
      setDirty(false)
    }
  }, [data])

  if (isLoading) return <div className="p-6 text-gray-500">설정 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">설정을 불러올 수 없습니다.</div>
  if (!data) return null

  const strategies = data.strategies
  const totalWeight = Object.values(weights).reduce((sum, w) => sum + w, 0)

  const handleWeightChange = (key: string, value: number) => {
    setWeights((prev) => {
      const next = { ...prev, [key]: value }
      const otherKeys = Object.keys(next).filter((k) => k !== key)
      const otherTotal = otherKeys.reduce((sum, k) => sum + next[k], 0)
      const overflow = value + otherTotal - 100
      if (overflow > 0 && otherTotal > 0) {
        for (const k of otherKeys) {
          const ratio = next[k] / otherTotal
          next[k] = Math.max(0, Math.round(next[k] - overflow * ratio))
        }
      }
      return next
    })
    setDirty(true)
  }

  const handleSaveWeights = () => {
    const normalized: Record<string, number> = {}
    if (totalWeight > 0) {
      for (const [key, w] of Object.entries(weights)) {
        normalized[key] = Math.round((w / totalWeight) * 100)
      }
    }
    weightMutation.mutate(normalized)
  }

  const openParamEditor = (strategyKey: string, params: Record<string, unknown>) => {
    const editable: Record<string, string> = {}
    for (const [k, v] of Object.entries(params)) {
      if (typeof v === 'number' && k in PARAM_LABELS) {
        editable[k] = String(v)
      }
    }
    setParamEdits(editable)
    setEditingParams(strategyKey)
    setParamDirty(false)
  }

  const handleParamChange = (key: string, value: string) => {
    setParamEdits((prev) => ({ ...prev, [key]: value }))
    setParamDirty(true)
  }

  const handleSaveParams = () => {
    if (!editingParams) return
    const parsed: Record<string, number> = {}
    for (const [k, v] of Object.entries(paramEdits)) {
      const n = Number(v)
      if (Number.isFinite(n)) parsed[k] = n
    }
    paramMutation.mutate({ id: editingParams, params: parsed })
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">설정</h1>

      {/* 자동 매매 시작 */}
      <AutoStartToggle />

      {/* 전략별 운영시각 */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">전략별 운영시각</h2>
        <div className="space-y-2">
          {strategies.map((s) => {
            const color = getStrategyColor(s.key)
            const isVB = s.key === 'volatility_breakout'
            const isLTV = s.key === 'long_tail_volatility'
            const isDS = s.key === 'donchian_swing'
            return (
              <div key={s.key} className="flex items-center justify-between p-3 bg-gray-50 rounded">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color.hex }} />
                  <span className="text-sm font-medium text-gray-700 inline-flex items-center">
                    {s.name}
                    {STRATEGY_INFO[s.key] && (
                      <InfoTooltip
                        content={`${STRATEGY_INFO[s.key].tagline}\n\n${STRATEGY_INFO[s.key].description}`}
                        ariaLabel={`${s.name} 전략 설명`}
                      />
                    )}
                  </span>
                </div>
                <div className="text-sm text-gray-600">
                  {isVB ? (
                    <span>NXT 프리 08:00 / KRX 메인 09:00:05 / NXT 애프터 15:30~19:50 <span className="text-xs text-gray-400 ml-1">(보드별 시가·K값 분리)</span></span>
                  ) : isLTV ? (
                    <span>NXT 프리 08:00 / KRX 메인 09:00:05 / NXT 애프터 15:30~19:50 <span className="text-xs text-gray-400 ml-1">(상한가 도달 시 다음 영업일 NXT 08:00 청산)</span></span>
                  ) : isDS ? (
                    <span>09:05 ~ 추세 종료 <span className="text-xs text-gray-400 ml-1">(KRX 메인만, 멀티데이 ATR 트레일링)</span></span>
                  ) : (
                    <span>09:30 ~ 15:20 <span className="text-xs text-gray-400 ml-1">(KRX 메인, 익일 NXT 프리 08:00 청산)</span></span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        <p className="text-xs text-gray-400 mt-3">
          자동 시작 07:45 / 부트 07:50 / NXT 프리 08:00 / KRX 메인 09:00 / KRX 마감 15:30 / NXT 애프터 종료 20:00 / 정산 20:10
        </p>
      </div>

      {/* 비중 관리 */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">전략 비중</h2>

        {strategies.length === 0 ? (
          <p className="text-gray-500">등록된 전략이 없습니다.</p>
        ) : (
          <>
            <div className="mb-6 p-4 bg-gray-50 rounded-lg">
              <div className="flex h-6 rounded-full overflow-hidden bg-gray-200">
                {strategies.map((s) => {
                  const pct = totalWeight > 0 ? ((weights[s.key] ?? 0) / totalWeight) * 100 : 0
                  const color = getStrategyColor(s.key)
                  if (pct <= 0) return null
                  return (
                    <div
                      key={s.key}
                      className="flex items-center justify-center text-white text-xs font-medium transition-all duration-300"
                      style={{ width: `${pct}%`, backgroundColor: color.hex, minWidth: pct > 0 ? '2rem' : 0 }}
                    >
                      {pct >= 15 ? `${pct.toFixed(0)}%` : ''}
                    </div>
                  )
                })}
              </div>
              <div className="flex gap-4 mt-2">
                {strategies.map((s) => {
                  const color = getStrategyColor(s.key)
                  const pct = totalWeight > 0 ? ((weights[s.key] ?? 0) / totalWeight) * 100 : 0
                  return (
                    <div key={s.key} className="flex items-center gap-1.5 text-xs">
                      <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: color.hex }} />
                      <span className="text-gray-600">{s.name} ({pct.toFixed(0)}%)</span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="space-y-4">
              {strategies.map((s) => {
                const color = getStrategyColor(s.key)
                const w = weights[s.key] ?? 0
                const minW = s.min_weight ?? 0
                const invested = s.invested_amount ?? 0
                return (
                  <div key={s.key}>
                    <div className="flex items-center gap-4">
                      <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: color.hex }} />
                      <span className="text-sm font-medium w-28 shrink-0">{s.name}</span>
                      <div className="flex-1 relative">
                        <input
                          type="range"
                          min={0}
                          max={100}
                          value={w}
                          onChange={(e) => {
                            handleWeightChange(s.key, Number(e.target.value))
                            setWeightError(null)
                          }}
                          className="w-full h-2 rounded-lg appearance-none cursor-pointer"
                          style={{ accentColor: color.hex }}
                        />
                        {minW > 0 && (
                          <div
                            className="absolute top-4 h-2 border-l-2 border-red-400"
                            style={{ left: `${minW}%` }}
                            title={`하한선 ${minW}% (매수금액 ${(invested / 10000).toFixed(0)}만원)`}
                          >
                            <span className="absolute -top-0.5 left-1 text-[10px] text-red-400 whitespace-nowrap">
                              {minW}%
                            </span>
                          </div>
                        )}
                      </div>
                      <span className="text-sm font-mono font-medium w-12 text-right">{w}%</span>
                    </div>
                    {minW > 0 && (
                      <div className="ml-[calc(0.75rem+1rem+7rem+1rem)] text-[11px] text-gray-400 mt-0.5">
                        매수 중 {(invested / 10000).toFixed(0)}만원 — 최소 {minW}%
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {weightError && (
              <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {weightError}
              </div>
            )}

            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowConfirm(true)}
                disabled={!dirty}
                className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                비중 저장
              </button>
            </div>
          </>
        )}
      </div>

      {/* 전략별 파라미터 */}
      <div className="space-y-4">
        {strategies.map((s) => {
          const color = getStrategyColor(s.key)
          const isEditing = editingParams === s.key
          const params = (s as unknown as { params?: Record<string, unknown> }).params ?? {}
          const editableKeys = Object.keys(params).filter((k) => k in PARAM_LABELS && typeof params[k] === 'number')

          if (editableKeys.length === 0) return null

          return (
            <div key={s.key} className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color.hex }} />
                  <h2 className="text-lg font-semibold text-gray-900">{s.name} 파라미터</h2>
                </div>
                {!isEditing && (
                  <button
                    onClick={() => openParamEditor(s.key, params)}
                    className="px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded-md"
                  >
                    편집
                  </button>
                )}
              </div>

              {isEditing ? (
                <div className="space-y-3">
                  {editableKeys.map((key) => {
                    const meta = PARAM_LABELS[key]
                    const rawValue = paramEdits[key] ?? '0'
                    const numValue = Number(rawValue)
                    const safeNum = Number.isFinite(numValue) ? numValue : 0
                    const totalInv = s.total_investment ?? 0
                    return (
                      <div key={key}>
                        <div className="flex items-center gap-4">
                          <span className="text-sm text-gray-600 w-40 shrink-0 inline-flex items-center">
                            <label>{meta.label}</label>
                            <InfoTooltip content={meta.description} ariaLabel={`${meta.label} 설명`} />
                          </span>
                          <input
                            type="text"
                            inputMode="decimal"
                            value={rawValue}
                            onChange={(e) => handleParamChange(key, e.target.value)}
                            className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                          <span className="text-xs text-gray-400 w-8">{meta.unit}</span>
                        </div>
                        {key === 'position_ratio' && totalInv > 0 && (
                          <div className="ml-44 mt-1 text-xs text-gray-400">
                            예상 종목당 매수: ~{((totalInv * safeNum) / 10000).toFixed(0)}만원
                            (할당금 {(totalInv / 10000).toFixed(0)}만원 x {(safeNum * 100).toFixed(0)}%)
                          </div>
                        )}
                      </div>
                    )
                  })}
                  <div className="flex justify-end gap-2 mt-4">
                    <button
                      onClick={() => { setEditingParams(null); setParamDirty(false) }}
                      className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md"
                    >
                      취소
                    </button>
                    <button
                      onClick={() => setShowParamConfirm(true)}
                      disabled={!paramDirty}
                      className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      저장
                    </button>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {editableKeys.map((key) => {
                    const meta = PARAM_LABELS[key]
                    const value = params[key] as number
                    const totalInv = s.total_investment ?? 0
                    return (
                      <div key={key}>
                        <div className="flex justify-between text-sm py-1">
                          <span className="text-gray-500 inline-flex items-center">
                            {meta.label}
                            <InfoTooltip content={meta.description} ariaLabel={`${meta.label} 설명`} />
                          </span>
                          <span className="font-medium">{formatParamValue(key, value)}{meta.unit && !formatParamValue(key, value).includes(meta.unit) ? meta.unit : ''}</span>
                        </div>
                        {key === 'position_ratio' && totalInv > 0 && (
                          <div className="col-span-2 text-xs text-gray-400 -mt-0.5 mb-1">
                            예상 종목당 매수: ~{((totalInv * value) / 10000).toFixed(0)}만원
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <ConfirmModal
        open={showConfirm}
        title="전략 비중 변경"
        message="전략 비중을 변경하시겠습니까? 변경된 비중은 즉시 적용됩니다."
        onConfirm={handleSaveWeights}
        onCancel={() => setShowConfirm(false)}
        loading={weightMutation.isPending}
      />
      <ConfirmModal
        open={showParamConfirm}
        title="파라미터 변경"
        message="전략 파라미터를 변경하시겠습니까? 다음 스캔부터 적용됩니다."
        onConfirm={handleSaveParams}
        onCancel={() => setShowParamConfirm(false)}
        loading={paramMutation.isPending}
      />
    </div>
  )
}

function AutoStartToggle() {
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ['autoStart'],
    queryFn: async () => {
      const { data } = await apiClient.get('/strategies/system/auto-start')
      return data.data?.auto_start ?? false
    },
  })

  const mutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      await apiClient.put('/strategies/system/auto-start', { enabled })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['autoStart'] }),
  })

  const enabled = data ?? false

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">자동 매매 시작</h2>
          <p className="text-sm text-gray-500 mt-1">
            활성화 시 매일 08:20에 자동으로 매매를 시작합니다. 주말은 자동 건너뜁니다.
          </p>
        </div>
        <button
          onClick={() => mutation.mutate(!enabled)}
          disabled={mutation.isPending}
          className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
            enabled ? 'bg-green-500' : 'bg-gray-300'
          } ${mutation.isPending ? 'opacity-50' : ''}`}
        >
          <span
            className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
              enabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>
      {enabled && (
        <div className="mt-3 px-3 py-2 bg-green-50 border border-green-200 rounded text-sm text-green-700">
          서버 재시작 후에도 자동 매매가 유지됩니다.
        </div>
      )}
    </div>
  )
}
