/**
 * 사이클 I (2026-08-03): 포트폴리오 리스크 관찰 카드 (Part 4).
 *
 * `MarketRegimeCard.tsx` 템플릿 복제 — 관찰 전용(매수 차단/배제 없음, Phase 1).
 * 노출 정보:
 * - 요약 4지표: 총 명목가치 / 오픈 리스크 / 순자산 대비 % / 동시 보유
 * - 섹터별 리스크 집중 수평 막대 (`ScanMonitor.tsx::ScanFunnelBars` 패턴 재사용)
 * - 전략별 리스크 표
 * - top_sector 섹터 집중 경고 배너 (risk_share_pct >= 40)
 */
import { useQuery } from '@tanstack/react-query'
import { getPortfolioRisk } from '../api/portfolio'
import type { PortfolioRiskBucket } from '../types/portfolio'

const SECTOR_CONCENTRATION_WARNING_PCT = 40

function formatWon(value: number): string {
  return `${Math.round(value).toLocaleString('ko-KR')}원`
}

export default function PortfolioRiskCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['portfolioRisk'],
    queryFn: getPortfolioRisk,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4 mb-4" data-testid="portfolio-risk-card">
        <div className="text-gray-500 text-sm">포트폴리오 리스크 로딩 중...</div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="bg-white rounded-lg shadow p-4 mb-4" data-testid="portfolio-risk-card">
        <div className="text-gray-500 text-sm">포트폴리오 리스크 정보를 불러오지 못했습니다.</div>
      </div>
    )
  }

  const sectorEntries = Object.entries(data.by_sector).sort(
    (a, b) => b[1].risk_won - a[1].risk_won,
  )
  const strategyEntries = Object.entries(data.by_strategy).sort(
    (a, b) => b[1].risk_won - a[1].risk_won,
  )
  const maxSectorRisk = Math.max(1, ...sectorEntries.map(([, v]) => v.risk_won))

  const showConcentrationWarning =
    data.top_sector !== null && data.top_sector.risk_share_pct >= SECTOR_CONCENTRATION_WARNING_PCT

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4" data-testid="portfolio-risk-card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-900">포트폴리오 리스크 (관찰)</h2>
        <span className="text-xs text-gray-400">Phase 1 — 관찰 전용, 매수 배제 없음</span>
      </div>

      {showConcentrationWarning && data.top_sector && (
        <div
          data-testid="portfolio-risk-top-sector-banner"
          className="mb-3 px-3 py-2 bg-amber-50 border border-amber-300 rounded text-sm text-amber-900"
        >
          <strong>섹터 집중 경고</strong> — {data.top_sector.sector}{' '}
          {data.top_sector.risk_share_pct.toFixed(1)}%
          <div className="text-xs text-amber-700 mt-1">참고용 관찰 지표 — 자동 매수 제한 없음</div>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <Metric
          label="총 명목가치"
          value={formatWon(data.total_notional_won)}
          testId="portfolio-risk-total-notional"
        />
        <Metric
          label="오픈 리스크"
          value={formatWon(data.total_open_risk_won)}
          testId="portfolio-risk-open-risk"
        />
        <Metric
          label="순자산 대비"
          value={`${data.open_risk_pct_of_net.toFixed(2)}%`}
          testId="portfolio-risk-open-pct"
        />
        <Metric
          label="동시 보유"
          value={`${data.concurrent_positions}종목`}
          testId="portfolio-risk-concurrent-positions"
        />
      </div>

      <div className="border-t pt-3 mt-3">
        <h3 className="text-sm font-medium text-gray-700 mb-2">섹터별 리스크 집중</h3>
        {sectorEntries.length === 0 ? (
          <div className="text-xs text-gray-400" data-testid="portfolio-risk-sector-empty">
            보유 포지션 없음
          </div>
        ) : (
          <div className="space-y-1" data-testid="portfolio-risk-sector-bars">
            {sectorEntries.map(([sector, bucket]) => (
              <SectorBarRow
                key={sector}
                sector={sector}
                bucket={bucket}
                maxVal={maxSectorRisk}
              />
            ))}
          </div>
        )}
      </div>

      <div className="border-t pt-3 mt-3">
        <h3 className="text-sm font-medium text-gray-700 mb-2">전략별 리스크</h3>
        {strategyEntries.length === 0 ? (
          <div className="text-xs text-gray-400" data-testid="portfolio-risk-strategy-empty">
            보유 포지션 없음
          </div>
        ) : (
          <table className="w-full text-xs" data-testid="portfolio-risk-strategy-table">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="font-normal pb-1">전략</th>
                <th className="font-normal pb-1 text-right">보유</th>
                <th className="font-normal pb-1 text-right">명목가치</th>
                <th className="font-normal pb-1 text-right">리스크</th>
              </tr>
            </thead>
            <tbody>
              {strategyEntries.map(([sid, bucket]) => (
                <tr key={sid} data-testid={`portfolio-risk-strategy-row-${sid}`}>
                  <td className="py-0.5 text-gray-700">{sid}</td>
                  <td className="py-0.5 text-right font-mono">{bucket.positions}</td>
                  <td className="py-0.5 text-right font-mono">{formatWon(bucket.notional_won)}</td>
                  <td className="py-0.5 text-right font-mono">{formatWon(bucket.risk_won)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

interface SectorBarRowProps {
  sector: string
  bucket: PortfolioRiskBucket
  maxVal: number
}

function SectorBarRow({ sector, bucket, maxVal }: SectorBarRowProps) {
  const widthPct = Math.round((bucket.risk_won / maxVal) * 100)
  return (
    <div
      className="flex items-center gap-2 text-xs"
      data-testid={`portfolio-risk-sector-row-${sector}`}
    >
      <div className="w-24 shrink-0 text-gray-700 truncate" title={sector}>
        {sector}
      </div>
      <div className="flex-1">
        <div className="flex items-baseline justify-between mb-0.5">
          <span className="text-gray-500">{bucket.positions}종목</span>
          <span className="font-mono font-medium text-gray-700">
            {formatWon(bucket.risk_won)}
          </span>
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-indigo-300 transition-all"
            style={{ width: `${widthPct}%` }}
          />
        </div>
      </div>
    </div>
  )
}

interface MetricProps {
  label: string
  value: string
  testId: string
}
function Metric({ label, value, testId }: MetricProps) {
  return (
    <div className="bg-gray-50 rounded px-3 py-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-sm font-mono font-semibold text-gray-900" data-testid={testId}>
        {value}
      </div>
    </div>
  )
}
