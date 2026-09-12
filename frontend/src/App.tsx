import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { TradingStatusProvider, useTradingStatus } from './contexts/TradingStatusContext'
import Dashboard from './pages/Dashboard'
import NavBar from './components/NavBar'
import { contentMaxWidth, useContentWidth } from './utils/contentWidth'

// 비메인 페이지는 동적 import — 초기 번들 분리(Recharts/TanStack Table 페이지 단위로 떨어져 나감)
const History = lazy(() => import('./pages/History'))
const Recommendations = lazy(() => import('./pages/Recommendations'))
// 사이클 6 (2026-05-17): /log-reports → /logs?tab=daily-report 로 통합. 기존 페이지는 redirect.
const Logs = lazy(() => import('./pages/Logs'))
const Settings = lazy(() => import('./pages/Settings'))
// 사이클 34 (2026-05-21) — 조건검색 단계별 추적 신규 페이지
const StrategyFunnel = lazy(() => import('./pages/StrategyFunnel'))
// 사이클 85 (2026-06-09) — stock_master UI 신규 페이지 (Q2=A 7번째 메뉴)
const StockMaster = lazy(() => import('./pages/StockMaster'))
// 사이클 103 (2026-06-11) — 실시간 건강 모니터링 신규 페이지 (8번째 메뉴)
const RealtimeHealth = lazy(() => import('./pages/RealtimeHealth'))
// 사이클 103 (2026-06-11) — 전략 현황 (손절 임계 가시화) 신규 페이지 (9번째 메뉴)
const Strategies = lazy(() => import('./pages/Strategies'))
// cycle282 (2026-09-11) — 장운영상태(거래소 실제 장 운영 상태 + 주문유형 카탈로그) 신규 페이지
const MarketState = lazy(() => import('./pages/MarketState'))

// cycle288 (2026-09-12) — 나브 항목 구조(그룹 묶음 포함)는 components/NavBar.tsx 로 이전.
// 여기 남는 것은 라우트·레이아웃뿐이다. 화면 폭 슬라이더 상태(useContentWidth)는 나브(슬라이더)와
// main(적용 대상) 양쪽이 공유해야 해서 AppShell 이 계속 소유하고 NavBar 에는 값/콜백만 내려준다.

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
      status.env === 'real' ? 'bg-red-600' : 'bg-sky-600'
    }`}>
      {status.env === 'real' ? '실전 매매 환경' : '모의투자 환경'}
    </div>
  )
}

function AppShell() {
  const { level: contentWidthLevel, setLevel: setContentWidthLevel } = useContentWidth()

  return (
    <div className="min-h-screen bg-beige-100">
      {/* 상단 환경 배너 + 네비게이션 — 스크롤해도 항상 화면 최상단에 고정 */}
      <div className="sticky top-0 z-50" data-testid="nav-sticky-wrapper">
        <EnvBanner />
        <NavBar contentWidthLevel={contentWidthLevel} onContentWidthChange={setContentWidthLevel} />
      </div>

      <main
        className="mx-auto px-4 py-6"
        style={{ maxWidth: contentMaxWidth(contentWidthLevel) }}
      >
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<History />} />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/strategy-funnel" element={<StrategyFunnel />} />
            {/* 사이클 85 (2026-06-09) — stock_master UI */}
            <Route path="/stock-master" element={<StockMaster />} />
            <Route path="/logs" element={<Logs />} />
            {/* 사이클 6: 기존 북마크 호환 — /log-reports → /logs?tab=daily-report */}
            <Route
              path="/log-reports"
              element={<Navigate to="/logs?tab=daily-report" replace />}
            />
            <Route path="/settings" element={<Settings />} />
            {/* 사이클 103 (2026-06-11) — 실시간 건강 + 전략 현황 */}
            <Route path="/realtime-health" element={<RealtimeHealth />} />
            <Route path="/strategies" element={<Strategies />} />
            {/* cycle282 (2026-09-11) — 장운영상태 */}
            <Route path="/market-state" element={<MarketState />} />
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
