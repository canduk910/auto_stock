import { useQuery } from '@tanstack/react-query'
import { getPerformanceSummary } from '../api/performance'
import { getStrategyTeRr } from '../api/strategies'
import { useTradingStatus } from '../contexts/TradingStatusContext'
import type { TeRrMetrics } from '../types/strategy'

function formatKRW(value: number): string {
  return value.toLocaleString('ko-KR') + '원'
}

function formatKRWSigned(value: number): string {
  const sign = value > 0 ? '+' : ''
  return sign + Math.round(value).toLocaleString('ko-KR') + '원'
}

function profitColor(value: number): string {
  if (value > 0) return 'text-[#FF3333]'
  if (value < 0) return 'text-[#3366FF]'
  return 'text-[#333333]'
}

interface Props {
  selectedStrategy: string
}

export default function PerformanceCard({ selectedStrategy }: Props) {
  const strategyParam = selectedStrategy === 'all' ? undefined : selectedStrategy

  const { data, isLoading, isError } = useQuery({
    queryKey: ['performanceSummary', strategyParam],
    queryFn: () => getPerformanceSummary(strategyParam),
    retry: 1,
  })

  // 완결 매매 기준 실현손익 — daily_performance.total_asset(전략별=배분예산+당일실현손익
  // 합성값)과 분리된 정직한 성과. strategy-te 쿼리키는 Strategies.tsx 와 동일 —
  // 캐시 공유(중복 네트워크 호출 없음).
  const {
    data: teData,
    isLoading: teIsLoading,
    isError: teIsError,
  } = useQuery({
    queryKey: ['strategy-te', 3],
    queryFn: () => getStrategyTeRr(3),
    retry: 1,
    staleTime: 5 * 60 * 1000,
  })

  const { data: status } = useTradingStatus()
  const strategies = status?.strategies ?? {}

  if (isLoading) return <div className="p-6 text-gray-500">실적 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">실적 데이터를 불러올 수 없습니다.</div>
  if (!data) return null

  // 전체(all) 탭의 latest_asset/수익률은 daily_performance 의 strategy='total' row
  // (scheduler._settle 이 KIS 잔고 실측 net_asset 으로 기록) — 실제 값이라 정직.
  // 특정 전략 탭은 strategy=X row (배분 예산 + 당일 실현손익 합성값) — 오해 소지 있어 라벨링.
  const isStrategySynthetic = strategyParam !== undefined

  const cards = [
    { key: 'total-days', label: '운영 일수', value: `${data.total_days}일` },
    {
      key: 'latest-asset',
      label: isStrategySynthetic ? '배분 예산(합성)' : '최근 자산',
      value: formatKRW(data.latest_asset),
    },
    {
      key: 'total-return',
      label: isStrategySynthetic ? '누적 수익률(합성)' : '누적 수익률',
      value: data.total_profit_rate.toFixed(2) + '%',
      colorValue: data.total_profit_rate,
    },
    {
      key: 'avg-daily-return',
      label: isStrategySynthetic ? '일평균 수익률(합성)' : '일평균 수익률',
      value: data.avg_daily_profit_rate.toFixed(2) + '%',
      colorValue: data.avg_daily_profit_rate,
    },
  ]

  // 선택 탭에 해당하는 실현 성과 행 — 'all' 이면 전 전략, 아니면 1건.
  const teRows: TeRrMetrics[] =
    selectedStrategy === 'all'
      ? teData ?? []
      : (teData ?? []).filter((m) => m.strategy_id === selectedStrategy)

  return (
    <div className="space-y-3" data-testid="performance-card">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div key={card.key} className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-500 mb-1">{card.label}</p>
            <p
              data-testid={`performance-metric-${card.key}`}
              className={`text-lg font-semibold ${
                card.colorValue !== undefined ? profitColor(card.colorValue) : 'text-gray-900'
              }`}
            >
              {card.value}
            </p>
          </div>
        ))}
      </div>

      {/* 전략별 탭은 배분 예산 + 당일 실현손익 합성값 — 실제 누적 성과로 오인되지 않도록 명시 */}
      {isStrategySynthetic && (
        <div
          data-testid="performance-synthetic-banner"
          className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700"
        >
          위 자산/수익률은 <b>전략 배분 예산(비중×순자산) + 당일 실현손익 기준 합성값</b>입니다.
          체결이 없어도 비중만큼 자산이 잡히고, 비중이 바뀌면 과거 수익률이 왜곡될 수 있습니다.
          아래 <b>실현 성과</b>가 완결 매매 기준 실제 손익입니다.
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-4" data-testid="realized-performance-section">
        <p className="text-sm font-semibold text-gray-900 mb-2">실현 성과 (완결 매매 기준, 최근 3개월)</p>

        {teIsLoading && (
          <p data-testid="realized-performance-loading" className="text-xs text-gray-400">
            실현 성과 로딩 중...
          </p>
        )}

        {!teIsLoading && teIsError && (
          <p data-testid="realized-performance-error" className="text-xs text-red-500">
            서버 연결 끊김 — 실현 성과 조회 실패
          </p>
        )}

        {!teIsLoading && !teIsError && teRows.length === 0 && (
          <p data-testid="realized-performance-empty" className="text-xs text-gray-400">
            실현 성과 데이터 없음
          </p>
        )}

        {!teIsLoading && !teIsError && teRows.length > 0 && (
          <div className="space-y-2">
            {teRows.map((m) => {
              const info = strategies[m.strategy_id]
              const isInsufficient = m.sample_tier === 'insufficient'
              return (
                <div
                  key={m.strategy_id}
                  data-testid={`realized-row-${m.strategy_id}`}
                  className="flex items-center justify-between flex-wrap gap-2 border-t border-gray-100 pt-2 first:border-t-0 first:pt-0"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-800">{info?.name ?? m.strategy_id}</span>
                    {info && (
                      <span
                        data-testid={`strategy-status-badge-${m.strategy_id}`}
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          info.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {info.enabled ? '활성' : '비활성'} · 비중 {(info.weight * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>

                  {isInsufficient ? (
                    <span
                      data-testid={`realized-insufficient-badge-${m.strategy_id}`}
                      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500"
                    >
                      체결 {m.n}건 — 실현 성과 미확정
                    </span>
                  ) : (
                    <div className="flex items-center gap-3">
                      <span
                        data-testid={`realized-pnl-${m.strategy_id}`}
                        className={`text-sm font-semibold ${profitColor(m.realized_sum_krw)}`}
                      >
                        {formatKRWSigned(m.realized_sum_krw)}
                      </span>
                      <span data-testid={`realized-winrate-${m.strategy_id}`} className="text-xs text-gray-500">
                        승률 {(m.win_rate * 100).toFixed(0)}% (승{m.win}/패{m.loss})
                      </span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
