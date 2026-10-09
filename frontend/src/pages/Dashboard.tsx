import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTradingStatus } from '../contexts/TradingStatusContext'
import { getStrategyColor } from '../types/strategy'
import { STRATEGY_INFO, ALL_STRATEGIES_INFO } from '../utils/strategyInfo'
import { strategyLabel } from '../utils/strategyMeta'
import { getStrategiesMonitor } from '../api/strategies'
import { getExitLines } from '../api/balance'
import { getRecentFunnel } from '../api/strategy-funnel'
import ControlPanel from '../components/ControlPanel'
import MarketRegimeCard from '../components/MarketRegimeCard'
import MarketRegimeLabelCard from '../components/MarketRegimeLabelCard'
import PortfolioRiskCard from '../components/PortfolioRiskCard'
import KisAccountPoolCard from '../components/KisAccountPoolCard'
import ScanMonitor from '../components/ScanMonitor'
import OrderMonitor from '../components/OrderMonitor'
import PerformanceCard from '../components/PerformanceCard'
import ProfitChart from '../components/ProfitChart'
import BalanceTable from '../components/BalanceTable'
import StrategyMonitor from '../components/StrategyMonitor'
import StrategySummaryTable from '../components/StrategySummaryTable'
import { extractDailyFinalCounts } from './StrategyFunnel'
// 사이클 6 (2026-05-17): LogViewer 는 /logs 메뉴로 분리됨. Dashboard 하단 제거.

// cycle414 — 전략별 진행상황(§2.1): 「전체」 탭은 요약표, 전략 탭은 상세 패널. 고지로는
// 기존 ScanMonitor 내 KojiroMonitor 가 이미 그리므로 중복 렌더를 피해 여기서는 건너뛴다.
const RECENT_FUNNEL_DAYS = 14

export default function Dashboard() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')
  const [showTabTooltip, setShowTabTooltip] = useState(false)
  const tabsBoxRef = useRef<HTMLDivElement>(null)

  const { data: status } = useTradingStatus()

  const strategies = status?.strategies ?? {}
  const strategyKeys = Object.keys(strategies)

  // cycle414 §2.10 — 10초 폴링(탭 무관, 캐시 가벼움). 실패해도 null 폴백(status 데이터로 그린다).
  const monitorQuery = useQuery({
    queryKey: ['strategies-monitor'],
    queryFn: getStrategiesMonitor,
    refetchInterval: 10_000,
    retry: false,
  })
  const exitLinesQuery = useQuery({
    queryKey: ['balance-exit-lines'],
    queryFn: getExitLines,
    refetchInterval: 10_000,
    retry: false,
  })
  // 14일 추이는 전략 탭을 열 때만(고지로는 KojiroMonitor 전용 — 이번 범위 밖), 10분 캐시.
  const showDetailPanel = selectedStrategy !== 'all' && selectedStrategy !== 'kojiro'
  const recentFunnelQuery = useQuery({
    queryKey: ['strategy-funnel-recent-panel', selectedStrategy],
    queryFn: () => getRecentFunnel(selectedStrategy, RECENT_FUNNEL_DAYS),
    enabled: showDetailPanel,
    staleTime: 10 * 60_000,
    retry: false,
  })
  const funnelTrend = recentFunnelQuery.data ? extractDailyFinalCounts(recentFunnelQuery.data.snapshots) : null

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

      {/* cycle410 (2026-10-05): 6장세 라벨 — 관찰 전용, 매매에 쓰지 않는다 */}
      <MarketRegimeLabelCard />

      {/* 사이클 I (2026-08-03): 포트폴리오 리스크 관찰 카드 — 시장 레짐 직하 (관찰 전용, Phase 1) */}
      <PortfolioRiskCard />

      {/* 사이클 7-D (2026-05-18): KIS 시세 풀 — 시장 상태 → 인프라 상태 위계 */}
      <KisAccountPoolCard />

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
                  {strategyLabel(key, info.name)}
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

      {/* cycle414 — 「전체」 탭 = 전략 요약표, 전략 탭 = 상세 패널(고지로는 아래 ScanMonitor 가 그린다). */}
      {selectedStrategy === 'all' ? (
        <StrategySummaryTable
          strategies={strategies}
          monitor={monitorQuery.data ?? null}
          exitLines={exitLinesQuery.data?.items ?? null}
          tickerPrices={status?.scan?.ticker_prices}
          onSelect={setSelectedStrategy}
        />
      ) : showDetailPanel ? (
        <StrategyMonitor
          strategyId={selectedStrategy}
          strategies={strategies}
          monitor={monitorQuery.data ?? null}
          exitLines={exitLinesQuery.data?.items ?? null}
          tickerPrices={status?.scan?.ticker_prices}
          tickerNames={status?.scan?.ticker_names}
          subscribedTickers={status?.scan?.subscribed_tickers}
          funnelTrend={funnelTrend}
        />
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ScanMonitor
          selectedStrategy={selectedStrategy}
          monitor={monitorQuery.data ?? null}
          exitLines={exitLinesQuery.data?.items ?? null}
        />
        <OrderMonitor selectedStrategy={selectedStrategy} />
      </div>
      <BalanceTable selectedStrategy={selectedStrategy} />
      <PerformanceCard selectedStrategy={selectedStrategy} />
      <ProfitChart selectedStrategy={selectedStrategy} />
    </div>
  )
}
