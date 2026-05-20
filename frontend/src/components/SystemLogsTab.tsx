import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchLogs, searchLogs, type LogEntry } from '../api/logs'

/**
 * SystemLogsTab — 사이클 6 (2026-05-17).
 *
 * /logs?tab=system 탭 본문. LogViewer 의 로직을 확장:
 *  - from_date / to_date 분리 date input (기본 둘 다 오늘 KST)
 *  - level 필터 (전체/INFO/WARNING/ERROR/CRITICAL)
 *  - 페이징 (1-base, size 기본 50)
 *  - 자동 새로고침 3s — 오늘 + page 1 + level 변경 없을 때만 활성
 *  - 시각 표시는 Asia/Seoul 강제 (CLAUDE.md L3 컨벤션)
 *
 * 사이클 6 통합 (2026-05-20) — 키워드 검색 박스 추가.
 *  - 검색어 입력 + 검색 버튼 → /api/logs/search (ILIKE substring 매칭)
 *  - 검색 모드 동안 페이징/자동 새로고침 비활성
 *  - 초기화 버튼 → 검색 모드 종료, 기존 페이징 모드 복귀
 *  - has_more=true 시 "키워드를 좁혀주세요" 안내
 */

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: 'text-gray-400',
  INFO: 'text-green-600',
  WARNING: 'text-yellow-600',
  ERROR: 'text-red-500 font-medium',
  CRITICAL: 'text-red-700 font-bold',
}

const LEVELS: Array<{ value: string | null; label: string }> = [
  { value: null, label: '전체' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'CRITICAL', label: 'CRITICAL' },
]

const DEFAULT_SIZE = 50
const SEARCH_LIMIT = 200

/**
 * KST 오늘 날짜 (YYYY-MM-DD).
 * `new Date().toISOString()` 은 UTC 기준이라 09시 이전이면 어제로 빗나간다 → Intl.DateTimeFormat 사용.
 */
function todayKST(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
  return parts // en-CA → YYYY-MM-DD
}

function formatKST(iso: string): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour12: false,
    })
  } catch {
    return iso
  }
}

/**
 * 사용자 입력 from_date(YYYY-MM-DD) → ISO 8601 (`T00:00:00+09:00`).
 * 검색 API 가 `gte/lte` 비교용 ISO 를 받으므로 KST suffix 강제.
 */
function dateToIsoStart(d: string): string {
  return `${d}T00:00:00+09:00`
}

function dateToIsoEnd(d: string): string {
  return `${d}T23:59:59.999+09:00`
}

