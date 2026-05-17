/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 카드.
 *
 * 3 토글 통합 (운영자 시야 집중을 위해 단일 카드 + 분리 행):
 * - dkstock-regime: 매크로 레짐 fetch (활성화 시 백그라운드 fetch trigger)
 * - kis-mcp: 외부 백테스트 서버 (자문 시점에만 사용)
 * - auto-regime-adjust: 매크로 레짐 → cash_usage_ratio 자동 갱신
 *
 * 핵심 안전 원칙:
 * - DB 값 != null → DB 사용 (source='db'), null → .env fallback (source='env')
 * - ConfirmModal 이중 확인 (특히 dkstock-regime 활성화는 매수 가드 영향)
 * - 활성화 즉시 fetch 는 백그라운드 — API 응답은 즉시 반환
 * - 비활성 시 안내 메시지로 차단
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getAutoRegimeAdjust,
  getDkstockRegime,
  getKisMcp,
  setAutoRegimeAdjustToggle,
  setDkstockRegime,
  setKisMcp,
} from '../api/integrations'
import type { IntegrationKey, IntegrationToggleStatus } from '../types/integrations'
import ConfirmModal from './ConfirmModal'

interface ToggleMeta {
  key: IntegrationKey
  label: string
  description: string
  confirmOnMessage: string
  confirmOffMessage: string
  enableHint?: string
  envVarName: string
}

const TOGGLES: ToggleMeta[] = [
  {
    key: 'dkstock-regime',
    label: '매크로 레짐 (dkstock.cloud)',
    description:
      '외부 매크로 데이터(VIX/Fear&Greed/cycle) 를 fetch 해 매수 가드 + cash_usage_ratio 자동 조정에 사용합니다.',
    confirmOnMessage:
      '매크로 레짐을 활성화합니다. defensive/극단치 시 매수 가드가 발동되고 cash_usage_ratio 가 자동 조정될 수 있습니다 (auto_regime_adjust=ON 시). 활성화 직후 백그라운드로 fetch 가 진행됩니다. 진행하시겠습니까?',
    confirmOffMessage:
      '매크로 레짐을 비활성화합니다. 매수 가드가 즉시 해제되고 cash_usage_ratio 는 운영자 수동값 그대로 유지됩니다. 진행하시겠습니까?',
    enableHint: '활성화 직후 백그라운드 fetch 진행 — 잠시 후 대시보드에서 결과 확인',
    envVarName: 'DKSTOCK_REGIME_ENABLED',
  },
  {
    key: 'kis-mcp',
    label: '외부 백테스트 서버 (KIS MCP)',
    description:
      '20:00 AI 자문 시점에 외부 MCP 서버로 백테스트 검증을 요청합니다 (운영 매매 흐름 무관).',
    confirmOnMessage:
      '외부 백테스트 서버를 활성화합니다. 다음 20:00 자문부터 백테스트 검증 결과가 자문 카드에 포함됩니다. 진행하시겠습니까?',
    confirmOffMessage:
      '외부 백테스트 서버를 비활성화합니다. 자문은 backtest_summary=null 로 graceful degrade 됩니다. 진행하시겠습니까?',
    envVarName: 'KIS_MCP_ENABLED',
  },
  {
    key: 'auto-regime-adjust',
    label: '레짐 기반 cash_usage_ratio 자동 조정',
    description:
      '매크로 레짐 cash_min 기반으로 cash_usage_ratio 를 자동 갱신합니다 (defensive=0.25 / neutral=0.50 / aggressive=0.80).',
    confirmOnMessage:
      '자동 조정을 활성화합니다. 매크로 레짐 변동 시 cash_usage_ratio 가 자동 갱신됩니다 (다음 영업일 _boot 부터 반영). 진행하시겠습니까?',
    confirmOffMessage:
      '자동 조정을 비활성화합니다. cash_usage_ratio 는 운영자 수동 설정값 그대로 유지됩니다. 진행하시겠습니까?',
    envVarName: '— (DB 키 only, 사이클 2 컨벤션)',
  },
]

function getterFor(key: IntegrationKey) {
  switch (key) {
    case 'dkstock-regime':
      return getDkstockRegime
    case 'kis-mcp':
      return getKisMcp
    case 'auto-regime-adjust':
      return getAutoRegimeAdjust
  }
}

function setterFor(key: IntegrationKey) {
  switch (key) {
    case 'dkstock-regime':
      return setDkstockRegime
    case 'kis-mcp':
      return setKisMcp
    case 'auto-regime-adjust':
      return setAutoRegimeAdjustToggle
  }
}

