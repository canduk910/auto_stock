/**
 * 시세수신현황 페이지 (사이클 15-C-2, 2026-05-19).
 *
 * REST/WS/탈락 3 탭 — `stream_pool_manager.snapshot()` 응답 가시화.
 * - REST: REST 폴링 관찰 중인 종목 (임박 후보 검사 대상)
 * - WS: WS 풀에 활성 구독 중 (매수 신호 평가 대상)
 * - 탈락 (cooldown): 강등 후 재승격 제한 중
 *
 * 30s 자동 폴링 + 수동 새로고침. 매매 영향 0 — 단순 모니터링.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { StreamEntry } from '../api/realtime'
import { getStreamStatus } from '../api/realtime'

type TabKey = 'rest' | 'ws' | 'dropped'

const TAB_LABELS: Record<TabKey, string> = {
  rest: 'REST 관찰',
  ws: 'WS 활성',
  dropped: '탈락 (cooldown)',
}

const STRATEGY_LABELS: Record<string, string> = {
  positions: '보유',
  next_day_clear: '익일청산',
  momentum: '상한가 모멘텀',
  volatility_breakout: '변동성 돌파',
  long_tail_volatility: '롱테일 변동성',
  donchian_swing: '돈치안 스윙',
  bull_flag_breakout: '눌림목 돌파',
  vcp_breakout: 'VCP 변동성 수축',
}

function strategyLabel(strategy: string): string {
  return STRATEGY_LABELS[strategy] ?? strategy
}

function formatSecs(secs: number | undefined): string {
  if (secs === undefined || secs < 0) return '-'
  if (secs < 60) return `${Math.round(secs)}초`
  const min = Math.floor(secs / 60)
  const rem = Math.round(secs % 60)
  return `${min}분 ${rem}초`
}

function EmptyMessage({ label }: { label: string }) {
  return (
    <div
      data-testid={`stream-empty-${label}`}
      className="text-center py-10 text-gray-500 text-sm"
    >
      해당 카테고리에 종목이 없습니다.
    </div>
  )
}

function StreamTable({
  entries,
  remainingKey,
  remainingLabel,
  tabKey,
}: {
  entries: StreamEntry[]
  remainingKey?: 'min_hold_remaining_secs' | 'cooldown_remaining_secs'
  remainingLabel?: string
  tabKey: TabKey
}) {
  if (entries.length === 0) {
    return <EmptyMessage label={tabKey} />
  }
  return (
    <table
      data-testid={`stream-table-${tabKey}`}
      className="min-w-full divide-y divide-gray-200 text-sm"
    >
      <thead className="bg-gray-50">
        <tr>
          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">종목</th>
          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">전략</th>
          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">사유</th>
          <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">
            등록 후 경과
          </th>
          {remainingKey && remainingLabel && (
            <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">
              {remainingLabel}
            </th>
          )}
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-gray-100">
        {entries.map((entry) => (
          <tr key={entry.ticker} data-testid={`stream-row-${tabKey}-${entry.ticker}`}>
            <td className="px-3 py-2 font-medium text-gray-900">{entry.ticker}</td>
            <td className="px-3 py-2 text-gray-700">{strategyLabel(entry.strategy)}</td>
            <td className="px-3 py-2 text-gray-600 text-xs">{entry.reason}</td>
            <td className="px-3 py-2 text-right text-gray-700">
              {formatSecs(entry.since_secs)}
            </td>
            {remainingKey && (
              <td className="px-3 py-2 text-right text-gray-700">
                {formatSecs(entry[remainingKey])}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function StreamStatus() {
  const [tab, setTab] = useState<TabKey>('ws')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['stream-status'],
    queryFn: getStreamStatus,
    refetchInterval: 30_000,
    staleTime: 5_000,
    refetchOnWindowFocus: false,
  })

  const counts = {
    rest: data?.rest.length ?? 0,
    ws: data?.ws.length ?? 0,
    dropped: data?.dropped.length ?? 0,
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">시세수신현황</h1>
          <p className="text-sm text-gray-500 mt-1">
            REST 관찰 → 임박 종목 WS 승격 → 강등 후 cooldown. 사이클 15-B 풀 매니저
            상태.
          </p>
        </div>
        <button
          data-testid="stream-refresh"
          type="button"
          onClick={() => refetch()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          새로고침
        </button>
      </div>

      <div className="border-b border-gray-200 mb-4">
        <nav className="flex gap-1" role="tablist">
          {(Object.keys(TAB_LABELS) as TabKey[]).map((key) => (
            <button
              key={key}
              role="tab"
              data-testid={`stream-tab-${key}`}
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 ${
                tab === key
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              {TAB_LABELS[key]} ({counts[key]})
            </button>
          ))}
        </nav>
      </div>

      {isLoading && (
        <div data-testid="stream-loading" className="text-center py-10 text-gray-500">
          불러오는 중...
        </div>
      )}

      {isError && (
        <div data-testid="stream-error" className="text-center py-10 text-red-600">
          상태 조회 실패. 잠시 후 재시도하세요.
        </div>
      )}

      {data && !isLoading && !isError && (
        <div className="overflow-x-auto">
          {tab === 'rest' && (
            <StreamTable entries={data.rest} tabKey="rest" />
          )}
          {tab === 'ws' && (
            <StreamTable
              entries={data.ws}
              tabKey="ws"
              remainingKey="min_hold_remaining_secs"
              remainingLabel="최소 유지 남은시간"
            />
          )}
          {tab === 'dropped' && (
            <StreamTable
              entries={data.dropped}
              tabKey="dropped"
              remainingKey="cooldown_remaining_secs"
              remainingLabel="cooldown 남은시간"
            />
          )}
        </div>
      )}
    </div>
  )
}
