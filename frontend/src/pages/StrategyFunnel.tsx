/**
 * 사이클 34 (2026-05-21) — 조건검색 단계별 추적 페이지.
 *
 * 사용자 5/21 15:26 funnel 결함 (donchian 111→0 / BFB 30→0 / VCP 113→0) 진단 시
 * 단계별 살아남은/탈락 종목을 알 수 없어 디버깅 곤란했던 문제 해소.
 *
 * 화면:
 * - 전략 선택 dropdown + target_date picker
 * - 단계별 expand 가능한 테이블 (survived_count + excluded_count + tickers expand)
 * - 단계 클릭 시 survived 종목 리스트 + excluded sample (탈락 사유 포함)
 * - "지금 snapshot 실행" 버튼 (수동 trigger)
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getFunnel,
  getRecentFunnel,
  triggerFunnelSnapshot,
  type FunnelSnapshot,
} from '../api/strategy-funnel'

const STRATEGY_OPTIONS = [
  { id: '', label: '전체' },
  { id: 'donchian_swing', label: '도치안 스윙' },
  { id: 'kojiro', label: '고지로 대순환' },
  { id: 'bull_flag_breakout', label: '눌림목 돌파' },
  { id: 'vcp_breakout', label: 'VCP 변동성 수축' },
  { id: 'momentum', label: '모멘텀' },
  { id: 'volatility_breakout', label: '변동성 돌파' },
  { id: 'long_tail_volatility', label: '롱테일 변동성' },
]

function todayKst(): string {
  // YYYY-MM-DD (KST)
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return fmt.format(new Date())
}

/**
 * team-leader 3d — 깔때기 병목 강조 + 최근 추이.
 *
 * VCP 실측 (코스피200+코스닥150 348 → EMA 정렬 7 → Pullback 0) 처럼
 * 단계별 통과 수가 어디서 급감하는지 화면이 진단해 주지 않던 문제 해소.
 */
export interface BottleneckInfo {
  stepNo: number
  stepName: string
  prevCount: number
  curCount: number
  dropRatePct: number
}

/**
 * 단계별 survived_count 중 직전 단계 대비 감소가 가장 큰 단계를 병목으로 판정.
 *
 * 랭킹 기준은 **절대 감소 수**(prevCount − curCount)다 — VCP 실측(329→7, 322건 감소, 97.9%)이
 * 이 병목이지만 그 뒤 7→0(7건 감소, 100%) 은 순수 %로는 더 높다. 이미 7개로 졸아든 마지막
 * 한 줌이 전멸하는 것보다 대규모 322건 컷이 일어나는 지점이 진단적으로 더 의미있는 병목이라
 * "감소율(%) 최대"가 아닌 "감소 수 최대"로 판정 — dropRatePct 는 표시용으로 함께 계산.
 * rows 는 step_no ASC 정렬을 가정 (백엔드 `list_snapshots` ORDER BY step_no — src/db/strategy_funnel.py).
 * 단계 1개 이하면 비교 대상이 없어 null.
 */
export function computeBottleneck(rows: FunnelSnapshot[]): BottleneckInfo | null {
  if (rows.length <= 1) return null
  let best: BottleneckInfo | null = null
  let bestDrop = -Infinity
  for (let i = 1; i < rows.length; i++) {
    const prev = rows[i - 1]
    const cur = rows[i]
    const drop = prev.survived_count - cur.survived_count
    const dropRatePct =
      prev.survived_count > 0 ? (drop / prev.survived_count) * 100 : 0
    if (drop > bestDrop) {
      bestDrop = drop
      best = {
        stepNo: cur.step_no,
        stepName: cur.step_name,
        prevCount: prev.survived_count,
        curCount: cur.survived_count,
        dropRatePct,
      }
    }
  }
  return best
}

export interface DailyFinalCount {
  date: string
  count: number
}

/**
 * getRecentFunnel 응답(여러 날짜×여러 단계 혼재)에서 날짜별 "최종 단계" 통과 수만 추출.
 * 최종 단계 = step_no===99 우선(수동 trigger/자동 09:30 캡처 공통 계약), 없으면 그 날짜의 최대 step_no.
 */
