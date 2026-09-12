import { lazy, Suspense, useState } from 'react'
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
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
// 사이클 85 (2026-06-09) — stock_master UI 신규 페이지 (Q2=A 7번째 메뉴)
const StockMaster = lazy(() => import('./pages/StockMaster'))
// 사이클 103 (2026-06-11) — 실시간 건강 모니터링 신규 페이지 (8번째 메뉴)
const RealtimeHealth = lazy(() => import('./pages/RealtimeHealth'))
// 사이클 103 (2026-06-11) — 전략 현황 (손절 임계 가시화) 신규 페이지 (9번째 메뉴)
const Strategies = lazy(() => import('./pages/Strategies'))
// cycle282 (2026-09-11) — 장운영상태(거래소 실제 장 운영 상태 + 주문유형 카탈로그) 신규 페이지
const MarketState = lazy(() => import('./pages/MarketState'))

const navItems = [
  { to: '/', label: '대시보드' },
  { to: '/history', label: '거래 내역' },
  { to: '/recommendations', label: '전략수정 AI자문' },
  { to: '/strategy-funnel', label: '조건검색 추적' },
  { to: '/stock-master', label: '종목마스터' },
  { to: '/logs', label: '로그' },
  { to: '/settings', label: '설정' },
  { to: '/realtime-health', label: '실시간 상태' },
  { to: '/strategies', label: '전략 현황' },
  { to: '/market-state', label: '장운영상태' },
]

// 나브바 화면 폭 슬라이더 — 콘텐츠 max-width 사용자 조정 (localStorage 영속)
const CONTENT_WIDTH_STORAGE_KEY = 'autostock.contentWidth'
const CONTENT_WIDTH_DEFAULT_LEVEL = 100

function clampContentWidthLevel(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function readStoredContentWidthLevel(): number {
  try {
    const raw = window.localStorage.getItem(CONTENT_WIDTH_STORAGE_KEY)
    if (raw === null) return CONTENT_WIDTH_DEFAULT_LEVEL
    const parsed = parseInt(raw, 10)
    if (Number.isNaN(parsed)) return CONTENT_WIDTH_DEFAULT_LEVEL
    return clampContentWidthLevel(parsed)
  } catch {
    return CONTENT_WIDTH_DEFAULT_LEVEL
  }
}

function contentMaxWidth(level: number): string {
  return `max(1024px, ${60 + level * 0.4}%)`
}

function useContentWidth() {
  // SSR 없음(vite CSR) — lazy 초기화 함수가 최초 렌더 시 localStorage 를 직접 읽어 복원한다.
  const [level, setLevelState] = useState<number>(() => readStoredContentWidthLevel())

  const setLevel = (next: number) => {
    const clamped = clampContentWidthLevel(next)
    setLevelState(clamped)
    try {
      window.localStorage.setItem(CONTENT_WIDTH_STORAGE_KEY, String(clamped))
    } catch {
      // localStorage 접근 불가 환경(예: 프라이빗 모드) — graceful, state 는 이미 갱신됨
    }
  }

  return { level, setLevel }
}

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

// 모바일 햄버거 메뉴 — 현재 경로를 표시하기 위해 useLocation 사용
function MobileMenuLabel() {
  const { pathname } = useLocation()
  const current = navItems.find((item) =>
    item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)
  )
  return (
    <span className="text-sm font-medium text-gray-700">
      {current?.label ?? '메뉴'}
    </span>
  )
}

function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { level: contentWidthLevel, setLevel: setContentWidthLevel } = useContentWidth()

  return (
    <div className="min-h-screen bg-beige-100">
      {/* 상단 환경 배너 + 네비게이션 — 스크롤해도 항상 화면 최상단에 고정 */}
      <div className="sticky top-0 z-50" data-testid="nav-sticky-wrapper">
        <EnvBanner />

        <nav className="bg-white shadow-sm" aria-label="기본 네비게이션">
          {/* 나브 내부 폭도 콘텐츠(main)와 동일하게 — 전체폭 시 메뉴/슬라이더가 콘텐츠 좌우 끝에 정렬 */}
          <div className="mx-auto px-4" style={{ maxWidth: contentMaxWidth(contentWidthLevel) }}>
            {/* PC (sm 이상): 한 줄 가로 메뉴 */}
            <div className="hidden sm:flex items-center h-14 gap-8">
              <span className="font-brand font-bold tracking-tight text-gray-900 shrink-0">DK Stock</span>
              <div className="flex gap-1 flex-wrap">
                {navItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) =>
                      `text-sm font-medium px-3 py-2 rounded-md whitespace-nowrap ${
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

              {/* 화면 폭 조정 슬라이더 — 콘텐츠 max-width 사용자 조정, PC 전용(모바일은 소화면이라 조정 불요) */}
              <div className="ml-auto flex items-center gap-2 shrink-0">
                <span className="text-xs text-gray-400 select-none" aria-hidden="true">
                  폭
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={contentWidthLevel}
                  onChange={(e) => setContentWidthLevel(Number(e.target.value))}
                  data-testid="content-width-slider"
                  aria-label="화면 폭 조정"
                  className="w-24 h-2 rounded-lg appearance-none cursor-pointer"
                  style={{ accentColor: 'var(--color-navy-600)' }}
                />
              </div>
            </div>

            {/* 모바일 (sm 미만): 로고 + 현재 메뉴명 + 햄버거 버튼 */}
            <div className="flex sm:hidden items-center justify-between h-14">
              <span className="font-brand font-bold tracking-tight text-gray-900">DK Stock</span>
              <MobileMenuLabel />
              <button
                data-testid="mobile-menu-button"
                aria-label="메뉴 열기"
                aria-expanded={mobileOpen}
                onClick={() => setMobileOpen((prev) => !prev)}
                className="p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
              >
                {/* 햄버거 / X 아이콘 */}
                {mobileOpen ? (
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                ) : (
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          {/* 모바일 드롭다운 메뉴 */}
          {mobileOpen && (
            <div
              data-testid="mobile-menu-drawer"
              className="sm:hidden border-t border-gray-100 bg-white shadow-md"
            >
              <div className="px-2 py-2 space-y-1">
                {navItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      `block text-sm font-medium px-3 py-2 rounded-md ${
                        isActive
                          ? 'bg-gray-100 text-gray-900'
                          : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          )}
        </nav>
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
