import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchRefreshProgress } from '../api/stock-master'
import type {
  AllRefreshProgress,
  RefreshProgress,
  RefreshTaskKey,
} from '../types/stock-master'

const TASK_LABELS: Record<RefreshTaskKey, string> = {
  universe: '종목마스터 새로고침',
  basics: '기본정보 새로고침 (NXT/거래정지/관리종목)',
  daily: '일봉 새로고침 (30일)',
  master: '종목마스터 일일 갱신 (KIS 마스터 파일)',  // 사이클 129
}

const TASK_ORDER: RefreshTaskKey[] = ['universe', 'basics', 'daily', 'master']  // 사이클 129 — master 4 확장

function formatElapsed(ms: number): string {
  if (ms <= 0) return '0초'
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}시간 ${m}분 ${s}초`
  if (m > 0) return `${m}분 ${s}초`
  return `${s}초`
}

function formatKstTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(iso))
  } catch {
    return '—'
  }
}

function pct(processed: number, total: number): number {
  if (total <= 0) return 0
  return Math.min(100, Math.round((processed / total) * 100))
}

interface TaskRowProps {
  taskKey: RefreshTaskKey
  progress: RefreshProgress
}

function TaskRow({ taskKey, progress }: TaskRowProps) {
  const percent = pct(progress.processed, progress.total)
  const isRunning = progress.status === 'running'
  const isFailed = progress.status === 'failed'
  const barColor = isFailed
    ? 'bg-red-500'
    : progress.status === 'completed'
      ? 'bg-emerald-500'
      : 'bg-blue-500'
  const barWidth = isRunning && progress.total > 0 ? `${percent}%` : isFailed ? '100%' : `${percent}%`

  return (
    <div
      data-testid={`refresh-progress-row-${taskKey}`}
      className="border-b border-gray-200 last:border-b-0 py-3"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="font-medium text-sm text-gray-800">
          {TASK_LABELS[taskKey]}
        </span>
        <span
          data-testid={`refresh-progress-status-${taskKey}`}
          className={
            isRunning
              ? 'text-blue-600 text-xs font-semibold'
              : progress.status === 'completed'
                ? 'text-emerald-600 text-xs font-semibold'
                : isFailed
                  ? 'text-red-600 text-xs font-semibold'
                  : 'text-gray-400 text-xs'
          }
        >
          {isRunning
            ? `진행 중 ${percent}%`
            : progress.status === 'completed'
              ? '완료'
              : isFailed
                ? '실패'
                : '대기'}
        </span>
      </div>

      <div
        className="w-full bg-gray-200 rounded-full h-2 overflow-hidden mb-2"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${TASK_LABELS[taskKey]} 진행률`}
      >
        <div
          data-testid={`refresh-progress-bar-${taskKey}`}
          className={`h-full transition-all duration-500 ${barColor}`}
          style={{ width: barWidth }}
        />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
        <span data-testid={`refresh-progress-counter-${taskKey}`}>
          처리 {progress.processed.toLocaleString('ko-KR')} / {progress.total.toLocaleString('ko-KR')}
        </span>
        <span>
          성공 <span className="text-emerald-600">{progress.updated.toLocaleString('ko-KR')}</span>
        </span>
        <span>
          스킵 <span className="text-gray-500">{progress.skipped.toLocaleString('ko-KR')}</span>
        </span>
        <span>
          실패 <span className="text-red-600">{progress.failed.toLocaleString('ko-KR')}</span>
        </span>
        <span>경과 {formatElapsed(progress.elapsed_ms)}</span>
        {progress.started_at && (
          <span>시작 {formatKstTime(progress.started_at)}</span>
        )}
        {progress.finished_at && (
          <span>종료 {formatKstTime(progress.finished_at)}</span>
        )}
      </div>

      {isFailed && progress.error_message && (
        <div
          data-testid={`refresh-progress-error-${taskKey}`}
          className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2"
        >
          {progress.error_message}
        </div>
      )}
    </div>
  )
}

interface RefreshProgressBannerProps {
  // 테스트 주입용 — 미지정 시 useQuery 폴링
  initialData?: AllRefreshProgress
}

/**
 * 사이클 127 — 3 작업 (universe/basics/daily) 진행 상단 배너.
 *
 * 영속 의무:
 * - useQuery retry:1 (사이클 65 H3 / 75 G-AST-RT 영속)
 * - KST 강제 (사이클 68) — Intl.DateTimeFormat timeZone='Asia/Seoul'
 * - 한글 친숙 용어 (사이클 89 영속)
 * - running 시 5초 폴링, idle/completed/failed 시 60초 (트래픽 절감)
 * - 완료 또는 실패 후 3초 후 자동 숨김 + invalidateQueries (stats/list)
 */
export function RefreshProgressBanner({ initialData }: RefreshProgressBannerProps = {}) {
  const queryClient = useQueryClient()
  const [hiddenAfterFinish, setHiddenAfterFinish] = useState<Set<RefreshTaskKey>>(new Set())

  const { data } = useQuery({
    queryKey: ['refresh-progress'],
    queryFn: fetchRefreshProgress,
    retry: 1,
    refetchInterval: (query) => {
      const d = query.state.data as AllRefreshProgress | undefined
      if (!d) return 5_000
      const anyRunning = TASK_ORDER.some((k) => d[k]?.status === 'running')
      return anyRunning ? 5_000 : 60_000
    },
    initialData,
  })

  const progress = data

  // 완료/실패 후 3초 후 자동 숨김 + invalidate
  useEffect(() => {
    if (!progress) return
    const timers: ReturnType<typeof setTimeout>[] = []
    TASK_ORDER.forEach((key) => {
      const p = progress[key]
      if ((p.status === 'completed' || p.status === 'failed') && !hiddenAfterFinish.has(key)) {
        timers.push(
          setTimeout(() => {
            setHiddenAfterFinish((prev) => new Set(prev).add(key))
            queryClient.invalidateQueries({ queryKey: ['stock-master-stats'] })
            queryClient.invalidateQueries({ queryKey: ['stock-master-list'] })
          }, 3_000),
        )
      }
      // running으로 돌아오면 hidden 해제
      if (p.status === 'running' && hiddenAfterFinish.has(key)) {
        setHiddenAfterFinish((prev) => {
          const next = new Set(prev)
          next.delete(key)
          return next
        })
      }
    })
    return () => {
      timers.forEach((t) => clearTimeout(t))
    }
  }, [progress, hiddenAfterFinish, queryClient])

  if (!progress) return null

  // 표시 대상: running 또는 (completed/failed 이고 hidden 안 됨)
  const visibleTasks = TASK_ORDER.filter((key) => {
    const p = progress[key]
    if (p.status === 'idle') return false
    if ((p.status === 'completed' || p.status === 'failed') && hiddenAfterFinish.has(key))
      return false
    return true
  })

  if (visibleTasks.length === 0) return null

  return (
    <div
      data-testid="refresh-progress-banner"
      className="bg-white border border-blue-200 rounded-lg shadow-sm p-3 mb-4"
      role="status"
      aria-live="polite"
    >
      <div className="text-sm font-semibold text-blue-700 mb-2">
        종목마스터 갱신 작업 진행
      </div>
      {visibleTasks.map((key) => (
        <TaskRow key={key} taskKey={key} progress={progress[key]} />
      ))}
    </div>
  )
}

export default RefreshProgressBanner
