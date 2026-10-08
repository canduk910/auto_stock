import { useQuery } from '@tanstack/react-query'
import { getPerformanceSummary } from '../api/performance'
import { getStrategyTeRr } from '../api/strategies'
import { useTradingStatus } from '../contexts/TradingStatusContext'
import type { TeRrMetrics } from '../types/strategy'
import { pnlColorClass as profitColor } from '../utils/pnlColor'
import { strategyLabel } from '../utils/strategyMeta'
import { useCostBasis } from '../utils/costBasis'
import CostBasisToggle from './CostBasisToggle'

/**
 * 백엔드 계약은 숫자(`PerformanceSummary.latest_asset: number`)이고 `src/routes/performance.py`
 * 가 `float()` 로 그 계약을 지킨다. 다만 그 값의 출처가 NUMERIC 컬럼이라 사영이 빠지면
 * 문자열이 오는데, `String` 에는 자체 `toLocaleString` 이 없어 `Object.prototype` 쪽으로
 * 떨어져 **예외 없이 천단위 구분만 조용히 사라진다**(`'10720000.00'` 그대로). 숫자로 강제해
 * 그 무증상 열화를 막는다.
 */
function formatKRW(value: number | string): string {
  const n = Number(value)
  return Number.isFinite(n) ? n.toLocaleString('ko-KR') + '원' : '-'
}

function formatKRWSigned(value: number): string {
  const sign = value > 0 ? '+' : ''
  return sign + Math.round(value).toLocaleString('ko-KR') + '원'
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

  // cycle411 — 세후(net) 기본 + 세전(gross) 토글. net 칸 없는(구 서버) 응답은 세전으로 폴백한다(PN5).
  const [costBasis, setCostBasis] = useCostBasis()

  if (isLoading) return <div className="p-6 text-gray-500">실적 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">실적 데이터를 불러올 수 없습니다.</div>
  if (!data) return null

  // 전체(all) 탭의 latest_asset/수익률은 daily_performance 의 strategy='total' row
  // (scheduler._settle 이 KIS 잔고 실측 net_asset 으로 기록) — 실제 값이라 정직.
  // 특정 전략 탭은 strategy=X row (배분 예산 + 당일 실현손익 합성값) — 오해 소지 있어 라벨링.
  const isStrategySynthetic = strategyParam !== undefined

  const isNet = costBasis === 'net'
  // cycle411c B3 — 세후 칸은 비용 조회 실패 시 **null**(undefined 가 아니라 명시적 「모름」)
  // 로 온다. `!= null` 로 걸러야 null·undefined 둘 다 세전 값으로 폴백한다. 세후 칸이
  // 없어서(폴백) 보이는 값인지를 따로 추적해 그 카드에 「세전」 을 단다(PC1·PC3).
  const totalReturnIsGrossFallback = isNet && data.net_total_profit_rate == null
  const totalReturn = isNet && data.net_total_profit_rate != null
    ? data.net_total_profit_rate
    : data.total_profit_rate
  const avgDailyReturnIsGrossFallback = isNet && data.net_avg_daily_profit_rate == null
  const avgDailyReturn = isNet && data.net_avg_daily_profit_rate != null
    ? data.net_avg_daily_profit_rate
    : data.avg_daily_profit_rate

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
      value: totalReturn.toFixed(2) + '%',
      colorValue: totalReturn,
      grossFallback: totalReturnIsGrossFallback,
    },
    {
      key: 'avg-daily-return',
      label: isStrategySynthetic ? '일평균 수익률(합성)' : '일평균 수익률',
      value: avgDailyReturn.toFixed(2) + '%',
      colorValue: avgDailyReturn,
      grossFallback: avgDailyReturnIsGrossFallback,
    },
  ]

  // 선택 탭에 해당하는 실현 성과 행 — 'all' 이면 전 전략, 아니면 1건.
  const teRows: TeRrMetrics[] =
    selectedStrategy === 'all'
      ? teData ?? []
      : (teData ?? []).filter((m) => m.strategy_id === selectedStrategy)

  return (
    <div className="space-y-3" data-testid="performance-card">
      <div className="flex justify-end">
        <CostBasisToggle value={costBasis} onChange={setCostBasis} />
      </div>
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
            {/* cycle411c B3 — 세후 칸이 null(모름)이라 세전 값으로 폴백한 카드에만 표시 */}
            {card.grossFallback && (
              <span className="text-[10px] text-gray-400">세전</span>
            )}
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
                    <span className="text-sm text-gray-800">{strategyLabel(m.strategy_id, info?.name)}</span>
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
                      {(() => {
                        // cycle411 PN6 — 세후 기본 = realized_net_sum_krw, 세전 = realized_sum_krw.
                        // cycle411c B3 — 세후 칸이 null(비용 조회 실패, 「모름」)이면 세전으로
                        // 폴백하고 그 사실을 「세전」 으로 밝힌다(0원으로 치지 않는다).
                        const realizedIsGrossFallback = isNet && m.realized_net_sum_krw == null
                        const realized =
                          isNet && m.realized_net_sum_krw != null
                            ? m.realized_net_sum_krw
                            : m.realized_sum_krw
                        return (
                          <span
                            data-testid={`realized-pnl-${m.strategy_id}`}
                            className={`text-sm font-semibold ${profitColor(realized)}`}
                          >
                            {formatKRWSigned(realized)}
                            {realizedIsGrossFallback && (
                              <span className="ml-1 text-[10px] text-gray-400">세전</span>
                            )}
                          </span>
                        )
                      })()}
                      {(() => {
                        // cycle411b M5 — 세전 모드는 win_rate_gross·win_gross·loss_gross (없으면 세후 값 폴백).
                        const winRate =
                          !isNet && m.win_rate_gross !== undefined ? m.win_rate_gross : m.win_rate
                        const win = !isNet && m.win_gross !== undefined ? m.win_gross : m.win
                        const loss = !isNet && m.loss_gross !== undefined ? m.loss_gross : m.loss
                        return (
                          <span
                            data-testid={`realized-winrate-${m.strategy_id}`}
                            className="text-xs text-gray-500"
                          >
                            승률 {(winRate * 100).toFixed(0)}% (승{win}/패{loss})
                          </span>
                        )
                      })()}
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
