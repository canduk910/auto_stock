/**
 * 대시보드 경고등 (cycle434).
 *
 * 사용자 지시(2026-10-10) "잔고/권리 불일치 등 일일작업 작업오류 발생 시
 * 대시보드에 경고등 추가". `NavBar.tsx` 에 박아 어느 화면에서든 보인다.
 *
 * 상태 4종(색 + 글자, 색맹 고려):
 * - red    "위험"  — 장부 불일치 · 주문 결과 모름/청산 실패
 * - yellow "주의"  — 일일 작업 실패
 * - green  "정상"  — 오늘 해당 없음
 * - unknown "모름" — DB 조회 실패(조회 자체가 실패) 또는 네트워크 오류
 *
 * 60초 폴링(`refetchIntervalInBackground: false` — 탭이 백그라운드일 때는
 * 쉰다). 누르면 범주별 목록이 열리고 로그 화면(`/logs`)으로 가는 링크가 있다.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getSystemAlerts } from '../api/system-alerts'
import type { AlertSignalStatus } from '../types/system-alerts'
import { formatKstDateTime } from '../utils/kst'

const STATUS_META: Record<
  AlertSignalStatus | 'loading' | 'error',
  { label: string; dotClass: string; textClass: string }
> = {
  red: { label: '위험', dotClass: 'bg-red-600', textClass: 'text-red-700' },
  yellow: { label: '주의', dotClass: 'bg-beige-600', textClass: 'text-beige-800' },
  green: { label: '정상', dotClass: 'bg-sky-600', textClass: 'text-sky-800' },
  unknown: { label: '모름', dotClass: 'bg-gray-400', textClass: 'text-gray-600' },
  loading: { label: '확인 중', dotClass: 'bg-gray-300', textClass: 'text-gray-500' },
  error: { label: '조회 실패', dotClass: 'bg-gray-400', textClass: 'text-gray-600' },
}

export default function AlertLight() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['system-alerts'],
    queryFn: getSystemAlerts,
    retry: 1,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  const metaKey: AlertSignalStatus | 'loading' | 'error' = isLoading
    ? 'loading'
    : isError
      ? 'error'
      : (data?.status ?? 'unknown')
  const meta = STATUS_META[metaKey]

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        ref={triggerRef}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="true"
        data-testid="alert-light"
        data-status={metaKey}
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1.5 rounded-md hover:bg-gray-100"
        title={`경고등 — ${meta.label}`}
      >
        <span
          data-testid="alert-light-dot"
          aria-hidden="true"
          className={`inline-block h-2.5 w-2.5 rounded-full ${meta.dotClass}`}
        />
        <span data-testid="alert-light-label" className={meta.textClass}>
          {meta.label}
        </span>
      </button>

      {open && (
        <div
          data-testid="alert-light-panel"
          role="dialog"
          className="absolute right-0 top-full mt-1 w-80 max-w-[90vw] bg-white border border-gray-200 rounded-md shadow-lg p-3 z-20"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-gray-900">오늘 경고</span>
            {data?.as_of && (
              <span className="text-xs text-gray-400">{formatKstDateTime(data.as_of)}</span>
            )}
          </div>

          {isError && (
            <p className="text-xs text-gray-500" data-testid="alert-light-error">
              경고 집계를 불러오지 못했습니다.
            </p>
          )}

          {!isError && !data && !isLoading && (
            <p className="text-xs text-gray-500" data-testid="alert-light-empty">
              데이터가 없습니다.
            </p>
          )}

          {data && (
            <ul className="space-y-2">
              {data.categories.map((cat) => {
                const known = cat.count !== null
                const hasIssue = known && (cat.count as number) > 0
                return (
                  <li
                    key={cat.key}
                    data-testid={`alert-light-category-${cat.key}`}
                    className="border border-gray-100 rounded-md p-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-800">{cat.label}</span>
                      <span
                        className={`text-xs font-semibold ${
                          !known
                            ? 'text-gray-500'
                            : hasIssue
                              ? cat.color === 'red'
                                ? 'text-red-700'
                                : 'text-beige-800'
                              : 'text-gray-500'
                        }`}
                      >
                        {!known ? '모름' : `${cat.count}건`}
                      </span>
                    </div>
                    {hasIssue && (
                      <div className="mt-1 text-[11px] text-gray-500 space-y-0.5">
                        <div>
                          최고 {cat.max_level ?? '—'} · 첫 {formatKstDateTime(cat.first_at)} · 마지막{' '}
                          {formatKstDateTime(cat.last_at)}
                        </div>
                        {cat.recent_messages.slice(0, 3).map((m, idx) => (
                          <div key={idx} className="truncate" title={m.message}>
                            {m.message}
                          </div>
                        ))}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}

          <Link
            to="/logs?tab=system"
            data-testid="alert-light-logs-link"
            onClick={() => setOpen(false)}
            className="mt-3 inline-block text-xs font-medium text-navy-700 hover:underline"
          >
            로그 화면으로 이동 →
          </Link>
        </div>
      )}
    </div>
  )
}
