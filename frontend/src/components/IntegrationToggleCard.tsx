/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 카드.
 * 사이클 8 (2026-05-18) 확장: 매수 가드 4 모드 + 4 임계값 조정.
 *
 * 3 토글 통합 (운영자 시야 집중을 위해 단일 카드 + 분리 행):
 * - dkstock-regime: 매크로 레짐 fetch (활성화 시 백그라운드 fetch trigger)
 * - kis-mcp: 외부 백테스트 서버 (자문 시점에만 사용)
 * - auto-regime-adjust: 매크로 레짐 → cash_usage_ratio 자동 갱신
 *
 * 사이클 8 — 매수 가드 영역:
 * - 모드 select (OFF/WARN/SOFT/HARD) + ConfirmModal 이중 확인
 * - 4 임계값 슬라이더 + defensive_enabled 체크박스 + 저장 버튼 (즉시 적용)
 * - 발동 사유 + SOFT multiplier 표시
 *
 * 핵심 안전 원칙:
 * - DB 값 != null → DB 사용 (source='db'), null → .env fallback (source='env')
 * - ConfirmModal 이중 확인 (특히 dkstock-regime 활성화는 매수 가드 영향)
 * - 매수 가드 모드 변경 시 ConfirmModal 이중 확인 (매매 흐름 직접 영향)
 * - 임계값 변경은 ConfirmModal 없이 즉시 (덜 위험, 사이클 8 결정)
 * - 활성화 즉시 fetch 는 백그라운드 — API 응답은 즉시 반환
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getAutoRegimeAdjust,
  getBuyBlock,
  getDkstockRegime,
  getKisMcp,
  setAutoRegimeAdjustToggle,
  setBuyBlock,
  setDkstockRegime,
  setKisMcp,
} from '../api/integrations'
import type {
  BuyBlockMode,
  BuyBlockState,
  IntegrationKey,
  IntegrationToggleStatus,
} from '../types/integrations'
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

      {/* 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값 */}
      <BuyBlockSection />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 사이클 8 (2026-05-18) — 매수 가드 섹션
// ---------------------------------------------------------------------------
const MODE_DESCRIPTIONS: Record<BuyBlockMode, string> = {
  OFF: '가드 비활성 (모든 시장 상황에서 매수 허용)',
  WARN: '로그만 기록 (매수 허용, 감사용)',
  SOFT: '비중 절반 축소 (position_ratio × 0.5, 최소 1주)',
  HARD: '완전 차단 (기본값, 사이클 2 동작 보존)',
}

const MODE_CONFIRM_MESSAGES: Record<BuyBlockMode, string> = {
  OFF: '매수 가드를 OFF 로 변경합니다. 모든 시장 상황에서 매수가 허용됩니다 (defensive/VIX 극단/Fear & Greed 극단 무관). 매매 흐름에 즉시 영향이 있으니 신중히 결정하세요. 진행하시겠습니까?',
  WARN: '매수 가드를 WARN 으로 변경합니다. 가드 발동 시 매수는 허용되지만 WARNING 로그가 남습니다 (감사용 모드). 진행하시겠습니까?',
  SOFT: '매수 가드를 SOFT 로 변경합니다. 가드 발동 시 매수는 허용되지만 종목당 수량이 절반(position_ratio × 0.5)으로 축소됩니다 (최소 1주). 진행하시겠습니까?',
  HARD: '매수 가드를 HARD 로 변경합니다. 가드 발동 시 모든 전략의 매수가 차단됩니다 (사이클 2 기본 동작). 진행하시겠습니까?',
}