export default function SystemLogsTab() {
  const today = useMemo(() => todayKST(), [])
  const [fromDate, setFromDate] = useState(today)
  const [toDate, setToDate] = useState(today)
  const [level, setLevel] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [size] = useState(DEFAULT_SIZE)
  const [dateError, setDateError] = useState<string | null>(null)

  // 사이클 6 통합 — 검색 모드
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState<string | null>(null)
  const searchMode = searchQuery !== null && searchQuery !== ''

  // 자동 새로고침: 오늘만 검색하고 page=1, 검색 모드 아닐 때만 활성.
  const autoRefresh = !searchMode && fromDate === today && toDate === today && page === 1

  // 페이징 모드 — 기존 fetchLogs
  const {
    data: pagedData,
    isLoading: pagedLoading,
    isError: pagedError,
  } = useQuery({
    queryKey: ['systemLogs', fromDate, toDate, level, page, size],
    queryFn: () =>
      fetchLogs({
        from_date: fromDate,
        to_date: toDate,
        level,
        page,
        size,
      }),
    refetchInterval: autoRefresh ? 3000 : false,
    enabled: !dateError && !searchMode,
  })

  // 검색 모드 — searchLogs
  const {
    data: searchData,
    isLoading: searchLoading,
    isError: searchError,
  } = useQuery({
    queryKey: ['systemLogsSearch', searchQuery, fromDate, toDate, level],
    queryFn: () =>
      searchLogs({
        q: searchQuery!,
        level,
        start: fromDate ? dateToIsoStart(fromDate) : null,
        end: toDate ? dateToIsoEnd(toDate) : null,
        limit: SEARCH_LIMIT,
      }),
    enabled: searchMode,
  })

  const items: LogEntry[] = searchMode
    ? (searchData?.logs ?? [])
    : (pagedData?.items ?? [])
  const total = searchMode ? (searchData?.total ?? 0) : (pagedData?.total ?? 0)
  const totalPages = pagedData?.total_pages ?? 0
  const hasMore = searchData?.has_more ?? false
  const isLoading = searchMode ? searchLoading : pagedLoading
  const isError = searchMode ? searchError : pagedError

  const handleApply = () => {
    if (fromDate > toDate) {
      setDateError('시작일이 종료일보다 늦을 수 없습니다.')
      return
    }
    setDateError(null)
    setPage(1)
  }

  const handleLevelChange = (next: string | null) => {
    setLevel(next)
    setPage(1)
  }

  const handleSearch = () => {
    const q = searchInput.trim()
    if (!q) return
    setSearchQuery(q)
  }

  const handleClearSearch = () => {
    setSearchInput('')
    setSearchQuery(null)
  }

  const canPrev = page > 1
  const canNext = totalPages > 0 && page < totalPages

  return (
    <div className="bg-white rounded-lg shadow">
      {/* 검색 박스 (사이클 6 통합) */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-gray-200">
        <label className="text-xs text-gray-500">검색</label>
        <input
          type="text"
          data-testid="system-logs-search-input"
          placeholder="키워드 검색 (메시지 ILIKE)"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSearch()
          }}
          className="flex-1 min-w-[16rem] text-sm border border-gray-300 rounded px-2 py-1"
        />
        <button
          type="button"
          onClick={handleSearch}
          disabled={!searchInput.trim()}
          data-testid="system-logs-search-button"
          className="px-3 py-1 text-xs font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          검색
        </button>
        {searchMode && (
          <button
            type="button"
            onClick={handleClearSearch}
            data-testid="system-logs-search-clear"
            className="px-3 py-1 text-xs font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200"
          >
            초기화
          </button>
        )}
        {searchMode && (
          <span className="text-xs text-indigo-700 ml-1">
            검색 모드 · &quot;{searchQuery}&quot;
          </span>
        )}
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">시작일</label>
          <input
            type="date"
            data-testid="system-logs-from-date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">종료일</label>
          <input
            type="date"
            data-testid="system-logs-to-date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          />
        </div>
        <button
          type="button"
          onClick={handleApply}
          data-testid="system-logs-apply"
          className="px-3 py-1 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700"
        >
          적용
        </button>

        <div className="flex items-center gap-1 ml-auto">
          {LEVELS.map((lvl) => (
            <button
              key={lvl.value ?? 'ALL'}
              type="button"
              onClick={() => handleLevelChange(lvl.value)}
              data-testid={`system-logs-level-${lvl.value ?? 'all'}`}
              className={`px-2 py-0.5 text-xs rounded ${
                level === lvl.value
                  ? 'bg-gray-800 text-white'
                  : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              {lvl.label}
            </button>
          ))}
        </div>
      </div>

      {dateError && (
        <div
          data-testid="system-logs-date-error"
          className="px-4 py-2 text-xs text-red-700 bg-red-50 border-b border-red-100"
        >
          {dateError}
        </div>
      )}

      {/* has_more 안내 (검색 모드 한정) */}
      {searchMode && hasMore && (
        <div
          data-testid="system-logs-search-has-more"
          className="px-4 py-2 text-xs text-amber-800 bg-amber-50 border-b border-amber-100"
        >
          검색 결과가 {SEARCH_LIMIT}건을 초과합니다. 키워드를 좁혀주세요. (총 {total.toLocaleString()}건 중 상위 {SEARCH_LIMIT}건)
        </div>
      )}

      {/* 본문 — 검정 배경 콘솔 톤 */}
      <div
        data-testid="system-logs-body"
        className="bg-gray-900 font-mono text-xs p-3 max-h-[60vh] min-h-[20rem] overflow-y-auto space-y-0.5"
      >
        {isLoading ? (
          <p className="text-gray-500">{searchMode ? '검색 중...' : '로딩 중...'}</p>
        ) : isError ? (
          <p className="text-red-400">로그를 불러올 수 없습니다.</p>
        ) : items.length === 0 ? (
          <p className="text-gray-500">
            {searchMode ? '검색 결과가 없습니다.' : '로그가 없습니다.'}
          </p>
        ) : (
          items.map((log) => (
            <div key={log.id} className="flex gap-2 leading-5">
              <span className="text-gray-500 shrink-0">{formatKST(log.timestamp)}</span>
              <span
                className={`shrink-0 w-16 ${LEVEL_STYLE[log.log_level] ?? 'text-gray-300'}`}
              >
                {log.log_level}
              </span>
              <span className="text-gray-300 break-all">{log.message}</span>
            </div>
          ))
        )}
      </div>

      {/* 페이징 + 메타 (검색 모드는 페이징 비활성) */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-gray-200 text-xs text-gray-600">
        <span data-testid="system-logs-meta">
          총 <span className="font-medium">{total.toLocaleString()}</span>건
          {autoRefresh && <span className="ml-2 text-green-600">· 자동 새로고침</span>}
          {searchMode && <span className="ml-2 text-indigo-600">· 검색 모드</span>}
        </span>
        {!searchMode && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => canPrev && setPage((p) => p - 1)}
              disabled={!canPrev}
              data-testid="system-logs-prev"
              className="px-2 py-1 rounded border border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              이전
            </button>
            <span data-testid="system-logs-page">
              {totalPages === 0 ? '0 / 0' : `${page} / ${totalPages}`}
            </span>
            <button
              type="button"
              onClick={() => canNext && setPage((p) => p + 1)}
              disabled={!canNext}
              data-testid="system-logs-next"
              className="px-2 py-1 rounded border border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              다음
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
