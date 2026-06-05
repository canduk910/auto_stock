/**
 * 가격 필터 카드 (사이클 62, 2026-06-05).
 *
 * 기능:
 * - 매수 진입 전 가격 필터 설정 (저가주 차단 + 초고가주 차단)
 * - 3 모드: HARD (차단) / WARN (경고만) / OFF (비활성)
 * - 저장 즉시 반영 (백엔드 60s TTL 캐시 invalidate)
 * - 보유 종목 매도 / 익일청산 / 손절 영향 0 (매수 진입 전용)
 *
 * testid 매트릭스 (Red 명세 §F-FE 기준):
 *   price-filter-card          — 카드 컨테이너
 *   price-filter-mode-select   — HARD/WARN/OFF 셀렉트
 *   price-filter-min-slider    — 최소가 슬라이더 (0~20,000원, step 1,000)
 *   price-filter-max-slider    — 최대가 슬라이더 (0~2,000,000원, step 50,000)
 *   price-filter-save-button   — 저장 버튼
 *   price-filter-save-toast    — 저장 성공 안내
 *   price-filter-validation-error — max < min 에러
 *
 * 패턴 답습: CashUsageRatioCard (슬라이더 + 명시 저장 버튼)
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getPriceFilter, updatePriceFilter } from '../api/price-filter'
import type { PriceFilterMode } from '../types/price-filter'

// 권장값 (자문 Q1 확정 — UI 툴팁만, DB 디폴트 아님)
const RECOMMENDED_MIN = 5_000
const RECOMMENDED_MAX = 1_000_000

// 슬라이더 범위 (자문 Q1 확정)
const MIN_SLIDER_MAX = 20_000
const MIN_SLIDER_STEP = 1_000
const MAX_SLIDER_MAX = 2_000_000
const MAX_SLIDER_STEP = 50_000

const MODE_LABELS: Record<PriceFilterMode, string> = {
  HARD: 'HARD (차단)',
  WARN: 'WARN (경고만)',
  OFF: 'OFF (비활성)',
}

function formatPrice(value: number): string {
  if (value === 0) return '0 (비활성)'
  return `${value.toLocaleString('ko-KR')}원`
}

export default function PriceFilterCard() {
  const queryClient = useQueryClient()

  const [minPrice, setMinPrice] = useState<number>(0)
  const [maxPrice, setMaxPrice] = useState<number>(0)
  const [mode, setMode] = useState<PriceFilterMode>('OFF')
  const [dirty, setDirty] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [saveToast, setSaveToast] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['priceFilter'],
    queryFn: getPriceFilter,
  })

  useEffect(() => {
    if (data) {
      setMinPrice(data.min_price)
      setMaxPrice(data.max_price)
      setMode(data.mode)
      setDirty(false)
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: updatePriceFilter,
    onSuccess: (saved) => {
      setMinPrice(saved.min_price)
      setMaxPrice(saved.max_price)
      setMode(saved.mode)
      setDirty(false)
      setValidationError(null)
      setSaveToast('가격 필터가 즉시 반영되었습니다.')
      queryClient.invalidateQueries({ queryKey: ['priceFilter'] })
      // toast 3초 후 자동 닫기
      setTimeout(() => setSaveToast(null), 3000)
    },
  })

  const onMinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMinPrice(Number(e.target.value))
    setDirty(true)
    setSaveToast(null)
    setValidationError(null)
  }

  const onMaxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMaxPrice(Number(e.target.value))
    setDirty(true)
    setSaveToast(null)
    setValidationError(null)
  }

  const onModeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setMode(e.target.value as PriceFilterMode)
    setDirty(true)
    setSaveToast(null)
    setValidationError(null)
  }

  const onSave = () => {
    // 클라이언트 검증: max < min (단 둘 다 > 0 일 때만)
    if (minPrice > 0 && maxPrice > 0 && maxPrice < minPrice) {
      setValidationError(
        '최대 가격은 최소 가격보다 커야 합니다. (최소: ' +
          minPrice.toLocaleString('ko-KR') +
          '원, 최대: ' +
          maxPrice.toLocaleString('ko-KR') +
          '원)',
      )
      return
    }
    setValidationError(null)
    mutation.mutate({ min_price: minPrice, max_price: maxPrice, mode })
  }

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="text-gray-500 text-sm">가격 필터 로딩 중...</div>
      </div>
    )
  }

  return (
    <div
      data-testid="price-filter-card"
      className="bg-white rounded-lg shadow p-6 mb-6"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold text-gray-900">가격 필터</h2>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
          매수 진입 전용
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        매수 진입 시 참조 가격이 [최소, 최대] 범위를 벗어나면 모드에 따라
        차단(HARD) 또는 경고(WARN) 합니다. 보유 종목 매도·손절·익일청산 영향
        0.
      </p>

      {/* 운영 모드 셀렉트 */}
      <div className="mb-5">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          운영 모드
        </label>
        <select
          data-testid="price-filter-mode-select"
          value={mode}
          onChange={onModeChange}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {(['HARD', 'WARN', 'OFF'] as PriceFilterMode[]).map((m) => (
            <option key={m} value={m}>
              {MODE_LABELS[m]}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-gray-400">
          HARD: 범위 벗어난 종목 매수 차단 / WARN: 경고 로그만 기록, 매수
          허용 / OFF: 필터 비활성
        </p>
      </div>

      {/* 최소 가격 슬라이더 */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-1">
          <label className="text-sm font-medium text-gray-700">
            최소 가격{' '}
            <span className="text-xs text-gray-400 font-normal">
              (0 = 비활성)
            </span>
          </label>
          <span className="text-sm font-mono font-medium text-blue-600">
            {formatPrice(minPrice)}
          </span>
        </div>
        <input
          type="range"
          data-testid="price-filter-min-slider"
          min={0}
          max={MIN_SLIDER_MAX}
          step={MIN_SLIDER_STEP}
          value={minPrice}
          onChange={onMinChange}
          className="w-full h-2 rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: '#2563eb' }}
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>0 (비활성)</span>
          <span
            className="text-blue-500 cursor-help"
            title={`권장: ${RECOMMENDED_MIN.toLocaleString('ko-KR')}원 (동전주 / 저가주 차단 표준 임계)`}
          >
            권장 {RECOMMENDED_MIN.toLocaleString('ko-KR')}원
          </span>
          <span>{(MIN_SLIDER_MAX / 10000).toFixed(0)}만원</span>
        </div>
      </div>

      {/* 최대 가격 슬라이더 */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-1">
          <label className="text-sm font-medium text-gray-700">
            최대 가격{' '}
            <span className="text-xs text-gray-400 font-normal">
              (0 = 비활성)
            </span>
          </label>
          <span className="text-sm font-mono font-medium text-blue-600">
            {formatPrice(maxPrice)}
          </span>
        </div>
        <input
          type="range"
          data-testid="price-filter-max-slider"
          min={0}
          max={MAX_SLIDER_MAX}
          step={MAX_SLIDER_STEP}
          value={maxPrice}
          onChange={onMaxChange}
          className="w-full h-2 rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: '#2563eb' }}
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>0 (비활성)</span>
          <span
            className="text-blue-500 cursor-help"
            title={`권장: ${(RECOMMENDED_MAX / 10000).toFixed(0)}만원 (1주 폴백 자금 비중 한계)`}
          >
            권장 {(RECOMMENDED_MAX / 10000).toFixed(0)}만원
          </span>
          <span>{(MAX_SLIDER_MAX / 10000).toFixed(0)}만원</span>
        </div>
      </div>

      {/* 검증 에러 */}
      {validationError && (
        <div
          data-testid="price-filter-validation-error"
          className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded text-sm text-red-700"
        >
          {validationError}
        </div>
      )}

      {/* 저장 toast */}
      {saveToast && (
        <div
          data-testid="price-filter-save-toast"
          className="mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded text-sm text-green-700"
        >
          {saveToast}
        </div>
      )}

      {/* 안내 */}
      <div className="mb-4 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-2">
        본 필터는 매수 진입에만 적용됩니다. 보유 종목 매도 / 익일청산 / 손절
        / 트레일링 스탑 영향 0.
      </div>

      {/* 저장 버튼 */}
      <div className="flex justify-end">
        <button
          type="button"
          data-testid="price-filter-save-button"
          onClick={onSave}
          disabled={!dirty || mutation.isPending}
          className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {mutation.isPending ? '저장 중...' : '저장 (즉시 반영)'}
        </button>
      </div>
    </div>
  )
}
