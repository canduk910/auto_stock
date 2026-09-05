import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCashUsageRatio, updateCashUsageRatio } from '../api/trading'

/**
 * 매매 가용 자금 비율 카드 (J3, 2026-05-12).
 *
 * `system_config.cash_usage_ratio` 키. 범위 [0.5, 1.0], 5% 단위. 기본 1.0.
 * scheduler `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출.
 * 변경 즉시 적용 안 됨 — 다음 영업일 부터 반영.
 *
 * 옵셔널 `netAsset` 가 주어지면 예상 가용액(`netAsset × ratio`) 을 함께 표시.
 */
interface Props {
  netAsset?: number
}

export default function CashUsageRatioCard({ netAsset }: Props) {
  const queryClient = useQueryClient()
  const [percent, setPercent] = useState<number>(100)
  const [dirty, setDirty] = useState(false)
  const [savedNotice, setSavedNotice] = useState<string | null>(null)

  const { data: ratio, isLoading } = useQuery({
    queryKey: ['cashUsageRatio'],
    queryFn: getCashUsageRatio,
    retry: 1, // 사이클 75 Q4 — e2e ECONNREFUSED 시 timeout 차단 (사이클 65 H1 패턴)
  })

  useEffect(() => {
    if (typeof ratio === 'number') {
      setPercent(Math.round(ratio * 100))
      setDirty(false)
    }
  }, [ratio])

  const mutation = useMutation({
    mutationFn: (next: number) => updateCashUsageRatio(next),
    onSuccess: (savedRatio) => {
      // 백엔드가 5% 단위로 보정한 값을 받아 슬라이더 동기화
      setPercent(Math.round(savedRatio * 100))
      setDirty(false)
      setSavedNotice(`${Math.round(savedRatio * 100)}% 저장 완료 — 다음 영업일부터 반영`)
      queryClient.invalidateQueries({ queryKey: ['cashUsageRatio'] })
    },
  })

  const onSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPercent(Number(e.target.value))
    setDirty(true)
    setSavedNotice(null)
  }

  const onSave = () => {
    mutation.mutate(percent / 100)
  }

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="text-gray-500 text-sm">가용 자금 비율 로딩 중...</div>
      </div>
    )
  }

  const expectedAvailable =
    typeof netAsset === 'number' ? Math.floor((netAsset * percent) / 100) : null

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold text-gray-900">매매 가용 자금 비율</h2>
        <span
          data-testid="cash-usage-ratio-percent"
          className="text-lg font-mono font-medium text-blue-600"
        >
          {percent}%
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        순자산 중 매매에 사용할 비율 (50% ~ 100%, 5% 단위). 나머지는 현금으로 유지됩니다.
      </p>

      <input
        type="range"
        min={50}
        max={100}
        step={5}
        value={percent}
        onChange={onSliderChange}
        data-testid="cash-usage-ratio-slider"
        className="w-full h-2 rounded-lg appearance-none cursor-pointer"
        style={{ accentColor: 'var(--color-navy-600)' }}
      />

      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>50%</span>
        <span>75%</span>
        <span>100%</span>
      </div>

      {expectedAvailable !== null && (
        <div className="mt-3 text-sm text-gray-700">
          예상 가용액: <strong>{expectedAvailable.toLocaleString()}원</strong>
          <span className="text-xs text-gray-400 ml-2">
            (순자산 {netAsset?.toLocaleString()}원 × {percent}%)
          </span>
        </div>
      )}

      <div className="mt-3 text-xs text-amber-700">
        다음 영업일부터 반영됩니다 (당일 운영 중 분배는 변경되지 않음).
      </div>

      {savedNotice && (
        <div className="mt-3 px-3 py-2 bg-green-50 border border-green-200 rounded text-sm text-green-700">
          {savedNotice}
        </div>
      )}

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty || mutation.isPending}
          data-testid="cash-usage-ratio-save"
          className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {mutation.isPending ? '저장 중...' : '저장'}
        </button>
      </div>
    </div>
  )
}
