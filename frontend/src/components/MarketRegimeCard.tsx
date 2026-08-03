/**
 * 사이클 2 (2026-05-17): 시장 레짐 카드 (Dashboard 환경 배너 직하).
 *
 * 노출 정보:
 * - regime + label + desc (defensive=red / neutral=gray / aggressive=blue)
 * - VIX 값 + level
 * - Fear & Greed Score + label
 * - Buffett Ratio
 * - cycle.phase (확장기/수축기)
 * - 자동 cash_usage_ratio + auto_regime_adjust 토글 (ConfirmModal 이중 확인)
 * - block_reason 이 있으면 "레짐 경보" 관찰 배너 (사이클 I 표시 정직화 —
 *   `buy_blocked` 는 이제 항상 false 이므로 더 이상 매수 차단 의미로 사용하지 않음)
 * - 지수ETF 레짐(관찰) 소섹션 — 코스피200/코스닥150 stage + 방어 여부 (사이클 I)
 * - DKSTOCK_REGIME_ENABLED=false / empty regime 시 graceful "비활성" 표시
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getMarketRegimeCurrent, setAutoRegimeAdjust } from '../api/market_regime'
import ConfirmModal from './ConfirmModal'

const REGIME_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  defensive: { bg: 'bg-red-100', text: 'text-red-800', label: '방어' },
  neutral: { bg: 'bg-gray-100', text: 'text-gray-800', label: '중립' },
  aggressive: { bg: 'bg-blue-100', text: 'text-blue-800', label: '공격' },
}

const CYCLE_LABEL: Record<string, string> = {
  expansion: '확장기',
  contraction: '수축기',
}

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
            비활성 (DKSTOCK_REGIME_ENABLED=false)
          </span>
        )}
      </div>

      {data.block_reason && (
        <div
          data-testid="market-regime-block-banner"
          className="mb-3 px-3 py-2 bg-amber-50 border border-amber-300 rounded text-sm text-amber-900"
        >
          <strong>레짐 경보</strong> — {data.block_reason}
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
          value={data.buffett_ratio?.toFixed(1) ?? '—'}
          testId="metric-buffett"
        />
        <Metric
          label="경기 사이클"
          value={data.cycle_phase ? CYCLE_LABEL[data.cycle_phase] ?? data.cycle_phase : '—'}
          testId="metric-cycle"
        />
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
              cash_usage_ratio: {(data.cash_usage_ratio * 100).toFixed(0)}%
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
            ? '시장 레짐 cash_min 기반으로 cash_usage_ratio 가 자동 갱신됩니다 (defensive=0.25 / neutral=0.5 / aggressive=0.8). 다음 영업일부터 반영됩니다.'
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
