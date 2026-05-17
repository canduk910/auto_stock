import { useEffect, useRef, useState } from 'react'
import { useTradingStatus } from '../contexts/TradingStatusContext'
import { getStrategyColor } from '../types/strategy'
import { STRATEGY_INFO, ALL_STRATEGIES_INFO } from '../utils/strategyInfo'
import ControlPanel from '../components/ControlPanel'
import MarketRegimeCard from '../components/MarketRegimeCard'
import ScanMonitor from '../components/ScanMonitor'
import OrderMonitor from '../components/OrderMonitor'
import PerformanceCard from '../components/PerformanceCard'
import ProfitChart from '../components/ProfitChart'
import BalanceTable from '../components/BalanceTable'
import LogViewer from '../components/LogViewer'

export default function Dashboard() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')
  const [showTabTooltip, setShowTabTooltip] = useState(false)
  const tabsBoxRef = useRef<HTMLDivElement>(null)

  const { data: status } = useTradingStatus()

  const strategies = status?.strategies ?? {}
  const strategyKeys = Object.keys(strategies)

  useEffect(() => {
    if (!showTabTooltip) return
    const onDocClick = (e: MouseEvent) => {
      if (!tabsBoxRef.current?.contains(e.target as Node)) setShowTabTooltip(false)
    }
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowTabTooltip(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onEsc)
    }
  }, [showTabTooltip])

  const handleTabClick = (key: string) => {
    setSelectedStrategy(key)
    setShowTabTooltip(true)
  }

  const activeTooltip =
    selectedStrategy === 'all'
      ? { tagline: ALL_STRATEGIES_INFO.tagline, description: ALL_STRATEGIES_INFO.description }
      : STRATEGY_INFO[selectedStrategy] ?? null

  return (
    <div className="space-y-6">
      <ControlPanel />

      {/* 사이클 2 (2026-05-17): 시장 레짐 카드 — 환경 배너 직하, 전략 탭 위 */}
      <MarketRegimeCard />

      {/* 전략 선택 탭 */}
      {strategyKeys.length > 0 && (
        <div ref={tabsBoxRef} className="bg-white rounded-lg shadow px-4 py-2 overflow-visible">
          <div className="flex flex-wrap items-center gap-1">
            <button
              onClick={() => handleTabClick('all')}
              className={`px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-colors ${
                selectedStrategy === 'all'
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              전체
            </button>
            {strategyKeys.map((key) => {
              const info = strategies[key]
              const color = getStrategyColor(key)
              const isActive = selectedStrategy === key
              return (
                <button
                  key={key}
                  onClick={() => handleTabClick(key)}
                  className={`px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-colors ${
                    isActive
                      ? `${color.badge} ring-1 ring-current`
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  {info.name}
                  <span className="ml-1.5 text-xs opacity-70">
                    ({info.positions})
                  </span>
                </button>
              )
            })}
          </div>

          {/* 활성 탭 설명 패널 — 탭 클릭 시 표시, 외부 클릭/ESC로 닫힘 */}
          {showTabTooltip && activeTooltip && (
            <div className="mt-3 px-4 py-3 bg-gray-900 text-white rounded-md shadow-lg relative">
              <button
                type="button"
                onClick={() => setShowTabTooltip(false)}
                aria-label="설명 닫기"
                className="absolute top-2 right-2 text-gray-300 hover:text-white text-xs px-2 py-0.5 rounded hover:bg-gray-700"
              >
                ✕
              </button>
              <div className="text-sm font-semibold mb-1 pr-6">{activeTooltip.tagline}</div>
              <div className="text-xs whitespace-pre-line leading-relaxed text-gray-100">
                {activeTooltip.description}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ScanMonitor selectedStrategy={selectedStrategy} />
        <OrderMonitor selectedStrategy={selectedStrategy} />
      </div>
      <BalanceTable selectedStrategy={selectedStrategy} />
      <PerformanceCard selectedStrategy={selectedStrategy} />
      <ProfitChart selectedStrategy={selectedStrategy} />
      <LogViewer />
    </div>
  )
}
