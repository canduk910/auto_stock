/**
 * 사이클 5 (2026-05-17): 외부 통합 토글 카드.
 * 사이클 8 (2026-05-18) 확장: 매수 가드 4 모드 + 4 임계값 조정.
 * 사이클 23 (2026-05-20) 확장: AI 자문 자동 적용 토글 (4번째 토글).
 * 사이클 I (2026-08-03) 확장: 지수ETF 레짐(관찰) 계산 토글 (5번째 토글).
 *
 * 5 토글 통합 (운영자 시야 집중을 위해 단일 카드 + 분리 행):
 * - dkstock-regime: 매크로 레짐 수집 (활성화 시 백그라운드 수집 trigger).
 *   ⚠️ key·env 이름만 옛 외부 서비스(dkstock.cloud)를 물려받았을 뿐, 실제 출처는
 *   cycle315 부터 **우리 macro 컨테이너**다 (외부 서비스는 2026-08-18 철거).
 * - kis-mcp: 외부 백테스트 서버 (자문 시점에만 사용)
 * - auto-regime-adjust: 매크로 레짐 → cash_usage_ratio 자동 갱신
 * - auto-apply: AI 자문 자동 적용 (전략 비중 감액만 + 50% cap, 기본 OFF — 매매 파라미터는 자동 적용 안 함)
 * - etf-regime: 지수ETF 레짐(관찰) 계산 — 코스피200/코스닥150 스테이지, 매수 가드 미개입
 *
 * 사이클 8 — 매수 가드 영역:
 * - 모드 select (OFF/WARN/SOFT/HARD) + ConfirmModal 이중 확인
 * - 4 임계값 슬라이더 + defensive_enabled 체크박스 + 저장 버튼 (즉시 적용)
 * - 발동 사유 + SOFT multiplier 표시
 *
 * 핵심 안전 원칙:
 * - DB 값 != null → DB 사용 (source='db'), null → .env fallback (source='env')
 * - ConfirmModal 이중 확인 (레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다)
 * - 매수 가드 모드 변경 시 ConfirmModal 이중 확인 (매매 흐름 직접 영향)
 * - 임계값 변경은 ConfirmModal 없이 즉시 (덜 위험, 사이클 8 결정)
 * - 활성화 즉시 fetch 는 백그라운드 — API 응답은 즉시 반환
 */
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getAutoApply,
  getAutoRegimeAdjust,
  getBuyBlock,
  getDkstockRegime,
  getEtfRegime,
  getKisMcp,
  setAutoApply,
  setAutoRegimeAdjustToggle,
  setBuyBlock,
  setDkstockRegime,
  setEtfRegime,
  setKisMcp,
} from '../api/integrations'
import type {
  AutoApplyStatus,
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
    // cycle315 (2026-09-19) — 출처가 철거된 dkstock.cloud 에서 우리 macro 컨테이너로 옮겨졌다.
    // 🔴 key `dkstock-regime` 과 env `DKSTOCK_REGIME_ENABLED` 는 **유지**한다(사용자 결정) —
    //    개명하면 운영 DB 의 기존 행이 고아가 되고 프론트·E2E·가드가 한 커밋에 묶인다.
    //    바뀌는 것은 운영자가 읽는 문장뿐이다. 레짐은 **관찰 지표**라 매수를 막지 않는다.
    key: 'dkstock-regime',
    label: '매크로 레짐 (자체 macro 컨테이너)',
    description:
      '우리 macro 컨테이너에서 매크로 지표(VIX/Fear&Greed/버핏지수/경기사이클) 를 받아 시장 레짐 카드에 관찰용으로 표시합니다. 매수를 차단하거나 줄이지 않습니다.',
    confirmOnMessage:
      '매크로 레짐 수집을 활성화합니다. 자체 macro 컨테이너에서 지표를 받아 시장 레짐 카드에 표시하고, 자동 조정이 ON 인 경우에만 cash_usage_ratio 가 다음 영업일부터 갱신됩니다. 진행하시겠습니까?',
    confirmOffMessage:
      '매크로 레짐 수집을 비활성화합니다. 시장 레짐 카드가 "비활성" 으로 표시되고 cash_usage_ratio 는 운영자 수동값 그대로 유지됩니다. 진행하시겠습니까?',
    enableHint: '활성화 직후 백그라운드 수집 진행 — 잠시 후 대시보드 시장 레짐 카드에서 확인',
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
    // 사다리는 macro_lite `REGIME_PARAMS` 의 cash_min 정본값 — 자금 사용률 = (100 − cash_min)%.
    // 종전 문구의 neutral/aggressive 는 어느 경로에서도 나오지 않는 죽은 레짐이었다.
    description:
      '매크로 레짐 cash_min 기반으로 cash_usage_ratio 를 자동 갱신합니다 (적극 매수=0.75 / 선별 매수=0.65 / 신중=0.50 / 방어=0.25).',
    confirmOnMessage:
      '자동 조정을 활성화합니다. 매크로 레짐 변동 시 cash_usage_ratio 가 자동 갱신됩니다 (다음 영업일 _boot 부터 반영). 진행하시겠습니까?',
    confirmOffMessage:
      '자동 조정을 비활성화합니다. cash_usage_ratio 는 운영자 수동 설정값 그대로 유지됩니다. 진행하시겠습니까?',
    envVarName: '— (DB 키 only, 사이클 2 컨벤션)',
  },
  {
    key: 'etf-regime',
    label: '지수ETF 레짐 (관찰, 코스피200/코스닥150)',
    description:
      '코스피200/코스닥150 ETF 일봉으로 스테이지를 계산해 시장 레짐 카드에 관찰용으로 노출합니다 (매수 가드 미개입, Phase 1 다크런치).',
    confirmOnMessage:
      '지수ETF 레짐 관찰 계산을 활성화합니다. 코스피200/코스닥150 스테이지가 시장 레짐 카드에 표시됩니다 (매수 가드에는 영향 없음, 관찰 전용). 진행하시겠습니까?',
    confirmOffMessage:
      '지수ETF 레짐 관찰 계산을 비활성화합니다. 시장 레짐 카드의 지수ETF 스테이지가 "관찰 비활성" 으로 표시됩니다. 진행하시겠습니까?',
    envVarName: '— (DB 키 only, 사이클 I, .env fallback 없음)',
  },
]

