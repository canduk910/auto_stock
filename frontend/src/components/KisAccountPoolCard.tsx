/**
 * 사이클 7-D (2026-05-18): Dashboard — WebsocketPool 세션 상태 + 슬롯 사용률.
 *
 * `/api/realtime/subscriptions` 응답의 sessions 배열을 표로 노출:
 * - label / ws_connected 배지 / subscribed/limit / fresh / stale / 재연결
 * - 보조 0개 시 메인 1행 + "보조 세션 없음 (메인 only)" 안내
 * - 총 슬롯 (41 × N) + 사용률 % 진행바
 * - 새로고침 버튼 (수동 트리거)
 *
 * 사이클 21 (2026-05-20): ScanMonitor 의 사이클 18 끊김 영역 통합.
 * - stale_60s > 0 시 stale-context-label (KRX 메인/PRE_NXT/그 외)
 * - pool-resubscribe-button (수동 재구독)
 * - pool-stale-list-toggle + pool-stale-row-{ticker} (마지막 tick KST HH:MM:SS)
 *
 * 위치: Dashboard MarketRegimeCard 직하 (시장 상태 → 인프라 상태 위계).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getSubscriptions, resubscribeStale } from '../api/realtime'
import type { SubscriptionSession, SubscriptionTickerDetail } from '../api/realtime'
import {
  getKstMinutes,
  getStaleContextByKstMinutes,
  STALE_CONTEXT_META,
  formatLastTickKst,
} from '../utils/stale-context'
import ScrollPane from './ScrollPane'

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

/**
 * 사이클 37 (2026-05-21) — KIS 체결시각 HHMMSS → HH:MM:SS 표시.
 */
function formatCntgHour(hhmmss: string | null): string {
  if (!hhmmss || hhmmss.length !== 6) return '—'
  return `${hhmmss.slice(0, 2)}:${hhmmss.slice(2, 4)}:${hhmmss.slice(4, 6)}`
}

/**
 * 사이클 37 — WS 구독 의심 판정.
 *
 * last_tick (WS 수신 ISO) 와 last_cntg_hour (KIS 실제 HHMMSS, KST 가정) 비교.
 * 차이가 5분(300초) 이상이면 WS 구독 문제 의심 (KIS 정상 송출 중인데 우리만 못 받음).
 *
 * 둘 중 하나라도 없으면 판정 불가 → false (정상 톤).
 */
function isWsSubscriptionSuspect(
  lastTickIso: string | null,
  lastCntgHour: string | null,
): boolean {
  if (!lastTickIso || !lastCntgHour || lastCntgHour.length !== 6) {
    return false
  }
  // last_tick ISO → KST HHMMSS 추출
  // Intl.DateTimeFormat 사용 (브라우저 로컬타임 추출 금지 컨벤션 준수)
  try {
    const tickDate = new Date(lastTickIso)
    if (Number.isNaN(tickDate.getTime())) return false
    const fmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Seoul',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    const tickHms = fmt.format(tickDate).replace(/:/g, '')
    if (tickHms.length !== 6) return false
    // HHMMSS 문자열 비교는 분 단위로 차이 계산 (당일 KST 기준)
    const tickSecs =
      parseInt(tickHms.slice(0, 2), 10) * 3600 +
      parseInt(tickHms.slice(2, 4), 10) * 60 +
      parseInt(tickHms.slice(4, 6), 10)
    const ccnlSecs =
      parseInt(lastCntgHour.slice(0, 2), 10) * 3600 +
      parseInt(lastCntgHour.slice(2, 4), 10) * 60 +
      parseInt(lastCntgHour.slice(4, 6), 10)
    // KIS 체결시각이 WS 수신 시각보다 5분 이상 최신 → WS 구독 의심
    return ccnlSecs - tickSecs >= 300
  } catch {
    return false
  }
}