function BuyBlockSection() {
  const queryClient = useQueryClient()
  const queryKey = ['integration', 'buy-block'] as const

  const { data, isLoading, isError } = useQuery<BuyBlockState>({
    queryKey,
    queryFn: getBuyBlock,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  // ConfirmModal — 모드 변경
  const [pendingMode, setPendingMode] = useState<BuyBlockMode | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  // 임계값 로컬 편집 상태 (저장 버튼 commit)
  const [vix, setVix] = useState<number>(25)
  const [fgHigh, setFgHigh] = useState<number>(85)
  const [fgLow, setFgLow] = useState<number>(15)
  const [defensiveEnabled, setDefensiveEnabled] = useState<boolean>(true)

  // 서버 값으로 동기화 (초기 + 외부 변경 시)
  useEffect(() => {
    if (data) {
      setVix(data.thresholds.vix_threshold)
      setFgHigh(data.thresholds.fg_high_threshold)
      setFgLow(data.thresholds.fg_low_threshold)
      setDefensiveEnabled(data.thresholds.defensive_enabled)
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: setBuyBlock,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
      setConfirmOpen(false)
      setPendingMode(null)
    },
    onError: () => {
      setConfirmOpen(false)
    },
  })

  const onModeChange = (next: BuyBlockMode) => {
    if (!data || next === data.mode) return
    setPendingMode(next)
    setConfirmOpen(true)
  }

  const onConfirmMode = () => {
    if (pendingMode) {
      mutation.mutate({ mode: pendingMode })
    }
  }

  const onCancelMode = () => {
    setConfirmOpen(false)
    setPendingMode(null)
  }

  const onSaveThresholds = () => {
    mutation.mutate({
      vix_threshold: vix,
      fg_high_threshold: fgHigh,
      fg_low_threshold: fgLow,
      defensive_enabled: defensiveEnabled,
    })
  }

  if (isLoading) {
    return (
      <div className="mt-6 pt-4 border-t border-gray-200 text-sm text-gray-500">
        매수 가드 로딩 중...
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div
        className="mt-6 pt-4 border-t border-gray-200 text-sm text-red-700 bg-red-50 rounded p-3"
        data-testid="buy-block-error"
      >
        매수 가드 상태를 불러오지 못했습니다. 잠시 후 재시도하세요.
      </div>
    )
  }

  const modeBadgeClass: Record<BuyBlockMode, string> = {
    OFF: 'bg-gray-100 text-gray-700 border-gray-300',
    WARN: 'bg-amber-100 text-amber-800 border-amber-300',
    SOFT: 'bg-blue-100 text-blue-800 border-blue-300',
    HARD: 'bg-red-100 text-red-800 border-red-300',
  }

  return (
    <div className="mt-6 pt-4 border-t border-gray-200">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">매수 가드</h3>
      <p className="text-xs text-gray-500 mb-3">
        defensive/VIX/Fear&amp;Greed 임계 발동 시 매수를 어떻게 처리할지 선택합니다.
        매도/손절은 영향 없음 (보유 종목 청산은 항상 정상).
      </p>

      {/* 모드 select */}
      <div className="space-y-2 mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs font-medium text-gray-700">모드</label>
          <select
            data-testid="buy-block-mode-select"
            value={data.mode}
            onChange={(e) => onModeChange(e.target.value as BuyBlockMode)}
            disabled={mutation.isPending}
            className="text-xs border border-gray-300 rounded px-2 py-1"
          >
            <option value="OFF">OFF</option>
            <option value="WARN">WARN</option>
            <option value="SOFT">SOFT</option>
            <option value="HARD">HARD</option>
          </select>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium border ${modeBadgeClass[data.mode]}`}
          >
            {data.mode}
          </span>
        </div>
        <p className="text-[11px] text-gray-500">{MODE_DESCRIPTIONS[data.mode]}</p>
        {data.mode === 'SOFT' && (
          <p
            data-testid="buy-block-soft-multiplier"
            className="text-[11px] text-blue-700"
          >
            현재 multiplier: {data.soft_multiplier.toFixed(2)} (가드 발동 시 비중 절반 축소)
          </p>
        )}
      </div>

      {/* 발동 사유 */}
      {data.reasons.length > 0 && (
        <div
          data-testid="buy-block-reasons"
          className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 mb-4"
        >
          <div className="font-medium mb-1">현재 발동 사유 ({data.reasons.length}건):</div>
          <ul className="list-disc list-inside space-y-0.5">
            {data.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          {data.blocked && (
            <div className="mt-1 text-red-700 font-medium">
              HARD 모드 + 가드 발동 — 매수 차단 중
            </div>
          )}
        </div>
      )}

      {/* 임계값 슬라이더 4종 */}
      <div className="space-y-3">
        <ThresholdSlider
          testId="buy-block-vix-slider"
          label="VIX 임계"
          value={vix}
          min={10}
          max={50}
          step={1}
          onChange={setVix}
          hint={`VIX > ${vix} 시 가드 발동 (기본 25)`}
        />
        <ThresholdSlider
          testId="buy-block-fg-high-slider"
          label="Fear & Greed 상한"
          value={fgHigh}
          min={50}
          max={100}
          step={1}
          onChange={setFgHigh}
          hint={`Fear & Greed > ${fgHigh} 시 가드 발동 (극도 탐욕, 기본 85)`}
        />
        <ThresholdSlider
          testId="buy-block-fg-low-slider"
          label="Fear & Greed 하한"
          value={fgLow}
          min={0}
          max={50}
          step={1}
          onChange={setFgLow}
          hint={`Fear & Greed < ${fgLow} 시 가드 발동 (극도 공포, 기본 15)`}
        />

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            data-testid="buy-block-defensive-toggle"
            checked={defensiveEnabled}
            onChange={(e) => setDefensiveEnabled(e.target.checked)}
            id="buy-block-defensive-checkbox"
          />
          <label htmlFor="buy-block-defensive-checkbox" className="text-xs text-gray-700">
            regime=defensive 차단 활성 (체크 해제 시 VIX/FG 임계만 평가)
          </label>
        </div>

        <button
          type="button"
          data-testid="buy-block-thresholds-save"
          onClick={onSaveThresholds}
          disabled={mutation.isPending}
          className="px-3 py-1 rounded text-xs font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          임계값 저장
        </button>
        <p className="text-[10px] text-gray-400">
          임계값 변경은 즉시 적용됩니다. 다음 매수 신호부터 새 값으로 평가.
        </p>
      </div>

      <ConfirmModal
        open={confirmOpen}
        title={pendingMode ? `매수 가드 모드 변경: ${pendingMode}` : '매수 가드 모드 변경'}
        message={pendingMode ? MODE_CONFIRM_MESSAGES[pendingMode] : ''}
        onConfirm={onConfirmMode}
        onCancel={onCancelMode}
        loading={mutation.isPending}
      />
    </div>
  )
}

interface ThresholdSliderProps {
  testId: string
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  hint: string
}

function ThresholdSlider({
  testId,
  label,
  value,
  min,
  max,
  step,
  onChange,
  hint,
}: ThresholdSliderProps) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-medium text-gray-700">{label}</label>
        <span className="text-xs text-gray-900 font-mono">{value}</span>
      </div>
      <input
        type="range"
        data-testid={testId}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
      <p className="text-[10px] text-gray-500 mt-0.5">{hint}</p>
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
