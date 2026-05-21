import { lazy, Suspense } from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { TradingStatusProvider, useTradingStatus } from './contexts/TradingStatusContext'
import Dashboard from './pages/Dashboard'

// 비메인 페이지는 동적 import — 초기 번들 분리(Recharts/TanStack Table 페이지 단위로 떨어져 나감)
const History = lazy(() => import('./pages/History'))
const Recommendations = lazy(() => import('./pages/Recommendations'))
// 사이클 6 (2026-05-17): /log-reports → /logs?tab=daily-report 로 통합. 기존 페이지는 redirect.
const Logs = lazy(() => import('./pages/Logs'))
const Settings = lazy(() => import('./pages/Settings'))
// 사이클 34 (2026-05-21) — 조건검색 단계별 추적 신규 페이지
const StrategyFunnel = lazy(() => import('./pages/StrategyFunnel'))

const navItems = [
  { to: '/', label: '대시보드' },
  { to: '/history', label: '거래 내역' },
  { to: '/recommendations', label: '전략수정 AI자문' },
  { to: '/strategy-funnel', label: '조건검색 추적' },
  { to: '/logs', label: '로그' },
  { to: '/settings', label: '설정' },
]

function PageFallback() {
  return (
    <div className="bg-white rounded-lg shadow p-8 animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-1/3 mb-4" />
      <div className="space-y-2">
        <div className="h-4 bg-gray-100 rounded" />
        <div className="h-4 bg-gray-100 rounded w-5/6" />
        <div className="h-4 bg-gray-100 rounded w-4/6" />
      </div>
    </div>
  )
}

function EnvBanner() {
  const { data: status } = useTradingStatus()
  if (!status) return null
  return (
    <div className={`text-center text-white text-sm font-medium py-1 ${
      status.env === 'real' ? 'bg-red-600' : 'bg-green-600'
    }`}>
      {status.env === 'real' ? '실전 매매 환경' : '모의투자 환경'}
    </div>
  )
}

function AppShell() {
  return (
    <div className="min-h-screen bg-gray-100">
      {/* 상단 환경 배너 + 네비게이션 — 스크롤해도 항상 화면 최상단에 고정 */}
      <div className="sticky top-0 z-50">
        <EnvBanner />

        <nav className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center h-14 gap-8">
              <span className="font-bold text-gray-900">AutoStock</span>
              <div className="flex gap-4">
                {navItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) =>
                      `text-sm font-medium px-3 py-2 rounded-md ${
                        isActive
                          ? 'bg-gray-100 text-gray-900'
                          : 'text-gray-600 hover:text-gray-900'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          </div>
        </nav>
      </div>

      <main className="max-w-7xl mx-auto px-4 py-6">
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<History />} />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/strategy-funnel" element={<StrategyFunnel />} />
            <Route path="/logs" element={<Logs />} />
            {/* 사이클 6: 기존 북마크 호환 — /log-reports → /logs?tab=daily-report */}
            <Route
              path="/log-reports"
              element={<Navigate to="/logs?tab=daily-report" replace />}
            />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <TradingStatusProvider>
      <AppShell />
    </TradingStatusProvider>
  )
}