export function extractDailyFinalCounts(snapshots: FunnelSnapshot[]): DailyFinalCount[] {
  const byDate = new Map<string, FunnelSnapshot[]>()
  for (const snap of snapshots) {
    const list = byDate.get(snap.target_date)
    if (list) {
      list.push(snap)
    } else {
      byDate.set(snap.target_date, [snap])
    }
  }
  const result: DailyFinalCount[] = []
  for (const [date, rows] of byDate.entries()) {
    const finalRow =
      rows.find((r) => r.step_no === 99) ??
      rows.reduce((a, b) => (b.step_no > a.step_no ? b : a))
    result.push({ date, count: finalRow.survived_count })
  }
  result.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
  return result
}

/** daily 배열 끝(최근일)부터 역순으로 count===0 이 연속되는 길이. */
export function computeZeroStreak(daily: DailyFinalCount[]): number {
  let streak = 0
  for (let i = daily.length - 1; i >= 0; i--) {
    if (daily[i].count !== 0) break
    streak++
  }
  return streak
}

/** "YYYY-MM-DD" → "MM-DD". 날짜 전용 문자열이라 Date() 파싱/타임존 변환 불필요(KST 강제 컨벤션 무관). */
function formatDateShort(dateStr: string): string {
  return dateStr.length >= 10 ? dateStr.slice(5, 10) : dateStr
}

