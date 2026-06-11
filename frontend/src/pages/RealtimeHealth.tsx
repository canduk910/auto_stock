/**
 * 사이클 103 영역 0 — 실시간 건강 모니터링 페이지.
 *
 * 4 카드:
 *   - [dispatch_drop_summary]: 메시지 누락 집계
 *   - [callback_exception]:    콜백 예외
 *   - [stale_force_retry]:     강제 재구독
 *   - [ws_auto_restart]:       자동 재기동 (사이클 92, 0건 = 정상)
 *
 * 영속 의무:
 *   - 사이클 65 H3 useQuery retry:1 영속
 *   - 사이클 68 KST 영속 (Intl.DateTimeFormat timeZone='Asia/Seoul')
 *   - 사이클 89 한글 친숙 용어 + 사이클 언급 0 영속
 *   - 빈 데이터 graceful (0건 정상 영역)
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRealtimeHealth } from '../api/realtime-health'
import type { TimeWindow, RealtimeHealthCard } from '../types/realtime-health'

// KST 시각 표시 헬퍼 — getHours() 사용 금지 (사이클 68 G-AST 영속)
function formatKst(isoStr: string): string {
  if (!isoStr) return '—'
  try {
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(isoStr))
  } catch {
    return isoStr
  }
}

interface CardConfig {
  testId: string
  title: string
  description: string
  levelColor: (level: string) => string
}

const CARD_CONFIGS: Record<string, CardConfig> = {
  dispatch_drop: {
    testId: 'realtime-health-card-dispatch-drop',
    title: '메시지 누락',
    description: '시세 수신 후 콜백 dispatch 누락 집계 (dispatch_drop_summary)',
    levelColor: (level) =>
      level === 'ERROR' ? 'text-red-600' : level === 'WARNING' ? 'text-amber-600' : 'text-gray-600',
  },
  callback_exception: {
    testId: 'realtime-health-card-callback-exception',
    title: '콜백 예외',
    description: 'on_tick / on_execution / on_board 핸들러 예외 발생 (callback_exception)',
    levelColor: (_level) => 'text-red-600',
  },
  stale_force_retry: {
    testId: 'realtime-health-card-stale-force-retry',
    title: '강제 재구독',
    description: 'K stale watcher — 오래된 시세 종목 강제 재구독 (stale_force_retry)',
    levelColor: (level) =>
      level === 'WARNING' ? 'text-amber-600' : level === 'ERROR' ? 'text-red-600' : 'text-gray-600',
  },
  ws_auto_restart: {
    testId: 'realtime-health-card-ws-auto-restart',
    title: '자동 재기동',
    description: 'WebSocket 최대 재연결 초과 시 자동 재기동 (ws_auto_restart). 0건 = 정상',
    levelColor: (_level) => 'text-amber-600',
  },
}

type CardKey = 'dispatch_drop' | 'callback_exception' | 'stale_force_retry' | 'ws_auto_restart'

function RealtimeHealthCardView({
  cardKey,
  card,
  config,
}: {
  cardKey: CardKey
  card: RealtimeHealthCard | undefined
  config: CardConfig
}) {
  const count = card?.count ?? 0
  const logs = card?.logs ?? []

  const badgeColor =
    cardKey === 'ws_auto_restart'
      ? count === 0
        ? 'bg-green-100 text-green-800'
        : 'bg-amber-100 text-amber-800'
      : count === 0
      ? 'bg-gray-100 text-gray-600'
      : 'bg-red-100 text-red-700'

  return (
    <div
      data-testid={config.testId}
      className="bg-white rounded-lg shadow p-4"
    >
      {/* 카드 헤더 */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900">{config.title}</h3>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badgeColor}`}>
          {count}건
        </span>
      </div>
      <p className="text-xs text-gray-500 mb-3">{config.description}</p>

      {/* 로그 목록 */}
      {logs.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          {cardKey === 'ws_auto_restart' ? '0건 — 정상' : '데이터 없음'}
        </p>
      ) : (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {logs.slice(0, 20).map((log) => (
            <div
              key={log.id}
              className="text-xs border-l-2 border-gray-200 pl-2 py-0.5"
            >
              <span className={`font-medium mr-1 ${config.levelColor(log.level)}`}>
                {log.level}
              </span>
              <span className="text-gray-400 mr-1">{formatKst(log.created_at)}</span>
              <span className="text-gray-700 break-all">{log.message}</span>
            </div>
          ))}
          {logs.length > 20 && (
            <p className="text-xs text-gray-400 text-right">… 외 {logs.length - 20}건</p>
          )}
        </div>
      )}
    </div>
  )
}

export default function RealtimeHealth() {
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('24h')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['realtime-health', timeWindow],
    queryFn: () => fetchRealtimeHealth(timeWindow),
    retry: 1, // 사이클 65 H3 영속
    refetchInterval: 60_000, // 60s polling
    staleTime: 30_000,
  })

  return (
    <div className="space-y-4">
      {/* 페이지 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">실시간 건강 모니터링</h1>
          <p className="text-sm text-gray-500">
            WebSocket 시세 수신 / 콜백 / 재구독 / 재기동 이상 징후 추적
          </p>
        </div>

        {/* 시간 윈도우 토글 — 사이클 103 MEDIUM-2 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">기간:</span>
          <button
            data-testid="realtime-health-window-24h"
            onClick={() => setTimeWindow('24h')}
            className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${
              timeWindow === '24h'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            24시간
          </button>
          <button
            data-testid="realtime-health-window-7d"
            onClick={() => setTimeWindow('7d')}
            className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${
              timeWindow === '7d'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            7일
          </button>
        </div>
      </div>

      {/* 로딩 상태 */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
              <div className="h-3 bg-gray-100 rounded w-2/3 mb-4" />
              <div className="space-y-2">
                <div className="h-3 bg-gray-100 rounded" />
                <div className="h-3 bg-gray-100 rounded w-4/5" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 에러 상태 */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">서버 연결 끊김 — 로그 조회 실패</p>
        </div>
      )}

      {/* 4 카드 그리드 */}
      {!isLoading && !isError && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(
            [
              'dispatch_drop',
              'callback_exception',
              'stale_force_retry',
              'ws_auto_restart',
            ] as CardKey[]
          ).map((key) => (
            <RealtimeHealthCardView
              key={key}
              cardKey={key}
              card={data?.[key]}
              config={CARD_CONFIGS[key]}
            />
          ))}
        </div>
      )}

      {/* 안내 영역 */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
        <p className="text-xs text-gray-500">
          system_logs 검색 기반 집계. 보유/익일청산 종목 재구독은 항상 정상 작동.
          자동 재기동 0건 = 정상 (사이클 92 60s 쿨다운 가드 영속).
        </p>
      </div>
    </div>
  )
}