// 사이클 23 P3-3 — auto-apply 별도 섹션 (DB-only, .env fallback 없음)
const AUTO_APPLY_META: ToggleMeta = {
  key: 'auto-apply',
  label: 'AI 자문 자동 적용 (전략 비중 감액만 + 50% cap)',
  description:
    '20:00 AI 자문 직후 전략 비중(weight) 감액 권고만 자동 반영합니다 (감액폭 50% cap, 증액 권고는 자동 반영 대상이 아닙니다). 손절폭·종목당 비중·일일 손실한도 같은 매매 파라미터는 자동 적용되지 않으며, 필요하면 운영자가 자문 화면에서 직접 적용해야 합니다. 파라미터 자동 반영은 조이는 방향의 권고만 통과시키는 구조여서 조임이 매일 누적돼 전략이 사실상 매매를 못 하게 되는 문제가 확인되어 중단했습니다 (사이클 210).',
  confirmOnMessage:
    'AI 자문 자동 적용을 활성화합니다. 매일 20:00 자문 직후 전략 비중 감액 권고만 자동 반영됩니다 (감액폭 50% cap). 증액 권고와 매매 파라미터 권고는 자동 반영되지 않고, 운영자 명시 적용에서만 반영됩니다. 진행하시겠습니까?',
  confirmOffMessage:
    'AI 자문 자동 적용을 비활성화합니다. 모든 자문은 운영자 수동 적용에서만 반영됩니다. 진행하시겠습니까?',
  envVarName: '— (DB 키 only, 사이클 23)',
}