export default function StrategyFunnel() {
  const queryClient = useQueryClient()
  const [strategyId, setStrategyId] = useState<string>('')
  const [targetDate, setTargetDate] = useState<string>(todayKst())
  const [expandedStep, setExpandedStep] = useState<string | null>(null)
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['strategy-funnel', targetDate, strategyId],
    queryFn: () =>
      getFunnel({
        target_date: targetDate,
        strategy_id: strategyId || undefined,
      }),
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  })

  const triggerMutation = useMutation({
    mutationFn: triggerFunnelSnapshot,
    onSuccess: (res) => {
      setTriggerMsg(`${res.count}개 전략 snapshot 저장 완료`)
      queryClient.invalidateQueries({ queryKey: ['strategy-funnel'] })
    },
    onError: (err: Error) => {
      setTriggerMsg(`snapshot 실패: ${err.message || '알 수 없는 오류'}`)
    },
  })

  // team-leader 3d — 최근 14영업일 추이 (특정 전략 선택 시만, '전체'는 단일 strategy_id 가
  // 없어 API 호출 대상이 불명확 → 미조회).
  const {
    data: recentData,
    isLoading: recentLoading,
    isError: recentError,
  } = useQuery({
    queryKey: ['strategy-funnel-recent', strategyId],
    queryFn: () => getRecentFunnel(strategyId, 14),
    enabled: strategyId !== '',
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  })
  const dailyCounts = extractDailyFinalCounts(recentData?.snapshots ?? [])
  const zeroStreak = computeZeroStreak(dailyCounts)
  const trendMax = Math.max(1, ...dailyCounts.map((d) => d.count))

  const snapshots: FunnelSnapshot[] = data?.snapshots ?? []

  // 전략별 그룹화 (전체 조회 시)
  const groupedByStrategy = snapshots.reduce<Record<string, FunnelSnapshot[]>>(
    (acc, snap) => {
      const key = snap.strategy_id
      if (!acc[key]) acc[key] = []
      acc[key].push(snap)
      return acc
    },
    {},
  )

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-xl font-semibold text-gray-800 mb-3">
        조건검색 단계별 추적
      </h1>
      <div className="text-xs text-gray-500 mb-4">
        전략별 prepare 단계에서 어떤 종목이 살아남고 어떤 종목이 탈락했는지 영구 추적합니다.
      </div>

      {/* 필터 바 */}
      <div className="flex gap-3 items-end mb-4 bg-white border border-gray-200 rounded p-3">
        <div>
          <label className="block text-xs text-gray-600 mb-1">전략</label>
          <select
            data-testid="funnel-strategy-select"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          >
            {STRATEGY_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-600 mb-1">영업일</label>
          <input
            data-testid="funnel-date-input"
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          />
        </div>
        <div className="ml-auto flex flex-col items-end gap-1">
          <button
            type="button"
            data-testid="funnel-trigger-button"
            onClick={() => triggerMutation.mutate()}
            disabled={triggerMutation.isPending}
            className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded disabled:opacity-50"
          >
            {triggerMutation.isPending ? '실행 중...' : '지금 snapshot 실행'}
          </button>
          {triggerMsg && (
            <div className="text-[11px] text-amber-700">{triggerMsg}</div>
          )}
        </div>
      </div>

      {/* 사이클 132 (2026-06-15) — 휴장일 안내 amber 배너 (Q3=A 사용자 결정 영속) */}
      {data && data.is_business_day === false && (
        <div
          data-testid="strategy-funnel-holiday-banner"
          className="mb-4 px-3 py-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-800"
        >
          <strong>휴장일 안내</strong>
          {data.holiday_note && (
            <span
              data-testid="strategy-funnel-holiday-note"
              className="ml-2 text-amber-700"
            >
              {data.holiday_note}
            </span>
          )}
        </div>
      )}

      {/* 사이클 132 — momentum 정책 안내 영속 / 사이클 143 — VB/LTV 영역 영구 영속 정상 funnel 활성화 후 안내 메시지 영구 제거 */}
      <div
        data-testid="strategy-funnel-policy-notice"
        className="mb-4 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs text-gray-600"
      >
        <div data-testid="strategy-funnel-notice-momentum">
          • <strong>모멘텀</strong>: 실시간 돌파 기반 — funnel 적재 미적용
        </div>
      </div>

      {/* 상태 */}
      {isLoading && (
        <div className="text-sm text-gray-500" data-testid="funnel-loading">
          불러오는 중...
        </div>
      )}
      {isError && (
        <div className="text-sm text-red-600" data-testid="funnel-error">
          조회 실패. 잠시 후 다시 시도하세요.
        </div>
      )}
      {!isLoading && !isError && snapshots.length === 0 && (
        <div
          className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded p-3"
          data-testid="funnel-empty"
        >
          이 영업일에 기록된 snapshot 이 없습니다. 09:30 자동 또는 "지금 snapshot 실행" 으로 생성하세요.
        </div>
      )}

      {/* team-leader 3d — 최근 14영업일 추이 (특정 전략 선택 시만) */}
      {strategyId !== '' && (
        <div
          data-testid="funnel-recent-trend"
          className="mb-4 bg-white border border-gray-200 rounded p-3"
        >
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-700">
              최근 14영업일 추이 (최종 후보)
            </h3>
            {zeroStreak >= 2 && (
              <span
                data-testid="funnel-recent-trend-zero-streak-badge"
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  zeroStreak === dailyCounts.length
                    ? 'bg-red-100 text-red-800'
                    : 'bg-amber-100 text-amber-800'
                }`}
              >
                {zeroStreak}일 연속 후보 0
              </span>
            )}
          </div>
          {recentLoading && (
            <div className="text-xs text-gray-500">불러오는 중...</div>
          )}
          {recentError && (
            <div className="text-xs text-red-600">최근 추이 조회 실패. 잠시 후 다시 시도하세요.</div>
          )}
          {!recentLoading && !recentError && dailyCounts.length === 0 && (
            <div className="text-xs text-gray-500">최근 데이터가 없습니다.</div>
          )}
          {!recentLoading && !recentError && dailyCounts.length > 0 && (
            <div className="flex items-end gap-1 h-16">
              {dailyCounts.map((d) => {
                const barHeightPct = Math.round((d.count / trendMax) * 100)
                return (
                  <div
                    key={d.date}
                    data-testid={`funnel-recent-trend-bar-${d.date}`}
                    className="flex-1 flex flex-col items-center justify-end gap-0.5"
                    title={`${d.date}: ${d.count}건`}
                  >
                    <span className="text-[10px] text-gray-500 tabular-nums">{d.count}</span>
                    <div
                      className={`w-full rounded-t ${d.count === 0 ? 'bg-rose-300' : 'bg-blue-300'}`}
                      style={{ height: `${Math.max(2, barHeightPct)}%` }}
                    />
                    <span className="text-[9px] text-gray-400">{formatDateShort(d.date)}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* 단계별 테이블 */}
      {Object.entries(groupedByStrategy).map(([sid, rows]) => {
        // 병목 강조 (2026-08-06) — 직전 단계 대비 **절대 감소 수**가 가장 큰 단계.
        // 감소'율'로 잡으면 막판 7→0(100%)이 329→7(97.9%)을 이겨 진짜 병목을 가린다.
        // 진단 대상은 "어디서 물량이 통째로 빠지는가" 이므로 절대 수가 맞다.
        // rows 는 DB `ORDER BY step_no` 보장(src/db/strategy_funnel.py) — 순서 의존 안전.
        const bottleneck = computeBottleneck(rows)
        const finalCount = rows.length > 0 ? rows[rows.length - 1].survived_count : 0
        const maxSurvived = Math.max(1, ...rows.map((r) => r.survived_count))
        return (
        <div
          key={sid}
          data-testid={`funnel-strategy-block-${sid}`}
          className="mb-6 bg-white border border-gray-200 rounded"
        >
          <div className="px-3 py-2 border-b border-gray-200 bg-gray-50">
            <span className="font-medium text-gray-800">{sid}</span>
            <span className="ml-2 text-xs text-gray-500">{rows.length} 단계</span>
          </div>
          {bottleneck && (
            <div
              data-testid="funnel-bottleneck-banner"
              className={`mx-3 mt-2 px-3 py-2 rounded text-xs font-medium border ${
                finalCount === 0
                  ? 'bg-red-100 border-red-300 text-red-800'
                  : 'bg-amber-50 border-amber-200 text-amber-800'
              }`}
            >
              ⛔ 병목: {bottleneck.stepNo}단계 &quot;{bottleneck.stepName}&quot; —{' '}
              <span className="tabular-nums">{bottleneck.prevCount}</span> →{' '}
              <span className="tabular-nums">{bottleneck.curCount}</span> (
              <span className="tabular-nums">{bottleneck.dropRatePct.toFixed(1)}</span>% 탈락)
            </div>
          )}
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-left text-xs border-b border-gray-200">
                <th className="py-2 px-3 font-medium w-12">#</th>
                <th className="py-2 px-3 font-medium">단계</th>
                <th className="py-2 px-3 font-medium text-right">통과</th>
                <th className="py-2 px-3 font-medium text-right">탈락</th>
                <th className="py-2 px-3 font-medium w-20">상세</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const expandKey = `${sid}-${row.step_no}-${row.id}`
                const isOpen = expandedStep === expandKey
                return (
                  <>
                    <tr
                      key={row.id}
                      data-testid={`funnel-row-${sid}-${row.step_no}`}
                      className={`border-b border-gray-100 ${
                        bottleneck?.stepNo === row.step_no
                          ? finalCount === 0
                            ? 'bg-red-50'
                            : 'bg-amber-50'
                          : ''
                      }`}
                    >
                      <td className="py-2 px-3 font-mono text-gray-500">
                        {row.step_no}
                      </td>
                      <td className="py-2 px-3 text-gray-800">
                        {row.step_name}
                        {/* 사이클 41 — step_conditions 툴팁 (UI 표시 + title hover) */}
                        {row.step_conditions && (
                          <span
                            data-testid={`funnel-step-conditions-${sid}-${row.step_no}`}
                            title={row.step_conditions}
                            className="ml-2 inline-block text-[10px] text-blue-600 cursor-help underline decoration-dotted"
                          >
                            조건
                          </span>
                        )}
                        {/* 사이클 171 — 잠정(provisional) 배지 (16:20 저녁 캡처, 아침 델타 미반영) */}
                        {row.is_provisional && (
                          <span
                            data-testid={`funnel-provisional-badge-${sid}-${row.step_no}`}
                            title="16:20 저녁 잠정 캡처 — 익일 아침 마스터 델타 반영 전 (후보가 바뀔 수 있음)"
                            className="ml-2 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800"
                          >
                            잠정
                          </span>
                        )}
                        {/* team-leader 3d — 단계별 통과 수 비례 막대 (병목 단계는 톤 강조) */}
                        <div
                          data-testid={`funnel-bar-${sid}-${row.step_no}`}
                          className="h-1 bg-gray-100 rounded-full overflow-hidden mt-1 w-32"
                        >
                          <div
                            className={`h-full transition-all ${
                              bottleneck?.stepNo === row.step_no
                                ? finalCount === 0
                                  ? 'bg-red-400'
                                  : 'bg-amber-400'
                                : 'bg-blue-300'
                            }`}
                            style={{
                              width: `${Math.round((row.survived_count / maxSurvived) * 100)}%`,
                            }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-emerald-700 tabular-nums">
                        {row.survived_count}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-amber-700 tabular-nums">
                        {row.excluded_count}
                      </td>
                      <td className="py-2 px-3">
                        <button
                          type="button"
                          data-testid={`funnel-expand-${sid}-${row.step_no}`}
                          onClick={() =>
                            setExpandedStep((cur) =>
                              cur === expandKey ? null : expandKey,
                            )
                          }
                          className="text-xs text-blue-600 hover:underline"
                        >
                          {isOpen ? '접기' : '보기'}
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr key={`${row.id}-expand`}>
                        <td colSpan={5} className="py-2 px-3 bg-gray-50">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {/* 통과 종목 — 사이클 41: dict 형식 (ticker + name) 또는 string 호환 */}
                            <div>
                              <div className="text-xs font-medium text-gray-600 mb-1">
                                통과 ({(row.survived_tickers ?? []).length}건)
                              </div>
                              <div className="text-[11px] text-gray-700 max-h-32 overflow-y-auto bg-white border border-gray-100 rounded p-1">
                                {(row.survived_tickers ?? []).length === 0 ? (
                                  <span className="text-gray-400">—</span>
                                ) : (
                                  (row.survived_tickers ?? []).map((item, idx) => {
                                    // 사이클 41 — dict | string 둘 다 호환
                                    const ticker = typeof item === 'string' ? item : item.ticker
                                    const name = typeof item === 'string' ? '' : (item.name ?? '')
                                    return (
                                      <span
                                        key={`${ticker}-${idx}`}
                                        data-testid={`funnel-survived-${sid}-${row.step_no}-${ticker}`}
                                        className="inline-block mr-2 mb-1 px-1.5 py-0.5 bg-emerald-50 text-emerald-800 rounded border border-emerald-200"
                                      >
                                        <span className="font-mono">{ticker}</span>
                                        {name && (
                                          <span className="ml-1 text-emerald-700">
                                            {name}
                                          </span>
                                        )}
                                      </span>
                                    )
                                  })
                                )}
                              </div>
                            </div>
                            {/* 탈락 sample — 사이클 41: 종목명 + 수치 포함 사유 */}
                            <div>
                              <div className="text-xs font-medium text-gray-600 mb-1">
                                탈락 sample ({(row.excluded_sample ?? []).length}건)
                              </div>
                              <div className="text-[11px] text-gray-700 max-h-32 overflow-y-auto bg-white border border-gray-100 rounded p-1">
                                {(row.excluded_sample ?? []).length === 0 ? (
                                  <span className="text-gray-400">—</span>
                                ) : (
                                  (row.excluded_sample ?? []).map((ex, idx) => (
                                    <div
                                      key={`${ex.ticker}-${idx}`}
                                      data-testid={`funnel-excluded-${sid}-${row.step_no}-${ex.ticker}`}
                                      className="flex justify-between border-b border-gray-50 last:border-0 py-0.5 gap-2"
                                    >
                                      <span className="flex-shrink-0">
                                        <span className="font-mono">{ex.ticker}</span>
                                        {ex.name && (
                                          <span className="ml-1 text-gray-700">
                                            {ex.name}
                                          </span>
                                        )}
                                      </span>
                                      <span className="text-amber-700 text-right">
                                        {ex.reason}
                                      </span>
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
        )
      })}
    </div>
  )
}