export default function IntegrationToggleCard() {
  return (
    <div
      className="bg-white rounded-lg shadow p-6 mb-6"
      data-testid="integration-toggle-card"
    >
      <h2 className="text-lg font-semibold text-gray-900 mb-1">외부 통합</h2>
      <p className="text-xs text-gray-500 mb-4">
        외부 매크로/백테스트 서버 활성 여부 토글. 즉시 ON/OFF 가능 — DB 값이 우선,
        없으면 .env 환경변수로 fallback (하위 호환).
      </p>
      <div className="space-y-3">
        {TOGGLES.map((meta) => (
          <ToggleRow key={meta.key} meta={meta} />
        ))}
      </div>
    </div>
  )
}

interface ToggleRowProps {
  meta: ToggleMeta
}

function ToggleRow({ meta }: ToggleRowProps) {
  const queryClient = useQueryClient()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pendingValue, setPendingValue] = useState<boolean | null>(null)
  const [fetchProgress, setFetchProgress] = useState(false)

  const queryKey = ['integration', meta.key] as const

  const { data, isLoading, isError } = useQuery<IntegrationToggleStatus>({
    queryKey,
    queryFn: getterFor(meta.key),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  const mutation = useMutation({
    mutationFn: (next: boolean) => setterFor(meta.key)(next),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey })
      setConfirmOpen(false)
      setPendingValue(null)
      // dkstock-regime 활성화 시 백그라운드 fetch 진행 UI 표시
      if (meta.key === 'dkstock-regime' && saved.enabled) {
        setFetchProgress(true)
        // 3초 후 marketRegime 재조회 invalidate + progress 해제
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ['marketRegime'] })
          setFetchProgress(false)
        }, 3000)
      }
    },
    onError: () => {
      setConfirmOpen(false)
    },
  })

  if (isLoading) {
    return (
      <div className="border border-gray-200 rounded p-3 text-sm text-gray-500">
        {meta.label} 로딩 중...
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div
        className="border border-red-200 rounded p-3 text-sm text-red-700 bg-red-50"
        data-testid={`toggle-error-${meta.key}`}
      >
        {meta.label} 정보를 불러오지 못했습니다 (오류). 잠시 후 재시도하세요.
      </div>
    )
  }

  const onToggleClick = () => {
    setPendingValue(!data.enabled)
    setConfirmOpen(true)
  }

  const onConfirm = () => {
    if (pendingValue !== null) mutation.mutate(pendingValue)
  }

  const onCancel = () => {
    setConfirmOpen(false)
    setPendingValue(null)
  }

  const sourceBadgeClass =
    data.source === 'db'
      ? 'bg-blue-100 text-blue-800'
      : 'bg-gray-100 text-gray-600'

  const stateBadgeClass = data.enabled
    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
    : 'bg-gray-100 text-gray-600 border border-gray-300'

  return (
    <div className="border border-gray-200 rounded p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-900">{meta.label}</span>
            <span
              data-testid={`source-badge-${meta.key}`}
              className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sourceBadgeClass}`}
              title={
                data.source === 'db'
                  ? 'system_config DB 값 사용 중'
                  : `환경변수 ${meta.envVarName} fallback`
              }
            >
              {data.source === 'db' ? 'DB' : 'env'}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{meta.description}</p>
          {data.source === 'env' && (
            <p className="text-[11px] text-gray-400 mt-1">
              현재 출처: 환경변수 <code>{meta.envVarName}</code> = {String(data.env_value)}
            </p>
          )}
          {fetchProgress && meta.key === 'dkstock-regime' && (
            <p
              data-testid={`fetch-progress-${meta.key}`}
              className="text-[11px] text-amber-700 mt-1"
            >
              백그라운드 fetch 진행 중... (3초 후 시장 레짐 카드 자동 갱신)
            </p>
          )}
          {meta.enableHint && data.enabled && (
            <p className="text-[11px] text-amber-700 mt-1">{meta.enableHint}</p>
          )}
        </div>
        <button
          type="button"
          data-testid={`toggle-${meta.key}`}
          onClick={onToggleClick}
          disabled={mutation.isPending}
          className={`shrink-0 px-3 py-1 rounded text-xs font-medium ${stateBadgeClass} disabled:opacity-50`}
        >
          {data.enabled ? 'ON' : 'OFF'}
        </button>
      </div>

      <ConfirmModal
        open={confirmOpen}
        title={pendingValue ? `${meta.label} 활성화` : `${meta.label} 비활성화`}
        message={pendingValue ? meta.confirmOnMessage : meta.confirmOffMessage}
        onConfirm={onConfirm}
        onCancel={onCancel}
        loading={mutation.isPending}
      />
    </div>
  )
}
