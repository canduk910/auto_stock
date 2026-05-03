import { Routes, Route, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from './api/trading'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Recommendations from './pages/Recommendations'
import Settings from './pages/Settings'

const navItems = [
  { to: '/', label: '대시보드' },
  { to: '/history', label: '거래 내역' },
  { to: '/recommendations', label: '파라미터 추천' },
  { to: '/settings', label: '설정' },
]

export default function App() {
  const { data: status } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
    retry: false,
  })

  return (
    <div className="min-h-screen bg-gray-100">
      {status && (
        <div className={`text-center text-white text-sm font-medium py-1 ${
          status.env === 'real' ? 'bg-red-600' : 'bg-green-600'
        }`}>
          {status.env === 'real' ? '실전 매매 환경' : '모의투자 환경'}
        </div>
      )}

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

      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
