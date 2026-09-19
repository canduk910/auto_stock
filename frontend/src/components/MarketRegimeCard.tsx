/**
 * 사이클 2 (2026-05-17): 시장 레짐 카드 (Dashboard 환경 배너 직하).
 * cycle315 (2026-09-19): 레짐 출처가 외부 dkstock.cloud 에서 **우리 macro 컨테이너**로
 *   바뀌면서, 화면이 들고 있던 값이 실재와 어긋나 있던 것을 함께 시정한다.
 *
 * 노출 정보:
 * - regime + label + desc — 실재 레짐은 `macro/macro_lite/regime.py::REGIME_MATRIX` 가 내는
 *   accumulation / selective / cautious / defensive **4종뿐**이다. 종전 3키(defensive/
 *   neutral/aggressive)는 뒤의 둘이 어느 경로에서도 나올 수 없는 죽은 키였고, 그래서
 *   실제로 오는 accumulation·selective·cautious 가 전부 "비활성" 회색 폴백으로 떨어졌다.
 * - VIX 값 / Fear & Greed Score / Buffett Ratio(비율 계약) / cycle.phase(4국면)
 * - 자금 사다리 표 — regime → cash_min → 자금 사용률(= 100 − cash_min)
 * - 자동 cash_usage_ratio + auto_regime_adjust 토글 (ConfirmModal 이중 확인)
 * - block_reason 이 있으면 "레짐 경보" 관찰 배너 (사이클 I 표시 정직화 —
 *   `buy_blocked` 는 이제 항상 false 이므로 더 이상 매수 차단 의미로 사용하지 않음)
 * - 지수ETF 레짐(관찰) 소섹션 — 코스피200/코스닥150 stage + 방어 여부 (사이클 I)
 * - 레짐 수집 비활성 / empty regime 시 graceful "비활성" 표시
 *
 * 🔴 이 카드는 **부팅 시점 스냅샷**이다 — `_boot()`(매일 07:45 KST)이 한 번 받아 둔 값을
 *    보여 준다. 지금 이 순간의 값은 라이브 화면 `/macro` 가 따로 있다. 두 화면의 숫자가
 *    다르면 그것은 결함이 아니라 **다른 시점**이다.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getMarketRegimeCurrent, setAutoRegimeAdjust } from '../api/market_regime'
import ConfirmModal from './ConfirmModal'

// 표시 상수(레짐 4종 스타일·4국면 라벨·자금 사다리·버핏지수 포매터)는
// `utils/marketRegime.ts` 가 단일 진실원이다 — 컴포넌트 파일에서 함께 export 하면
// vite fast-refresh 가 깨진다(`utils/contentWidth.ts` 선례).
import {
  CYCLE_LABEL,
  REGIME_CASH_LADDER,
  REGIME_STYLE,
  formatBuffettRatio,
  usagePctFromCashMin,
} from '../utils/marketRegime'

export default function MarketRegimeCard() {
  const queryClient = useQueryClient()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pendingValue, setPendingValue] = useState<boolean | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['marketRegime'],
    queryFn: getMarketRegimeCurrent,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })

  const mutation = useMutation({
    mutationFn: (next: boolean) => setAutoRegimeAdjust(next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketRegime'] })
      setConfirmOpen(false)
      setPendingValue(null)
    },
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4 mb-4" data-testid="market-regime-card">
        <div className="text-gray-500 text-sm">시장 레짐 로딩 중...</div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="bg-white rounded-lg shadow p-4 mb-4" data-testid="market-regime-card">
        <div className="text-gray-500 text-sm">시장 레짐 정보를 불러오지 못했습니다.</div>
      </div>
    )
  }

  const regimeKey = data.regime ?? 'unknown'
  const style = REGIME_STYLE[regimeKey] ?? { bg: 'bg-gray-50', text: 'text-gray-500', label: '비활성' }

  // 자동 조정이 켜졌을 때 실제로 적용될 값 — 모달이 "지금 이 레짐이면 얼마가 되는가" 를
  // 예시 상수가 아니라 현재 cash_min 으로 말하게 한다.
  const autoUsagePct = data.cash_min != null ? usagePctFromCashMin(data.cash_min) : null
  const currentUsagePct = Math.round(data.cash_usage_ratio * 100)

  const onToggleClick = () => {
    setPendingValue(!data.auto_regime_adjust)
    setConfirmOpen(true)
  }
  const onConfirm = () => {
    if (pendingValue !== null) mutation.mutate(pendingValue)
  }
  const onCancel = () => {
    setConfirmOpen(false)
    setPendingValue(null)
  }

  const confirmOnMessage =
    autoUsagePct != null
      ? `시장 레짐의 현금 최소 비중(cash_min)으로 cash_usage_ratio 가 자동 갱신됩니다. ` +
        `지금 레짐(${style.label}, cash_min=${data.cash_min}) 기준이면 ` +
        `${currentUsagePct}% → ${autoUsagePct}% 로 바뀝니다. 다음 영업일부터 반영됩니다.`
      : '시장 레짐의 현금 최소 비중(cash_min)으로 cash_usage_ratio 가 자동 갱신됩니다. 다음 영업일부터 반영됩니다.'

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4" data-testid="market-regime-card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-900">시장 레짐</h2>
        {data.enabled ? (
          <span
            data-testid="market-regime-badge"
            className={`inline-block px-2 py-1 rounded text-xs font-medium ${style.bg} ${style.text}`}
          >
            {style.label}
            {data.regime_desc ? ` · ${data.regime_desc}` : ''}
          </span>
        ) : (
          <span
            data-testid="market-regime-badge"
            className="inline-block px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-500"
          >
            비활성 (레짐 수집 꺼짐)
          </span>
        )}
      </div>

      {/* 🔴 성격 명시 (cycle315) — 이 카드의 값은 _boot() 이 한 번 받아 둔 스냅샷이고
          `/macro` 는 요청할 때마다 새로 계산하는 라이브 화면이다. 두 숫자가 다른 이유가
          "어느 쪽이 틀렸나" 가 아니라 "시점이 다르다" 임을 화면이 스스로 말하게 한다. */}
      <div
        data-testid="market-regime-snapshot-note"
        className="mb-3 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs text-gray-600"
      >
        이 카드는 매일 아침 <strong>07:45 KST</strong> 부팅(<code>_boot()</code>) 시점에 받아 둔{' '}
        <strong>스냅샷</strong>입니다 — 그 뒤로는 자동 갱신되지 않습니다. 지금 이 순간의 라이브 값은{' '}
        <Link
          data-testid="market-regime-macro-link"
          to="/macro"
          className="text-blue-700 underline underline-offset-2"
        >
          매크로 화면(/macro)
        </Link>
        에서 봅니다.
      </div>

      {/* 관찰 전용 안내 (2026-08-07) — 자동 조정 OFF 이면 레짐은 실제 매매에
          반영되지 않는다. red 방어 배지 + amber 경보 + cash 100% 병치가 "시스템이
          방어 중"으로 오인되던 것을 화해시키는 문구. */}
      {data.enabled && !data.auto_regime_adjust && (
        <div
          data-testid="market-regime-observation-note"
          className="mb-3 px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs text-slate-600"
        >
          레짐은 <strong>관찰 전용</strong>입니다 — 실제 매매에 반영되지 않습니다
          (현재 cash_usage_ratio {currentUsagePct}% 수동).
          아래 배지·경보는 우리 매크로 컨테이너의 <strong>권고</strong>이며, 자동 조정은 OFF 입니다.
        </div>
      )}

      {data.block_reason && (
        <div
          data-testid="market-regime-block-banner"
          className="mb-3 px-3 py-2 bg-amber-50 border border-amber-300 rounded text-sm text-amber-900"
        >
          <strong>레짐 경보{!data.auto_regime_adjust ? ' (권고·관찰)' : ''}</strong> — {data.block_reason}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <Metric label="VIX" value={data.vix?.toFixed(2) ?? '—'} testId="metric-vix" />
        <Metric
          label="Fear & Greed"
          value={data.fear_greed_score?.toFixed(0) ?? '—'}
          testId="metric-fear-greed"
        />
        <Metric
          label="Buffett Ratio"
          value={formatBuffettRatio(data.buffett_ratio)}
          testId="metric-buffett"
        />
        <Metric
          label="경기 사이클"
          value={data.cycle_phase ? CYCLE_LABEL[data.cycle_phase] ?? data.cycle_phase : '—'}
          testId="metric-cycle"
        />
      </div>

      {/* 자금 사다리 — 레짐이 바뀌면 자동 조정이 어디로 가는지 미리 보여 준다.
          값은 macro_lite REGIME_PARAMS 정본(cash_min) 이고 사용률은 100 − cash_min 이다. */}
      <div className="border-t pt-3 mt-3" data-testid="market-regime-cash-ladder">
        <h3 className="text-sm font-medium text-gray-700 mb-2">자금 사다리 (레짐별 권고)</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {REGIME_CASH_LADDER.map(({ regime, cashMin }) => {
            const s = REGIME_STYLE[regime]
            const active = regimeKey === regime
            return (
              <div
                key={regime}
                data-testid={`market-regime-cash-ladder-${regime}`}
                data-active={active ? 'true' : 'false'}
                className={`rounded px-2 py-2 text-xs border ${
                  active ? `${s.bg} ${s.text} border-current font-semibold` : 'bg-gray-50 text-gray-600 border-gray-200'
                }`}
              >
                <div>{s.label}</div>
                <div className="font-mono">현금 최소 {cashMin}</div>
                <div className="font-mono">자금 사용률 {usagePctFromCashMin(cashMin)}%</div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 사이클 E-1 → 사이클 I (2026-08-03): 지수ETF 레짐(관찰) 소섹션 */}
      <div className="border-t pt-3 mt-3" data-testid="etf-regime-section">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-700">지수ETF 레짐 (관찰)</h3>
          {!data.etf_enabled && (
            <span
              data-testid="etf-regime-disabled-label"
              className="text-xs text-gray-400"
            >
              관찰 비활성
            </span>
          )}
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Metric
            label="코스피200 stage"
            value={data.etf_kospi_stage != null ? String(data.etf_kospi_stage) : '-'}
            testId="metric-etf-kospi-stage"
          />
          <Metric
            label="코스닥150 stage"
            value={data.etf_kosdaq_stage != null ? String(data.etf_kosdaq_stage) : '-'}
            testId="metric-etf-kosdaq-stage"
          />
          <Metric
            label="방어 여부"
            value={data.etf_defensive == null ? '-' : data.etf_defensive ? '방어' : '비방어'}
            testId="metric-etf-defensive"
          />
        </div>
      </div>

      <div className="border-t pt-3 mt-3">
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-700">
            <strong data-testid="metric-cash-ratio">
              cash_usage_ratio: {currentUsagePct}%
            </strong>
            {data.cash_min !== null && data.auto_regime_adjust && data.enabled && (
              <span className="ml-2 text-xs text-gray-500">
                (레짐 cash_min={data.cash_min} 기반 자동 조정)
              </span>
            )}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-gray-600">자동 조정</span>
            <button
              type="button"
              data-testid="auto-regime-toggle"
              onClick={onToggleClick}
              disabled={mutation.isPending}
              className={`px-3 py-1 rounded text-xs font-medium ${
                data.auto_regime_adjust
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                  : 'bg-gray-100 text-gray-600 border border-gray-300'
              } disabled:opacity-50`}
            >
              {data.auto_regime_adjust ? 'ON' : 'OFF'}
            </button>
          </label>
        </div>
        <div className="text-xs text-amber-700 mt-2">
          토글 변경은 다음 영업일 _boot 부터 반영됩니다.
        </div>
      </div>

      <ConfirmModal
        open={confirmOpen}
        title={pendingValue ? '자동 조정 ON' : '자동 조정 OFF'}
        message={
          pendingValue
            ? confirmOnMessage
            : '운영자 수동 cash_usage_ratio 가 보존됩니다. 레짐 변동과 무관하게 현 비율 그대로 분배됩니다. 다음 영업일부터 반영됩니다.'
        }
        onConfirm={onConfirm}
        onCancel={onCancel}
        loading={mutation.isPending}
      />
    </div>
  )
}

interface MetricProps {
  label: string
  value: string
  testId: string
}
function Metric({ label, value, testId }: MetricProps) {
  return (
    <div className="bg-gray-50 rounded px-3 py-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-sm font-mono font-semibold text-gray-900" data-testid={testId}>
        {value}
      </div>
    </div>
  )
}
