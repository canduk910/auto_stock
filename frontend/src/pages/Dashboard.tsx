import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from '../api/trading'
import { getStrategyColor } from '../types/strategy'
import { STRATEGY_INFO, ALL_STRATEGIES_INFO } from '../utils/strategyInfo'
import ControlPanel from '../components/ControlPanel'
import InfoTooltip from '../components/InfoTooltip'
import ScanMonitor from '../components/ScanMonitor'
import OrderMonitor from '../components/OrderMonitor'
import PerformanceCard from '../components/PerformanceCard'
import ProfitChart from '../components/ProfitChart'
import BalanceTable from '../components/BalanceTable'
import LogViewer from '../components/LogViewer'

export default function Dashboard() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')

  const { data: status } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
  })

  const strategies = status?.strategies ?? {}
  const strategyKeys = Object.keys(strategies)

  return (
    <div className="space-y-6">
      <ControlPanel />

      {/* 전략 선택 탭 */}
      {strategyKeys.length > 0 && (
        <div className="bg-white rounded-lg shadow px-4 py-2 overflow-visible">
          <div className="flex flex-wrap items-center gap-1">
            <span className="inline-flex items-center">
              <button
                onClick={() => setSelectedStrategy('all')}
                className={`px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-colors ${
                  selectedStrategy === 'all'
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                전체
              </button>
              <InfoTooltip content={ALL_STRATEGIES_INFO.description} ariaLabel="전체 탭 설명" />
            </span>
            {strategyKeys.map((key) => {
              const info = strategies[key]
              const color = getStrategyColor(key)
              const isActive = selectedStrategy === key
              const strategyInfo = STRATEGY_INFO[key]
              return (
                <span key={key} className="inline-flex items-center">
                  <button
                    onClick={() => setSelectedStrategy(key)}
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
                  {strategyInfo && (
                    <InfoTooltip
                      content={`${strategyInfo.tagline}\n\n${strategyInfo.description}`}
                      ariaLabel={`${info.name} 전략 설명`}
                    />
                  )}
                </span>
              )
            })}
          </div>
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
