/**
 * 사이클 103 영역 1 — 전략별 손절 임계 가시화 페이지.
 *
 * GET /api/strategies 영역 활용 (params JSONB 포함 영속 확인 완료).
 *
 * 4 임계 표시:
 *   - stop_loss_rate:      손절 임계
 *   - daily_loss_limit:    일일 손실 한도
 *   - trailing_stop_rate:  트레일링 임계
 *   - position_ratio:      종목당 포지션 비율
 *
 * 영속 의무:
 *   - 사이클 65 H3 useQuery retry:1 영속
 *   - 사이클 68 KST 영속 (Intl.DateTimeFormat)
 *   - 사이클 89 한글 친숙 용어 + 사이클 언급 0 영속
 *   - 데이터 부재 시 graceful (params={} → "—")
 *   - 모바일 viewport 375px 정합
 */
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { ApiResponse } from '../types/common'
import { getStrategyColor } from '../types/strategy'

// 전략 응답 타입 — GET /api/strategies 영역 정합
interface StrategyStatus {
  key?: string         // strategies dict의 키 (route 응답 형식에 따라 다름)
  name: string
  enabled: boolean
  weight: number
  params: Record<string, number | string | string[] | null | undefined>
  total_investment: number
  invested_amount?: number
  min_weight?: number
  positions?: number
  pending_buys?: number
}

interface StrategiesResponse {
  strategies: Record<string, StrategyStatus> | StrategyStatus[]
}

// 백분율 포맷 헬퍼
function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  const n = Number(val)
  if (isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

// 임계 색상 — 손절/손실은 파랑(손실색), 포지션비율은 중립
function thresholdColor(key: string, val: number | null | undefined): string {
  if (val === null || val === undefined) return 'text-gray-400'
  const n = Number(val)
  if (isNaN(n)) return 'text-gray-400'
  if (key === 'position_ratio') return 'text-gray-700'
  // 손절/손실 임계 — 음수면 손실색(파랑), 양수면 이익색(빨강)
  return n < 0 ? 'text-blue-600' : 'text-red-600'
}

const PARAM_LABELS: Record<string, string> = {
  stop_loss_rate: '손절 임계',
  daily_loss_limit: '일일 손실 한도',
  trailing_stop_rate: '트레일링 임계',
  position_ratio: '종목당 비율',
}

const THRESHOLD_KEYS = [
  'stop_loss_rate',
  'daily_loss_limit',
  'trailing_stop_rate',
  'position_ratio',
] as const

type ThresholdKey = typeof THRESHOLD_KEYS[number]

function StrategyCard({
  strategyKey,
  strategy,
}: {
  strategyKey: string
  strategy: StrategyStatus
}) {
  const color = getStrategyColor(strategyKey)

  return (
    <div
      data-testid={`strategy-card-${strategyKey}`}
      className={`bg-white rounded-lg shadow p-4 border-l-4 ${color.bg}`}
      style={{ borderLeftColor: color.hex }}
    >
      {/* 카드 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{strategy.name}</h3>
          <p className="text-xs text-gray-500">
            비중 {(strategy.weight * 100).toFixed(0)}%
            {strategy.total_investment > 0 &&
              ` · 배정 ${(strategy.total_investment / 10000).toFixed(0)}만원`}
          </p>
        </div>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
            strategy.enabled
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-500'
          }`}
        >
          {strategy.enabled ? '활성' : '비활성'}
        </span>
      </div>

      {/* 4 임계 그리드 */}
      <div className="grid grid-cols-2 gap-2">
        {THRESHOLD_KEYS.map((key) => {
          const val = strategy.params[key] as number | null | undefined
          const testId = `strategy-${strategyKey}-${key.replace(/_/g, '-')}`
          return (
            <div
              key={key}
              className="bg-gray-50 rounded p-2"
            >
              <p className="text-xs text-gray-500 mb-0.5">{PARAM_LABELS[key]}</p>
              <p
                data-testid={testId}
                className={`text-sm font-semibold ${thresholdColor(key, val)}`}
              >
                {key === 'position_ratio'
                  ? val !== null && val !== undefined && !isNaN(Number(val))
                    ? `${(Number(val) * 100).toFixed(0)}%`
                    : '—'
                  : formatPercent(val)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Strategies() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const resp = await apiClient.get<ApiResponse<StrategiesResponse>>('/strategies')
      return resp.data.data
    },
    retry: 1, // 사이클 65 H3 영속
    refetchInterval: 60_000,
    staleTime: 15_000,
  })

  // strategies는 dict 또는 배열 양쪽 처리.
  // 백엔드 GET /api/strategies 가 플랫 형식 { momentum: {...}, ... } 반환 시
  // data?.strategies = undefined → data 자체를 플랫 형식으로 fallback.
  const strategiesMap: Record<string, StrategyStatus> = (() => {
    const raw = data?.strategies ?? data
    if (!raw) return {}
    if (Array.isArray(raw)) {
      // 배열 형식 (key 필드 사용)
      return Object.fromEntries(
        raw.map((s) => [s.key ?? String(Math.random()), s])
      )
    }
    return raw as Record<string, StrategyStatus>
  })()

  const strategyKeys = Object.keys(strategiesMap)

  return (
    <div className="space-y-4">
      {/* 페이지 헤더 */}
      <div>
        <h1 className="text-lg font-bold text-gray-900">전략 현황</h1>
        <p className="text-sm text-gray-500">
          전략별 손절·트레일링·포지션 임계 실시간 모니터링
        </p>
      </div>

      {/* 로딩 */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
              <div className="h-5 bg-gray-200 rounded w-1/3 mb-3" />
              <div className="grid grid-cols-2 gap-2">
                {[1, 2, 3, 4].map((j) => (
                  <div key={j} className="bg-gray-50 rounded p-2">
                    <div className="h-3 bg-gray-200 rounded w-2/3 mb-1" />
                    <div className="h-4 bg-gray-100 rounded w-1/2" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 에러 */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">서버 연결 끊김 — 전략 조회 실패</p>
        </div>
      )}

      {/* 데이터 없음 */}
      {!isLoading && !isError && strategyKeys.length === 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-sm text-gray-500">등록된 전략이 없습니다.</p>
        </div>
      )}

      {/* 전략 카드 그리드 */}
      {!isLoading && !isError && strategyKeys.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {strategyKeys.map((key) => (
            <StrategyCard
              key={key}
              strategyKey={key}
              strategy={strategiesMap[key]}
            />
          ))}
        </div>
      )}

      {/* 안내 */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
        <p className="text-xs text-amber-700">
          손절·일일 손실 한도는 음수(파란색) 표시. 트레일링은 고가 대비 하락 임계.
          종목당 비율 = 전략 배정 자금 대비 단일 종목 매수 비율.
        </p>
      </div>
    </div>
  )
}
