/**
 * 가격 필터 카드 (사이클 64, 2026-06-06 — mode 단순화).
 *
 * 사이클 62 → 64 변경:
 * - mode select 제거 (HARD/WARN/OFF 모드 폐기)
 * - state mode 제거
 * - mutation body 의 mode 필드 제거
 * - 안내 배너 갱신 — "WebSocket 구독 대상 필터" + "보유/익일청산 절대 제외 안 됨"
 *
 * 기능:
 * - scanner 단계 WebSocket 구독 대상 가격 필터 설정 (저가주 차단 + 초고가주 차단)
 * - 임계 외 종목은 시세 구독 자체 차단
 * - 보유/익일청산 종목은 절대 제외 안 됨 (사이클 32 R4 universe guard + 사이클 64 Q1 옵션 D)
 * - 저장 즉시 반영 (백엔드 60s TTL 캐시 invalidate)
 *
 * testid 매트릭스 (Red 명세 §F-FE 기준):
 *   price-filter-card          — 카드 컨테이너
 *   price-filter-min-slider    — 최소가 슬라이더 (0~20,000원, step 1,000)
 *   price-filter-max-slider    — 최대가 슬라이더 (0~2,000,000원, step 50,000)
 *   price-filter-save-button   — 저장 버튼
 *   price-filter-save-toast    — 저장 성공 안내
 *   price-filter-validation-error — max < min 에러
 *
 * 폐기 (사이클 64):
 *   price-filter-mode-select   — HARD/WARN/OFF 셀렉트 (mode 필드 자체 폐기)
 *
 * 패턴 답습: CashUsageRatioCard (슬라이더 + 명시 저장 버튼)
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getPriceFilter, updatePriceFilter } from '../api/price-filter'

// 권장값 (자문 Q1 확정 — UI 툴팁만, DB 디폴트 아님)
const RECOMMENDED_MIN = 5_000
const RECOMMENDED_MAX = 1_000_000

// 슬라이더 범위 (자문 Q1 확정)
const MIN_SLIDER_MAX = 20_000
const MIN_SLIDER_STEP = 1_000
const MAX_SLIDER_MAX = 2_000_000
const MAX_SLIDER_STEP = 50_000

function formatPrice(value: number): string {
  if (value === 0) return '0 (비활성)'
  return `${value.toLocaleString('ko-KR')}원`
}

export default function PriceFilterCard() {
  const queryClient = useQueryClient()

  const [minPrice, setMinPrice] = useState<number>(0)
  const [maxPrice, setMaxPrice] = useState<number>(0)
  const [dirty, setDirty] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [saveToast, setSaveToast] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['priceFilter'],
    queryFn: getPriceFilter,
    retry: 1,  // 사이클 65 hotfix H1 — e2e ECONNREFUSED 빠른 실패 (기본 3 → 1)
  })

  useEffect(() => {
    if (data) {
      setMinPrice(data.min_price)
      setMaxPrice(data.max_price)
      setDirty(false)
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: updatePriceFilter,
    onSuccess: (saved) => {
      setMinPrice(saved.min_price)
      setMaxPrice(saved.max_price)
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
    // 사이클 64 — mode 필드 미포함 (PriceFilterUpdate 에서 mode 제거)
    mutation.mutate({ min_price: minPrice, max_price: maxPrice })
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
          WebSocket 구독 대상 필터
        </span>
      </div>

      {/* 사이클 64 안내 배너 — "WebSocket 구독 대상 필터" 갱신 */}
      <div className="mb-4 px-3 py-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-700">
        WebSocket 구독 대상 필터 — 임계 외 종목은 시세 구독 자체 차단.
        보유/익일청산 종목은 절대 제외 안 됨.
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
          style={{ accentColor: 'var(--color-navy-600)' }}
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
          style={{ accentColor: 'var(--color-navy-600)' }}
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
