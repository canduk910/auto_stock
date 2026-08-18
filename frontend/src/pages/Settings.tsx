import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getStrategies, updateStrategyWeights, updateStrategyParams } from '../api/trading'
import type { StrategyParamValue } from '../api/trading'
import apiClient from '../api/client'
import { getStrategyColor } from '../types/strategy'
import CashUsageRatioCard from '../components/CashUsageRatioCard'
import IntegrationToggleCard from '../components/IntegrationToggleCard'
import KisQuoteAccountsCard from '../components/KisQuoteAccountsCard'
import KrxOpenApiCard from '../components/KrxOpenApiCard'
import PriceFilterCard from '../components/PriceFilterCard'
import TradeAmountFilterCard from '../components/TradeAmountFilterCard'
import ConfirmModal from '../components/ConfirmModal'
import InfoTooltip from '../components/InfoTooltip'
import { PARAM_LABELS, formatParamValue } from '../utils/paramLabels'
import { STRATEGY_INFO } from '../utils/strategyInfo'
import { useTradingStatus } from '../contexts/TradingStatusContext'

const EXCHANGE_OPTIONS: { value: string; label: string; description: string }[] = [
  { value: 'KRX', label: 'KRX', description: '한국거래소 단일 — 안전, 모의(VTS)도 지원' },
  { value: 'NXT', label: 'NXT', description: '넥스트레이드 ATS 단일 — 실전 한정' },
  { value: 'SOR', label: 'SOR', description: 'Smart Order Routing — KIS가 KRX/NXT에 자동 분배 (실전 한정)' },
]

