import { useSearchParams } from 'react-router-dom'
import SystemLogsTab from '../components/SystemLogsTab'
import DailyReportTab from '../components/DailyReportTab'

/**
 * Logs 페이지 — 사이클 6 (2026-05-17).
 *
 * 메뉴 "/logs 로그" 단일 진입점. 두 탭:
 *  - system: 시스템 로그 (기간 + 레벨 + 페이징)
 *  - daily-report: 일일 로그 분석 리포트 (기존 LogReports)
 *
 * URL 쿼리 `?tab=system | daily-report` 로 활성 탭 표현 → 북마크/새로고침 상태 보존.
 * 기본 `system`.
 */

type TabKey = 'system' | 'daily-report'

function isTabKey(v: string | null): v is TabKey {
  return v === 'system' || v === 'daily-report'
}

export default function Logs() {
  const [searchParams, setSearchParams] = useSearchParams()
  const raw = searchParams.get('tab')
  const active: TabKey = isTabKey(raw) ? raw : 'system'

  const setTab = (tab: TabKey) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    setSearchParams(next, { replace: true })
  }

  return (
    <div>
      {/* 탭 헤더 */}
      <div className="bg-white rounded-lg shadow mb-4">
        <div className="flex border-b border-gray-200" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={active === 'system'}
            data-testid="logs-tab-system"
            onClick={() => setTab('system')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              active === 'system'
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-600 hover:text-gray-900'
            }`}
          >
            시스템 로그
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={active === 'daily-report'}
            data-testid="logs-tab-daily-report"
            onClick={() => setTab('daily-report')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              active === 'daily-report'
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-600 hover:text-gray-900'
            }`}
          >
            일일 로그 분석
          </button>
        </div>
      </div>

      {/* 탭 본문 */}
      <div role="tabpanel">
        {active === 'system' ? <SystemLogsTab /> : <DailyReportTab />}
      </div>
    </div>
  )
}