function getterFor(key: IntegrationKey) {
  switch (key) {
    case 'dkstock-regime':
      return getDkstockRegime
    case 'kis-mcp':
      return getKisMcp
    case 'auto-regime-adjust':
      return getAutoRegimeAdjust
    case 'etf-regime':
      return getEtfRegime
    case 'auto-apply':
      return () => getAutoApply().then((s: AutoApplyStatus) => ({
        enabled: s.enabled,
        source: 'db' as const,
        env_value: false,
        db_value: s.enabled,
      }))
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
    case 'etf-regime':
      return setEtfRegime
    case 'auto-apply':
      return setAutoApply
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
        {/* 사이클 23 P3-3 — AI 자문 자동 적용 토글 (4번째, DB-only) */}
        <ToggleRow key={AUTO_APPLY_META.key} meta={AUTO_APPLY_META} />
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
    retry: 1, // 사이클 75 Q4 — e2e ECONNREFUSED 시 timeout 차단 (사이클 65 H1 패턴)
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

      {/* 사이클 D-FE (2026-07-31) — 레짐 가드 silent inert 배너.
          data_available=false + mode!=='OFF' 이면 가드가 설정만 되고 실제로는
          무력(데이터 미유입으로 blocked/soft_multiplier 평가 자체가 무의미) —
          amber 발동 사유보다 강한 red 강조로 false sense of protection 차단. */}
      {data.guard_inert === true && (
        <div
          data-testid="buy-block-guard-inert"
          className="bg-red-100 text-red-800 border border-red-300 rounded p-2 mb-4"
        >
          {`⚠️ 매수 가드 무력 — 레짐 매크로 데이터 미유입. mode=${data.mode} 설정됐으나 실제 방어 미작동 (데이터 복구 전까지 매수 무제한 통과)`}
        </div>
      )}

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

/**
 * cycle315 — 매크로 레짐 활성화 직후 재조회 스케줄(ms).
 *
 * 종전에는 3초 뒤 한 번만 `marketRegime` 을 invalidate 했다. 그 숫자는 외부 dkstock.cloud
 * 가 이미 계산해 둔 값을 받아오던 시절의 것이고, 우리 macro 컨테이너는 캐시가 비어 있으면
 * 원천(yfinance/FRED 등)을 직접 긁어 **최대 2분**까지 걸린다(2026-09-18 실측 첫 호출 107초).
 * 3초 뒤 한 번만 보면 항상 빈 값을 보고 끝나므로, 값이 들어올 시간까지 몇 번 더 본다.
 */
const MACRO_REFETCH_DELAYS_MS = [3_000, 15_000, 30_000, 60_000, 120_000]

function ToggleRow({ meta }: ToggleRowProps) {
  const queryClient = useQueryClient()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pendingValue, setPendingValue] = useState<boolean | null>(null)
  const [fetchProgress, setFetchProgress] = useState(false)
  const refetchTimersRef = useRef<number[]>([])

  // 언마운트 시 대기 중인 재조회 타이머 정리 (Settings 이탈 후 setState 경고 차단)
  useEffect(
    () => () => {
      refetchTimersRef.current.forEach((id) => clearTimeout(id))
      refetchTimersRef.current = []
    },
    [],
  )

  const queryKey = ['integration', meta.key] as const

  const { data, isLoading, isError } = useQuery<IntegrationToggleStatus>({
    queryKey,
    queryFn: getterFor(meta.key),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1, // 사이클 75 Q4 — e2e ECONNREFUSED 시 timeout 차단 (사이클 65 H1 패턴)
  })

  const mutation = useMutation({
    mutationFn: (next: boolean) => setterFor(meta.key)(next),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey })
      setConfirmOpen(false)
      setPendingValue(null)
      // 매크로 레짐 활성화 시 백그라운드 수집 진행 UI 표시 + 단계적 재조회
      if (meta.key === 'dkstock-regime' && saved.enabled) {
        setFetchProgress(true)
        refetchTimersRef.current.forEach((id) => clearTimeout(id))
        refetchTimersRef.current = MACRO_REFETCH_DELAYS_MS.map((ms, i) =>
          window.setTimeout(() => {
            queryClient.invalidateQueries({ queryKey: ['marketRegime'] })
            if (i === MACRO_REFETCH_DELAYS_MS.length - 1) setFetchProgress(false)
          }, ms),
        )
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

  // cycle261 후속(적대 검토) — index.css 별칭(emerald≡blue) 때문에 종전 emerald 가
  // 바로 위 sourceBadgeClass(db=blue) · BuyBlockSection 의 SOFT 모드 배지(blue)와 실제
  // hex 가 동일했다. "활성" 의미를 다른 배지와 겹치지 않는 sky 계열로 분리.
  const stateBadgeClass = data.enabled
    ? 'bg-sky-100 text-sky-800 border border-sky-300'
    : 'bg-gray-100 text-gray-600 border border-gray-300'

  return (
    <div className="border border-gray-200 rounded p-3" data-testid={`toggle-row-${meta.key}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-900" data-testid={`toggle-label-${meta.key}`}>
              {meta.label}
            </span>
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
          <p className="text-xs text-gray-500 mt-1" data-testid={`toggle-desc-${meta.key}`}>
            {meta.description}
          </p>
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
              백그라운드 수집 진행 중... 캐시가 비어 있으면 첫 수집에 최대 2분 걸립니다 —
              값이 들어올 때까지 시장 레짐 카드를 자동으로 다시 조회합니다.
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
