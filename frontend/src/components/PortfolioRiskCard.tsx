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
import type { AccountGate, GateLevel, PortfolioRiskBucket } from '../types/portfolio'
import { formatKstHHMM } from '../utils/kst'
import ScrollPane from './ScrollPane'

const SECTOR_CONCENTRATION_WARNING_PCT = 40

function formatWon(value: number): string {
  return `${Math.round(value).toLocaleString('ko-KR')}원`
}

/**
 * 사이클 256 (리팩토링 카드 #10) — `AccountGate.level` 런타임 가드.
 *
 * 타입이 `GateLevel` 유니온이어도 API 응답은 컴파일 타임 보장 밖이다(백엔드가
 * 미지 값을 보낼 가능성). 미지 값은 이 가드가 걸러 아래 배지 로직이 알려진 4
 * 레벨과 정확히 같은 방식으로만 분기하게 한다 — 걸러진 값은 어떤 분기에도 걸리지
 * 않아 기존 `else` 분기("정상" 배지)와 동일하게 처리된다.
 */
export function isKnownLevel(value: unknown): value is GateLevel {
  return value === 'ok' || value === 'warn' || value === 'block' || value === 'error'
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

      <AccountGateBlock gate={data.account_gate} />

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
          <ScrollPane>
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
          </ScrollPane>
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

interface AccountGateBlockProps {
  gate: AccountGate | null | undefined
}

/**
 * 사이클 251 — 계좌 SOFT Σ상한 게이트 관측 배지 (cycle239 후속 F).
 *
 * `GET /api/portfolio/risk` 의 `data.account_gate` 를 그대로 표시한다.
 * `account_risk_watcher.get_gate_state()` 8키 — 백엔드 graceful 실패 시 키
 * 자체가 없거나 null 일 수 있어 그 경로는 "게이트 정보 없음" 한 줄로 처리한다
 * (기존 MSW 기본 응답이 이 경로 — 기존 카드 테스트 4건이 이 분기를 통과한다).
 */
function AccountGateBlock({ gate }: AccountGateBlockProps) {
  if (!gate) {
    return (
      <div
        className="border-t pt-3 mt-3 text-xs text-gray-400"
        data-testid="portfolio-risk-gate-absent"
      >
        게이트 정보 없음
      </div>
    )
  }

  const level = isKnownLevel(gate.level) ? gate.level : undefined
  const isBlocked = gate.effective_gated
  const isWarn = !isBlocked && level === 'warn'
  const isError = level === 'error'
  const isStale = gate.stale

  let badgeText = '정상'
  let badgeClass = 'bg-gray-100 text-gray-600'
  if (isBlocked) {
    badgeText = '차단 중'
    badgeClass = 'bg-red-100 text-red-700'
  } else if (isWarn) {
    badgeText = '경고'
    // cycle261 후속(적대 검토) — amber→beige 별칭 이후 종전 amber-100 이 gray-100("정상")과
    // 거의 같은 배경이 돼(sRGB 거리 ≈10.5) 구분이 글자색 채도 차이 하나에만 의존했다.
    // beige-200 로 배경 축 구분을 복원(거리 ≈39).
    badgeClass = 'bg-beige-200 text-beige-800'
  }

  const openRiskDisplay =
    gate.open_risk_pct === null || gate.open_risk_pct === undefined
      ? '—'
      : `${gate.open_risk_pct.toFixed(2)}%`

  const evaluatedDisplay = formatKstHHMM(gate.evaluated_at)

  const ageMinutes =
    gate.age_secs === null || gate.age_secs === undefined ? null : Math.floor(gate.age_secs / 60)

  // 동결 서명 — `level=block ∧ stale ∧ !effective_gated` 이면 "판정 자체는
  // 차단이었지만 신선도가 지나 fail-open 으로 풀렸다"는 사실을 툴팁으로 설명한다
  // (cycle239 R1 — 이 상태에서 배지가 "차단 중"으로 보이면 실제와 반대로 읽힌다).
  const freezeTitle =
    isStale && level === 'block' && !isBlocked
      ? 'block 판정이 stale 로 fail-open 되었습니다 (마지막 평가가 오래되어 매수 차단이 해제된 상태)'
      : undefined

  return (
    <div
      className="border-t pt-3 mt-3"
      data-testid="portfolio-risk-account-gate"
      title={freezeTitle}
    >
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <h3 className="text-sm font-medium text-gray-700">계좌 게이트</h3>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeClass}`}
          data-testid="portfolio-risk-gate-badge"
        >
          {badgeText}
        </span>
        {isStale && (
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-200 text-gray-600"
            data-testid="portfolio-risk-gate-stale"
          >
            STALE
          </span>
        )}
      </div>
      <div className="text-xs text-gray-600 flex flex-wrap gap-x-3 gap-y-0.5">
        <span>오픈 리스크 {openRiskDisplay}</span>
        <span>평가 시각 {evaluatedDisplay}</span>
        {isStale && ageMinutes !== null && <span>마지막 평가 {ageMinutes}분 전</span>}
        {isError && gate.reasons.length > 0 && (
          <span className="text-gray-400 lowercase">{gate.reasons[0]}</span>
        )}
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