export default function KisAccountPoolCard() {
  const queryClient = useQueryClient()
  const [staleListOpen, setStaleListOpen] = useState(false)
  const [resubMsg, setResubMsg] = useState<string | null>(null)
  // 사이클 35 (2026-05-21) — 세션별 종목 expand
  const [expandedSession, setExpandedSession] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['realtime-subscriptions'],
    queryFn: getSubscriptions,
    staleTime: 5_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })

  // 사이클 21 — 수동 재구독 mutation
  const resubMutation = useMutation({
    mutationFn: resubscribeStale,
    onSuccess: (res) => {
      setResubMsg(`${res.resubscribed}종목 재구독 완료`)
      queryClient.invalidateQueries({ queryKey: ['realtime-subscriptions'] })
      queryClient.invalidateQueries({ queryKey: ['trading-status'] })
    },
    onError: (err: Error) => {
      setResubMsg(`재구독 실패: ${err.message || '알 수 없는 오류'}`)
    },
  })

  const sessions: SubscriptionSession[] = data?.sessions ?? []
  const totalSlots = data?.limit ?? 0
  const totalUsed = data?.total ?? 0
  const usagePct = totalSlots > 0 ? Math.min(100, (totalUsed / totalSlots) * 100) : 0

  const hasSecondary = sessions.some((s) => s.label !== 'main')

  // 사이클 21 — 끊김 영역 노출 분기
  const staleCount = data?.stale_60s ?? 0
  const staleTickers = data?.tickers?.stale ?? []
  const lastTickMap = data?.last_tick_map ?? {}
  const kstMin = getKstMinutes()
  const staleCtx = getStaleContextByKstMinutes(kstMin)
  const staleCtxMeta = STALE_CONTEXT_META[staleCtx]

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
            메인 + 보조 시세 세션 상태. 매매·잔고·체결통보는 메인 단일 — 본 카드는 시세 분배 + 끊김 모니터링.
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
            <div className="mt-1 text-[11px] text-gray-500 flex gap-3 items-center flex-wrap">
              <span>
                정상(fresh):{' '}
                <span className="text-emerald-700 font-medium">{data?.fresh_60s ?? 0}</span>
              </span>
              <span>
                끊김(stale):{' '}
                <span className="text-amber-700 font-medium">{staleCount}</span>
              </span>
              <span>
                ACK:{' '}
                <span className="text-blue-700 font-medium">{data?.acked ?? 0}</span>
              </span>
              {/* 사이클 21 — 시간대 컨텍스트 라벨 + 수동 재구독 (stale > 0 시) */}
              {staleCount > 0 && staleCtxMeta.label && (
                <span
                  data-testid="stale-context-label"
                  className={`text-[11px] px-1.5 py-0.5 rounded ${staleCtxMeta.cls}`}
                >
                  {staleCtxMeta.label}
                </span>
              )}
              {staleCount > 0 && (
                <button
                  type="button"
                  data-testid="pool-resubscribe-button"
                  onClick={() => resubMutation.mutate()}
                  disabled={resubMutation.isPending}
                  className="text-[11px] px-2 py-0.5 rounded border border-amber-300 text-amber-800 hover:bg-amber-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  재구독
                </button>
              )}
            </div>
            {resubMsg && (
              <div className="mt-1 text-[11px] text-amber-700">{resubMsg}</div>
            )}
          </div>

          {/* 사이클 21 — 끊김 종목 펼치기 */}
          {staleCount > 0 && staleTickers.length > 0 && (
            <div className="mb-4">
              <button
                type="button"
                data-testid="pool-stale-list-toggle"
                onClick={() => setStaleListOpen((v) => !v)}
                className="text-xs text-amber-700 hover:underline"
              >
                {staleListOpen ? '끊김 종목 접기' : `끊김 종목 보기 (${staleTickers.length}개)`}
              </button>
              {staleListOpen && (
                <div className="mt-1 text-xs text-gray-600 max-h-32 overflow-y-auto border border-gray-100 rounded p-1">
                  {staleTickers.map((ticker: string) => (
                    <div
                      key={ticker}
                      data-testid={`pool-stale-row-${ticker}`}
                      className="flex justify-between py-0.5 border-b border-gray-50 last:border-0"
                    >
                      <span className="font-mono">{ticker}</span>
                      <span className="text-gray-500">
                        마지막: {formatLastTickKst(lastTickMap[ticker])}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 세션별 표 */}
          <ScrollPane>
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
          </ScrollPane>

          {/* 사이클 35 (2026-05-21) — 세션별 종목 expand */}
          <div className="mt-4">
            <div className="text-xs font-medium text-gray-600 mb-1">
              세션별 종목 상세
            </div>
            <div className="space-y-2">
              {sessions.map((s) => {
                const isOpen = expandedSession === s.label
                const detail: SubscriptionTickerDetail[] = s.tickers_detail ?? []
                if (detail.length === 0) {
                  return null
                }
                return (
                  <div key={s.label} className="border border-gray-200 rounded">
                    <button
                      type="button"
                      data-testid={`pool-session-expand-${s.label}`}
                      onClick={() =>
                        setExpandedSession((cur) => (cur === s.label ? null : s.label))
                      }
                      className="w-full px-2 py-1.5 flex justify-between items-center text-xs hover:bg-gray-50"
                    >
                      <span>
                        <span className="font-mono">{s.label}</span>
                        <span className="ml-2 text-gray-500">
                          {detail.length}종목 ({s.stale} 끊김)
                        </span>
                      </span>
                      <span className="text-gray-400">{isOpen ? '▲' : '▼'}</span>
                    </button>
                    {isOpen && (
                      <div
                        data-testid={`pool-session-tickers-${s.label}`}
                        className="border-t border-gray-100 max-h-64 overflow-y-auto"
                      >
                        <table className="min-w-full text-[11px]">
                          <thead className="bg-gray-50">
                            <tr className="text-gray-500 text-left">
                              <th className="py-1 px-2 font-medium">종목</th>
                              <th className="py-1 px-2 font-medium">이름</th>
                              <th className="py-1 px-2 font-medium">상태</th>
                              <th className="py-1 px-2 font-medium">WS tick</th>
                              {/* 사이클 37 (2026-05-21) — KIS 실제 체결시각 + 거래량 컬럼 */}
                              <th className="py-1 px-2 font-medium">KIS 체결</th>
                              <th className="py-1 px-2 font-medium">KIS 거래량</th>
                              <th className="py-1 px-2 font-medium">retries</th>
                              <th className="py-1 px-2 font-medium">강제 재구독</th>
                            </tr>
                          </thead>
                          <tbody>
                            {detail.map((row) => {
                              // 사이클 37 — WS 구독 의심 판정 (KIS 체결 - WS tick ≥ 5분)
                              const wsSuspect = isWsSubscriptionSuspect(
                                row.last_tick,
                                row.last_cntg_hour,
                              )
                              return (
                                <tr
                                  key={row.ticker}
                                  data-testid={`pool-ticker-row-${s.label}-${row.ticker}`}
                                  className={
                                    wsSuspect
                                      ? 'border-b border-gray-50 last:border-0 bg-amber-50'
                                      : 'border-b border-gray-50 last:border-0'
                                  }
                                >
                                  <td className="py-1 px-2 font-mono">{row.ticker}</td>
                                  <td className="py-1 px-2 text-gray-700">
                                    {row.ticker_name || '—'}
                                  </td>
                                  <td className="py-1 px-2">
                                    {row.stale ? (
                                      <span className="inline-block px-1 rounded text-[10px] bg-amber-100 text-amber-800 border border-amber-300">
                                        끊김
                                      </span>
                                    ) : (
                                      <span className="inline-block px-1 rounded text-[10px] bg-emerald-100 text-emerald-800 border border-emerald-300">
                                        정상
                                      </span>
                                    )}
                                    {wsSuspect && (
                                      <span
                                        data-testid={`pool-ws-suspect-${s.label}-${row.ticker}`}
                                        title="KIS 가 더 최근 체결을 보고하는데 우리 WS 가 못 받음 (5분+ 차이). WS 구독 문제 의심."
                                        className="ml-1 inline-block px-1 rounded text-[10px] bg-amber-200 text-amber-900 border border-amber-400"
                                      >
                                        WS 의심
                                      </span>
                                    )}
                                  </td>
                                  <td className="py-1 px-2 font-mono text-gray-600">
                                    {formatLastTickKst(row.last_tick)}
                                  </td>
                                  <td
                                    className={
                                      wsSuspect
                                        ? 'py-1 px-2 font-mono text-amber-800 font-semibold'
                                        : 'py-1 px-2 font-mono text-gray-700'
                                    }
                                  >
                                    {formatCntgHour(row.last_cntg_hour)}
                                  </td>
                                  <td className="py-1 px-2 font-mono text-gray-600">
                                    {row.today_volume != null
                                      ? row.today_volume.toLocaleString()
                                      : '—'}
                                  </td>
                                  <td className="py-1 px-2 font-mono text-gray-700">
                                    {row.retries > 0 ? row.retries : '—'}
                                  </td>
                                  <td className="py-1 px-2 font-mono text-gray-500">
                                    {formatLastTickKst(row.last_resub)}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {!hasSecondary && (
            <div
              className="mt-3 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded p-2"
              data-testid="pool-no-secondary-note"
            >
              보조 세션 없음 (메인 only). Settings &gt; 보조 KIS 시세 계좌에서 등록하면 다음 _boot(07:55) 부터 슬롯이 41 × (1 + N) 으로 확장됩니다.
            </div>
          )}
        </>
      )}
    </div>
  )
}
