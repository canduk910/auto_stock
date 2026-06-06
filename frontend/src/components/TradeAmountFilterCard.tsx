/**
 * 거래대금 동행 필터 카드 (사이클 65, 2026-06-06).
 *
 * 기능:
 * - scanner 단계 WebSocket 구독 대상 거래대금 필터 설정 (작전주/저유동성 차단)
 * - 임계 미만 종목은 WebSocket 구독 자체 차단 (사이클 64 가격 필터 순차 hook)
 * - 보유/익일청산 종목은 절대 제외 안 됨 (사이클 64 Q1 옵션 D 3 중 안전망 답습)
 * - 09:00 직후 거래대금 미반영 종목은 graceful 통과 (Q6-1)
 * - 저장 즉시 반영 (백엔드 60s TTL 캐시 invalidate)
 * - Q7-1: invalidate 가 unsubscribe 발화 0 (5분 자연 delta, KIS LMS chain 차단)
 *
 * Q1 자문 확정:
 * - 디폴트 0 (비활성)
 * - 슬라이더 범위: 0~100억 step 1억
 * - 권장값 마커: 1억 / 5억 / 10억
 *
 * testid 매트릭스 (Red 명세 §F-FE 기준):
 *   trade-amount-filter-card           — 카드 컨테이너
 *   trade-amount-filter-min-slider     — 최소거래대금 슬라이더 (0~100억, step 1억)
 *   trade-amount-filter-save-button    — 저장 버튼
 *   trade-amount-filter-save-toast     — 저장 성공 안내
 *
 * 패턴 답습: PriceFilterCard.tsx (사이클 64) — 동일 구조
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getTradeAmountFilter,
  updateTradeAmountFilter,
} from '../api/trade-amount-filter'

// 슬라이더 범위 (Q1 자문 확정 — 0~100억 step 1억)
const MIN_AMOUNT_MAX = 10_000_000_000 // 100억
const MIN_AMOUNT_STEP = 100_000_000 // 1억

// 권장값 마커 (Q1 자문 권고 — 1억 / 5억 / 10억)
const RECOMMENDED_MARKERS: { label: string; value: number }[] = [
  { label: '1억', value: 100_000_000 },
  { label: '5억', value: 500_000_000 },
  { label: '10억', value: 1_000_000_000 },
]

function formatAmount(value: number): string {
  if (value === 0) return '0 (비활성)'
  if (value >= 100_000_000) {
    const eok = value / 100_000_000
    return `${eok % 1 === 0 ? eok.toFixed(0) : eok.toFixed(1)}억원`
  }
  return `${value.toLocaleString('ko-KR')}원`
}

export default function TradeAmountFilterCard() {
  const queryClient = useQueryClient()

  const [minAmount, setMinAmount] = useState<number>(0)
  const [dirty, setDirty] = useState(false)
  const [saveToast, setSaveToast] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['tradeAmountFilter'],
    queryFn: getTradeAmountFilter,
  })

  useEffect(() => {
    if (data) {
      setMinAmount(data.min_amount)
      setDirty(false)
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: updateTradeAmountFilter,
    onSuccess: (saved) => {
      setMinAmount(saved.min_amount)
      setDirty(false)
      setSaveToast('거래대금 필터가 즉시 반영되었습니다')
      queryClient.invalidateQueries({ queryKey: ['tradeAmountFilter'] })
      // toast 3초 후 자동 닫기
      setTimeout(() => setSaveToast(null), 3000)
    },
  })

  const onSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMinAmount(Number(e.target.value))
    setDirty(true)
    setSaveToast(null)
  }

  const onMarkerClick = (value: number) => {
    setMinAmount(value)
    setDirty(true)
    setSaveToast(null)
  }

  const onSave = () => {
    mutation.mutate({ min_amount: minAmount })
  }

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="text-gray-500 text-sm">거래대금 필터 로딩 중...</div>
      </div>
    )
  }

  return (
    <div
      data-testid="trade-amount-filter-card"
      className="bg-white rounded-lg shadow p-6 mb-6"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold text-gray-900">
          거래대금 동행 필터 (사이클 65)
        </h2>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
          WebSocket 구독 대상 필터
        </span>
      </div>

      {/* 안내 배너 (Q6-1 + 보유 보호 필수 명시) */}
      <div className="mb-4 px-3 py-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-700 space-y-1">
        <div>
          <strong>거래대금 동행 필터</strong> — 임계 미만 종목은 WebSocket 구독
          자체 차단. 작전주/저유동성 차단 (사이클 64 갭상승 회피 보강).
        </div>
        <div>보유/익일청산 종목은 절대 제외 안 됨</div>
        <div>
          <strong>09:00 직후 거래대금 미반영 종목은 graceful 통과</strong>{' '}
          (Q6-1) — 장 시작 직후 누적 미반영 시 차단 없이 통과
        </div>
      </div>

      {/* 최소 거래대금 슬라이더 */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-1">
          <label className="text-sm font-medium text-gray-700">
            최소 거래대금 (원, 0 = 비활성)
          </label>
          <span className="text-sm font-mono font-medium text-blue-600">
            {formatAmount(minAmount)}
          </span>
        </div>
        <input
          type="range"
          data-testid="trade-amount-filter-min-slider"
          min={0}
          max={MIN_AMOUNT_MAX}
          step={MIN_AMOUNT_STEP}
          value={minAmount}
          onChange={onSliderChange}
          className="w-full h-2 rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: '#2563eb' }}
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>0 (비활성)</span>
          <span>{(MIN_AMOUNT_MAX / 100_000_000).toFixed(0)}억원</span>
        </div>

        {/* 권장값 마커 버튼 (Q1 자문 — 1억 / 5억 / 10억) */}
        <div className="flex gap-2 mt-2">
          <span className="text-xs text-gray-500 self-center">권장:</span>
          {RECOMMENDED_MARKERS.map(({ label, value }) => (
            <button
              key={label}
              type="button"
              onClick={() => onMarkerClick(value)}
              className={`px-3 py-1 text-xs rounded border transition-colors ${
                minAmount === value
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-blue-600 border-blue-300 hover:bg-blue-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 저장 toast */}
      {saveToast && (
        <div
          data-testid="trade-amount-filter-save-toast"
          className="mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded text-sm text-green-700"
        >
          {saveToast}
        </div>
      )}

      {/* 저장 버튼 */}
      <div className="flex justify-end">
        <button
          type="button"
          data-testid="trade-amount-filter-save-button"
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
