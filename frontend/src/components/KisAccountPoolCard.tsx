/**
 * 사이클 7-D (2026-05-18): Dashboard — WebsocketPool 세션 상태 + 슬롯 사용률.
 *
 * `/api/realtime/subscriptions` 응답의 sessions 배열을 표로 노출:
 * - label / ws_connected 배지 / subscribed/limit / fresh / stale / 재연결
 * - 보조 0개 시 메인 1행 + "보조 세션 없음 (메인 only)" 안내
 * - 총 슬롯 (41 × N) + 사용률 % 진행바
 * - 새로고침 버튼 (수동 트리거)
 *
 * 위치: Dashboard MarketRegimeCard 직하 (시장 상태 → 인프라 상태 위계).
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { getSubscriptions } from '../api/realtime'
import type { SubscriptionSession } from '../api/realtime'

function statusBadgeClass(connected: boolean): string {
  return connected
    ? 'inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-800 border border-emerald-300'
    : 'inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-800 border border-red-300'
}

function sessionLabelBadge(label: string): string {
  if (label === 'main') {
    return 'bg-blue-100 text-blue-800 border border-blue-300'
  }
  return 'bg-gray-100 text-gray-700 border border-gray-300'
}

export default function KisAccountPoolCard() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['realtime-subscriptions'],
    queryFn: getSubscriptions,
    staleTime: 5_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })

  const sessions: SubscriptionSession[] = data?.sessions ?? []
  const totalSlots = data?.limit ?? 0
  const totalUsed = data?.total ?? 0
  const usagePct = totalSlots > 0 ? Math.min(100, (totalUsed / totalSlots) * 100) : 0

  const hasSecondary = sessions.some((s) => s.label !== 'main')

  const onRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['realtime-subscriptions'] })
  }

  const progressColor = usagePct >= 80 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <div
      className="bg-white rounded-lg shadow p-6 mb-6"
      data-testid="kis-account-pool-card"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            KIS 시세 풀 (WebsocketPool)
          </h2>
          <p className="text-xs text-gray-500 mt-1">
            메인 + 보조 시세 세션 상태. 매매·잔고·체결통보는 메인 단일 — 본 카드는 시세 분배 모니터링만.
          </p>
        </div>
        <button
          type="button"
          data-testid="pool-refresh-button"
          onClick={onRefresh}
          disabled={isLoading}
          className="text-xs px-2 py-1 border border-gray-300 rounded text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          새로고침
        </button>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-500">시세 풀 상태 로딩 중...</div>
      ) : isError ? (
        <div
          className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3"
          data-testid="pool-error-message"
        >
          시세 풀 상태를 불러오지 못했습니다. 잠시 후 재시도하세요.
        </div>
      ) : (
        <>
          {/* 총 슬롯 + 사용률 진행바 */}
          <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-500">
                총 슬롯 사용률 (41 × {sessions.length || 1})
              </span>
              <span className="text-xs font-mono text-gray-700">
                <span data-testid="pool-used-slots">{totalUsed}</span>
                {' / '}
                <span data-testid="pool-total-slots">{totalSlots}</span>
                {' '}({usagePct.toFixed(0)}%)
              </span>
            </div>
            <div className="h-2 bg-gray-200 rounded overflow-hidden">
              <div
                data-testid="pool-usage-progress"
                className={`h-full transition-all duration-300 ${progressColor}`}
                style={{ width: `${usagePct}%` }}
              />
            </div>
            <div className="mt-1 text-[11px] text-gray-500 flex gap-3">
              <span>
                정상(fresh):{' '}
                <span className="text-emerald-700 font-medium">{data?.fresh_60s ?? 0}</span>
              </span>
              <span>
                끊김(stale):{' '}
                <span className="text-amber-700 font-medium">{data?.stale_60s ?? 0}</span>
              </span>
              <span>
                ACK:{' '}
                <span className="text-blue-700 font-medium">{data?.acked ?? 0}</span>
              </span>
            </div>
          </div>

          {/* 세션별 표 */}
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="text-gray-500 text-left border-b border-gray-200">
                  <th className="py-2 px-2 font-medium">세션</th>
                  <th className="py-2 px-2 font-medium">연결</th>
                  <th className="py-2 px-2 font-medium">구독</th>
                  <th className="py-2 px-2 font-medium">진행</th>
                  <th className="py-2 px-2 font-medium">정상</th>
                  <th className="py-2 px-2 font-medium">끊김</th>
                  <th className="py-2 px-2 font-medium">재연결</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => {
                  const pct = s.limit > 0 ? Math.min(100, (s.subscribed / s.limit) * 100) : 0
                  const isMain = s.label === 'main'
                  return (
                    <tr
                      key={s.label}
                      data-testid={`pool-session-row-${s.label}`}
                      className="border-b border-gray-100"
                    >
                      <td className="py-2 px-2">
                        <span
                          className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${sessionLabelBadge(
                            s.label,
                          )}`}
                        >
                          {s.label}
                        </span>
                        {isMain && (
                          <span className="ml-1 text-[10px] text-blue-700">
                            (체결통보)
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2">
                        <span
                          data-testid={`pool-session-status-${s.label}`}
                          className={statusBadgeClass(s.ws_connected)}
                        >
                          {s.ws_connected ? 'connected' : 'disconnected'}
                        </span>
                      </td>
                      <td className="py-2 px-2 font-mono text-gray-700">
                        {s.subscribed} / {s.limit}
                      </td>
                      <td className="py-2 px-2 w-32">
                        <div className="h-1.5 bg-gray-200 rounded overflow-hidden">
                          <div
                            data-testid={`pool-session-progress-${s.label}`}
                            className={
                              pct >= 80 ? 'h-full bg-amber-500' : 'h-full bg-emerald-500'
                            }
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-2 font-mono text-emerald-700">{s.fresh}</td>
                      <td className="py-2 px-2 font-mono text-amber-700">{s.stale}</td>
                      <td className="py-2 px-2 font-mono text-gray-600">
                        {s.reconnect_count}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {!hasSecondary && (
            <div
              className="mt-3 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded p-2"
              data-testid="pool-no-secondary-note"
            >
              보조 세션 없음 (메인 only). Settings &gt; 보조 KIS 시세 계좌에서 등록하면 다음 _boot(07:50) 부터 슬롯이 41 × (1 + N) 으로 확장됩니다.
            </div>
          )}
        </>
      )}
    </div>
  )
}