const BOARD_OPTIONS: { value: string; label: string; hint: string }[] = [
  { value: 'pre_nxt', label: 'NXT 프리 (08:00~)', hint: 'NXT 프리마켓 — 거래대금 작아 변동성 큼' },
  { value: 'krx_open', label: 'KRX 동시호가 (08:30~09:00)', hint: 'KRX 장전 동시호가' },
  { value: 'main', label: 'KRX 메인 (09:00~15:20)', hint: 'KRX 정규장 — 핵심 매매 시간대' },
  { value: 'krx_after', label: 'KRX 시간외 단일가 (15:30~18:00)', hint: 'KRX 시간외 — 현재 미사용' },
  { value: 'post_nxt', label: 'NXT 애프터 (15:30~20:00) 🌃', hint: '야간 매매 — 사용자 부재 시간대 사고 위험' },
]

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
    retry: 1,  // 사이클 80 hotfix — 사이클 65 H1 답습 + 사이클 79 e2e flaky 영구 차단
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
    mutationFn: ({ id, params }: { id: string; params: Record<string, StrategyParamValue> }) =>
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
      // 백엔드는 항상 비율(0~1)을 준다 (strategy_registry.get_strategies_status).
      // 합계로 단위를 추론하던 종전 분기는 오염 시에만 깨어나 유효숫자를 파괴하고
      // "3개 전략 균등분배" 화면으로 결함을 위장했다 (2026-08-18 폐기).
      for (const s of data.strategies) {
        w[s.key] = Math.round(s.weight * 100)
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
  // 배너·저장차단 판정은 **서버 저장값(비율)** 기준. 편집 중 퍼센트 합(totalWeight)을 쓰면
  // (a) 슬라이더를 내리는 정상 편집과 (b) 4dp 비율 → 정수% 반올림 누적오차(전략 n개면 최대 ±n/2 %p)를
  // 오염으로 오인한다. 실제 오염 시그니처는 "저장된 비율의 합"이다.
  // ⚠️ overflow 임계는 `serverWeightSum - 1 > 0.01` 형태로만 쓴다 — 동치인 상수 리터럴 형태는
  //    AST 가드(_ast_weight_unit_guard)가 단위 추론 휴리스틱 부활로 간주해 금지한다.
  const serverWeightSum = strategies.reduce((sum, s) => sum + (s.weight ?? 0), 0)
  const serverWeightPct = Math.round(serverWeightSum * 100)
  const weightSumAbnormal = strategies.length > 0 && Math.abs(serverWeightSum - 1) > 0.01
  const weightSumOverflow = strategies.length > 0 && serverWeightSum - 1 > 0.01
  // 가용금액 슬라이더 노출용 — 전략별 total_investment 합산 (registry.allocate_funds 결과).
  // 정확한 순자산은 `/api/balance::summary.net_asset` 이지만 Settings 페이지에서 새 API 호출을
  // 추가하지 않고 이미 fetch 한 strategies 응답으로 추정. 0 이면 카드는 카드만 표시.
  const netAssetEstimate = strategies.reduce(
    (sum, s) => sum + (s.total_investment ?? 0),
    0,
  )

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
    // 백엔드 계약: 비율(0.0~1.0). 퍼센트 송신 금지 (2026-08-18)
    const normalized: Record<string, number> = {}
    if (totalWeight > 0) {
      const keys = Object.keys(weights)
      for (const key of keys) {
        normalized[key] = Number((weights[key] / totalWeight).toFixed(4))
      }
      // 반올림 잔차를 최대 항목에 흡수 — Σ === 1.0 보장 (백엔드 Σ≤1.0 가드 정합)
      const sum = keys.reduce((acc, k) => acc + normalized[k], 0)
      const residual = Number((1 - sum).toFixed(4))
      if (residual !== 0) {
        const maxKey = keys.reduce((a, b) => (normalized[b] > normalized[a] ? b : a), keys[0])
        normalized[maxKey] = Number((normalized[maxKey] + residual).toFixed(4))
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

      {/* 야간 매매(POST_NXT) 활성 경고 — VB/LTV 중 하나라도 post_nxt 활성이면 표시 */}
      {strategies.some((s) => {
        const params = (s as unknown as { params?: Record<string, unknown> }).params ?? {}
        const tb = (params.tradable_boards as string[] | undefined) ?? []
        return s.enabled && tb.includes('post_nxt')
      }) && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-6 flex items-start gap-3">
          <span className="text-2xl">🌃</span>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-amber-900">야간 매매(NXT 애프터 15:30~20:00) 활성</h3>
            <p className="text-xs text-amber-800 mt-1">
              사용자 부재 시간대에 매매가 일어날 수 있습니다. 손절·트레일링은 실시간 작동하지만 NXT 거래대금이 KRX 대비 작아 변동성이 큽니다.
              비활성화하려면 해당 전략의 매매 가능 보드에서 <strong>NXT 애프터</strong>를 해제하세요.
            </p>
          </div>
        </div>
      )}

      {/* 전략별 거래소·매매 보드 */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">전략별 거래소·매매 보드</h2>
        <p className="text-xs text-gray-500 mb-4">
          주문은 선택한 거래소(`EXCG_ID_DVSN_CD`)로 전송됩니다. 매매 가능 보드는 RiskManager에서 보드 가드로 동작 — 비활성 보드에서는 매수 신호 평가 자체가 차단됩니다.
        </p>
        <div className="space-y-3">
          {strategies.map((s) => (
            <ExchangeBoardRow key={s.key} strategy={s} />
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-3">
          자동 시작 07:45 / 부트 07:50 / NXT 프리 08:00 / KRX 메인 09:00 / KRX 마감 15:30 / NXT 애프터 종료 20:00 / 정산 20:10
          · <strong>VTS(모의)는 KRX만 지원</strong> — NXT/SOR는 실전 한정
        </p>
      </div>

      {/* 비중 관리 */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">전략 비중</h2>

        {strategies.length === 0 ? (
          <p className="text-gray-500">등록된 전략이 없습니다.</p>
        ) : (
          <>
            {weightSumAbnormal && (
              <div
                data-testid="weight-sum-warning"
                className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700"
              >
                {weightSumOverflow
                  ? `저장된 비중 합이 100%를 초과합니다 (현재 ${serverWeightPct}%). 비중 값이 오염된 상태입니다 — 화면에서 저장하면 잘못된 비율이 그대로 굳으니, 운영 DB 에서 직접 정정하세요.`
                  : `저장된 비중 합이 100%가 아닙니다 (현재 ${serverWeightPct}%). 값을 확인한 뒤 저장하세요.`}
              </div>
            )}

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
                // 오염(Σ>1) 상태에서는 저장 차단 — 저장하면 handleWeightChange 의 overflow 재분배가
                // 오염 비율을 보존한 채 Σ=1.0 으로 정규화해 백엔드 오염 탐지기를 영구 침묵시킨다.
                // Σ<1 은 차단하지 않는다(운영자 고립 방지).
                disabled={!dirty || weightSumOverflow}
                className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                비중 저장
              </button>
            </div>
          </>
        )}
      </div>

      {/* J3 (2026-05-12) — 매매 가용 자금 비율 */}
      <CashUsageRatioCard netAsset={netAssetEstimate > 0 ? netAssetEstimate : undefined} />

      {/* 사이클 5 (2026-05-17) — 외부 통합 토글 (dkstock-regime / kis-mcp / auto-regime-adjust) */}
      <IntegrationToggleCard />

      {/* 사이클 7-D (2026-05-18) — 보조 KIS 시세 계좌 관리 */}
      <KisQuoteAccountsCard />

      {/* 사이클 112 (2026-06-12) — KRX 정식 OPEN API 키 관리 (인프라 사전 구성) */}
      <KrxOpenApiCard />

      {/* 사이클 62 (2026-06-05) — 가격 필터 (매수 진입 전용) */}
      {/* 사이클 64 (2026-06-06) — WebSocket 구독 대상 필터 단순화 */}
      <PriceFilterCard />

      {/* 사이클 65 (2026-06-06) — 거래대금 동행 필터 (WebSocket 구독 대상 필터 순차 hook) */}
      <TradeAmountFilterCard />

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

type StrategyRowProps = {
  strategy: {
    key: string
    name: string
    enabled: boolean
    params?: Record<string, unknown>
  }
}

function ExchangeBoardRow({ strategy }: StrategyRowProps) {
  const queryClient = useQueryClient()
  const { data: status } = useTradingStatus()
  const isVts = status?.env !== 'real'   // 실전이 아니면 모의로 간주 (보수적)
  const params = strategy.params ?? {}
  const initialExchange = ((params.exchange as string) ?? 'KRX').toUpperCase()
  const initialBoards = ((params.tradable_boards as string[] | undefined) ?? []) as string[]

  const [exchange, setExchange] = useState(initialExchange)
  const [boards, setBoards] = useState<string[]>(initialBoards)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)

  const color = getStrategyColor(strategy.key)
  const dirty = exchange !== initialExchange || !sameSet(boards, initialBoards)

  const mutation = useMutation({
    mutationFn: (next: Record<string, StrategyParamValue>) =>
      updateStrategyParams(strategy.key, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setEditing(false)
      setConfirm(false)
      setError(null)
    },
    onError: (err: Error) => {
      setError(err.message)
      setConfirm(false)
    },
  })

  const toggleBoard = (b: string) => {
    setBoards((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]))
  }

  const onSave = () => {
    if (boards.length === 0) {
      setError('최소 1개 이상의 매매 보드를 선택해야 합니다.')
      setConfirm(false)
      return
    }
    if (isVts && exchange !== 'KRX') {
      setError(`모의(VTS) 환경에서는 ${exchange}를 선택할 수 없습니다. KRX만 가능합니다.`)
      setConfirm(false)
      return
    }
    mutation.mutate({ exchange, tradable_boards: boards })
  }

  const exchangeNote = (() => {
    if (exchange === 'KRX') return null
    if (isVts) {
      return (
        <span className="text-xs text-red-700">⛔ 현재 모의(VTS) 환경 — {exchange} 주문은 KIS가 거절합니다. KRX로 변경하세요</span>
      )
    }
    return (
      <span className="text-xs text-amber-700">⚠️ {exchange} 주문은 실전 환경에서만 동작 — 모의(VTS)에서는 거절됩니다</span>
    )
  })()

  return (
    <div className="border border-gray-200 rounded p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color.hex }} />
          <span className="text-sm font-medium text-gray-800 inline-flex items-center">
            {strategy.name}
            {STRATEGY_INFO[strategy.key] && (
              <InfoTooltip
                content={`${STRATEGY_INFO[strategy.key].tagline}\n\n${STRATEGY_INFO[strategy.key].description}`}
                ariaLabel={`${strategy.name} 전략 설명`}
              />
            )}
          </span>
          {!strategy.enabled && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">비활성</span>
          )}
        </div>
        {!editing ? (
          <button
            onClick={() => setEditing(true)}
            className="px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-50 rounded"
          >
            편집
          </button>
        ) : (
          <div className="flex gap-1">
            <button
              onClick={() => {
                setExchange(initialExchange)
                setBoards(initialBoards)
                setEditing(false)
                setError(null)
              }}
              className="px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100 rounded"
            >
              취소
            </button>
            <button
              onClick={() => setConfirm(true)}
              disabled={!dirty}
              className="px-2 py-0.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              저장
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          {/* 거래소 라디오 — 모의(vts) 환경에선 NXT/SOR 차단 */}
          <div>
            <div className="text-xs font-medium text-gray-700 mb-1">거래소 (EXCG_ID_DVSN_CD)</div>
            <div className="flex gap-2">
              {EXCHANGE_OPTIONS.map((opt) => {
                const blocked = isVts && opt.value !== 'KRX'
                const checked = exchange === opt.value
                return (
                  <label
                    key={opt.value}
                    className={`flex-1 px-2 py-1.5 text-xs border rounded ${
                      blocked
                        ? 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed opacity-60'
                        : checked
                          ? 'border-blue-500 bg-blue-50 text-blue-700 cursor-pointer'
                          : 'border-gray-200 text-gray-700 hover:bg-gray-50 cursor-pointer'
                    }`}
                    title={blocked ? `모의(VTS)에서는 ${opt.label} 선택 불가 — KIS가 거절합니다` : opt.description}
                  >
                    <input
                      type="radio"
                      name={`exchange-${strategy.key}`}
                      value={opt.value}
                      checked={checked}
                      onChange={() => !blocked && setExchange(opt.value)}
                      disabled={blocked}
                      className="mr-1"
                    />
                    <strong>{opt.label}</strong>
                    {blocked && <span className="text-[10px] ml-1">(모의 불가)</span>}
                    <div className="text-[10px] text-gray-500 mt-0.5">{opt.description}</div>
                  </label>
                )
              })}
            </div>
            {exchangeNote && <div className="mt-1">{exchangeNote}</div>}
          </div>

          {/* 매매 가능 보드 체크박스 */}
          <div>
            <div className="text-xs font-medium text-gray-700 mb-1">매매 가능 보드 (tradable_boards)</div>
            <div className="grid grid-cols-1 gap-1">
              {BOARD_OPTIONS.map((opt) => {
                const checked = boards.includes(opt.value)
                const isPostNxt = opt.value === 'post_nxt'
                return (
                  <label
                    key={opt.value}
                    className={`flex items-center gap-2 px-2 py-1 text-xs border rounded cursor-pointer ${
                      checked
                        ? isPostNxt
                          ? 'border-amber-500 bg-amber-50'
                          : 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleBoard(opt.value)}
                    />
                    <span className="font-medium text-gray-800">{opt.label}</span>
                    <span className="text-[11px] text-gray-500">— {opt.hint}</span>
                  </label>
                )
              })}
            </div>
          </div>
          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
              {error}
            </div>
          )}
        </div>
      ) : (
        <div className="text-xs text-gray-600 flex items-center flex-wrap gap-2">
          <span>
            거래소: <strong className="text-gray-800">{initialExchange}</strong>
          </span>
          <span className="text-gray-300">|</span>
          <span>매매 보드:</span>
          {initialBoards.length > 0 ? (
            initialBoards.map((b) => {
              const opt = BOARD_OPTIONS.find((o) => o.value === b)
              const isPostNxt = b === 'post_nxt'
              return (
                <span
                  key={b}
                  className={`px-1.5 py-0.5 rounded ${
                    isPostNxt ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'
                  }`}
                >
                  {opt?.label.replace(/\(.*\)/, '').trim() ?? b}
                </span>
              )
            })
          ) : (
            <span className="text-gray-400">없음 — 매매 비활성</span>
          )}
        </div>
      )}

      <ConfirmModal
        open={confirm}
        title="거래소·보드 변경"
        message={`${strategy.name}의 거래소를 ${exchange}로, 매매 보드를 ${boards.join(', ') || '(없음)'}으로 변경합니다. 다음 매매 평가부터 적용됩니다.`}
        onConfirm={onSave}
        onCancel={() => setConfirm(false)}
        loading={mutation.isPending}
      />
    </div>
  )
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  const bs = new Set(b)
  return a.every((x) => bs.has(x))
}

function AutoStartToggle() {
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ['autoStart'],
    queryFn: async () => {
      const { data } = await apiClient.get('/strategies/system/auto-start')
      return data.data?.auto_start ?? false
    },
    retry: 1,  // 사이클 80 hotfix — 사이클 65 H1 답습
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
            활성화 시 매일 07:45에 자동으로 매매를 시작합니다. 주말·공휴일은 자동 건너뜁니다(KIS chk-holiday).
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
