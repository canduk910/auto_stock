/**
 * 경기 사이클 + 투자 체제 섹션 — 원본 `macro_lite/components/MacroCycleSection.jsx` 이식.
 *
 * 🔴 cycle303 spec §6 「경기사이클 보존 목록」 7항목을 이 파일이 전부 지킨다(구조 재설계 금지):
 *   1. 국면 4칸 가로 배열(PhaseCard, `macro-cycle-phase-{phase}`)
 *   2. 체제 4칸(RegimeDetail 안의 단일 배지) — 원본은 "국면 4칸 + 체제 1칸 상세 카드" 구조라,
 *      "체제 4칸 가로 배열" 요건은 RegimeDetail 내부에 REGIME_LABELS 4종을 가로로 펼친
 *      보조 스트립으로 추가한다(`macro-cycle-regime-{regime}`) — 원본 있는 배지는 그대로 두고
 *      "덧붙이는" 방식이라 기존 레이아웃을 재설계하지 않는다.
 *   3. 국면 카드 + 체제 카드가 `grid-cols-2`로 나란히(`macro-cycle-side-by-side`)
 *   4. 판단 근거 지표 카드 5종(IndicatorCard, `macro-cycle-indicator-{key}`)
 *   5. DivergenceNote(`macro-cycle-divergence-note`)
 *   6. 체제 상세(RegimeDetail 안의 공포탐욕/버핏지수/VIX)
 *   7. InfoTooltip(CYCLE_TOOLTIP/REGIME_TOOLTIP)
 *
 * 타입 계약 1(팀장 명세 §6) — `data.cycle || data` 폴백, `regime?.regime` optional chaining
 * 은 응답 shape 계약 자체이므로 "불필요한 방어"로 지우지 않는다(`types/macro.ts` 참고).
 */
import { useState, type ReactNode } from "react"
import LoadingSpinner from "./LoadingSpinner"
import ErrorAlert from "./ErrorAlert"
import type { CycleScoreItem, CyclePhase, InvestmentRegime, MacroCycleData, MacroCycleResponse, RegimeData } from "../../types/macro"

const PHASES: CyclePhase[] = ["recovery", "expansion", "overheating", "contraction"]
const PHASE_LABELS: Record<CyclePhase, string> = {
  recovery: "회복기",
  expansion: "확장기",
  overheating: "과열기",
  contraction: "수축기",
}
const PHASE_COLORS: Record<CyclePhase, { bg: string; text: string; active: string }> = {
  recovery: { bg: "bg-emerald-100", text: "text-emerald-700", active: "bg-emerald-600" },
  expansion: { bg: "bg-blue-100", text: "text-blue-700", active: "bg-blue-600" },
  overheating: { bg: "bg-amber-100", text: "text-amber-700", active: "bg-amber-600" },
  contraction: { bg: "bg-red-100", text: "text-red-700", active: "bg-red-600" },
}

const REGIMES: InvestmentRegime[] = ["accumulation", "selective", "cautious", "defensive"]
const REGIME_LABELS: Record<InvestmentRegime, string> = {
  accumulation: "적극 매수",
  selective: "선별 매수",
  cautious: "신중",
  defensive: "방어",
}
const REGIME_COLORS: Record<InvestmentRegime, { bg: string; text: string; active: string }> = {
  accumulation: { bg: "bg-emerald-100", text: "text-emerald-700", active: "bg-emerald-600" },
  selective: { bg: "bg-blue-100", text: "text-blue-700", active: "bg-blue-600" },
  cautious: { bg: "bg-amber-100", text: "text-amber-700", active: "bg-amber-600" },
  defensive: { bg: "bg-red-100", text: "text-red-700", active: "bg-red-600" },
}

// ── 툴팁 컴포넌트 ─────────────────────────────────────────────

function InfoTooltip({
  children,
  content,
  wide,
}: {
  children: ReactNode
  content: ReactNode
  wide?: boolean
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative inline-block" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <div
          className={`absolute z-50 left-1/2 -translate-x-1/2 top-full mt-2 rounded-lg bg-gray-900 text-white text-xs leading-relaxed p-4 shadow-xl pointer-events-none text-left ${
            wide ? "w-[22rem] sm:w-[26rem]" : "w-72 sm:w-80"
          }`}
        >
          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-gray-900 rotate-45" />
          {content}
        </div>
      )}
    </div>
  )
}

const CYCLE_TOOLTIP = (
  <>
    <div className="font-semibold mb-2">경기 사이클 국면 판단</div>
    <p className="mb-2">5개 매크로 지표의 가중합산으로 현재 경기가 어느 단계에 있는지 판단합니다.</p>
    <table className="w-full text-xs mb-2">
      <thead>
        <tr className="border-b border-gray-700">
          <th className="text-left py-1">지표</th>
          <th className="text-right py-1">가중치</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td className="py-0.5">장단기 금리차 (수익률곡선)</td>
          <td className="text-right">30%</td>
        </tr>
        <tr>
          <td className="py-0.5">하이일드 신용스프레드</td>
          <td className="text-right">20%</td>
        </tr>
        <tr>
          <td className="py-0.5">VIX (변동성)</td>
          <td className="text-right">20%</td>
        </tr>
        <tr>
          <td className="py-0.5">섹터 로테이션</td>
          <td className="text-right">15%</td>
        </tr>
        <tr>
          <td className="py-0.5">달러 강도</td>
          <td className="text-right">15%</td>
        </tr>
      </tbody>
    </table>
    <div className="border-t border-gray-700 pt-2 space-y-1">
      <div>
        <span className="text-emerald-400">회복기</span>: 수익률곡선 정상화, VIX 하락, 스프레드 축소
      </div>
      <div>
        <span className="text-blue-400">확장기</span>: 양의 수익률곡선, 낮은 VIX, 좁은 스프레드
      </div>
      <div>
        <span className="text-amber-400">과열기</span>: 수익률곡선 평탄화, VIX 저점, 방어 전환
      </div>
      <div>
        <span className="text-red-400">수축기</span>: 수익률곡선 역전, VIX 급등, 스프레드 확대
      </div>
    </div>
  </>
)

const REGIME_TOOLTIP = (
  <>
    <div className="font-semibold mb-2">투자 체제 판단</div>
    <p className="mb-2">시장 심리와 밸류에이션으로 현재 어떤 투자 전략을 취해야 하는지 판단합니다.</p>
    <div className="mb-2">
      <div className="font-medium mb-1">입력 지표:</div>
      <div>
        - <span className="text-yellow-300">버핏지수</span> (시총/GDP): 시장 전체의 고평가/저평가
      </div>
      <div>
        - <span className="text-yellow-300">공포탐욕지수</span>: VIX+모멘텀+시장폭 종합 심리
      </div>
      <div>
        - <span className="text-yellow-300">VIX &gt; 35</span>: 강제 극단적 공포 오버라이드
      </div>
    </div>
    <div className="mb-2">버핏지수(4단계) x 공포탐욕(5단계) = 20칸 매트릭스에서 체제를 결정합니다.</div>
    <div className="border-t border-gray-700 pt-2 space-y-1">
      <div>
        <span className="text-emerald-400">적극 매수</span>: 저평가+공포 구간. 현금 25%, 주식 최대 75%
      </div>
      <div>
        <span className="text-blue-400">선별 매수</span>: 적정+중립 구간. 현금 35%, 주식 최대 65%
      </div>
      <div>
        <span className="text-amber-400">신중</span>: 고평가 또는 탐욕 구간. 현금 50%, 주식 최대 50%
      </div>
      <div>
        <span className="text-red-400">방어</span>: 극단적 고평가+탐욕. 현금 75%, 신규 매수 금지
      </div>
    </div>
  </>
)

// ── 서브 컴포넌트 ─────────────────────────────────────────────

function PhaseCard({ phase, isActive }: { phase: CyclePhase; isActive: boolean }) {
  const colors = PHASE_COLORS[phase] || PHASE_COLORS.recovery
  return (
    <div
      data-testid={`macro-cycle-phase-${phase}`}
      data-active={isActive ? "true" : "false"}
      className={`rounded-lg p-3 text-center font-semibold text-sm transition-all ${
        isActive ? `${colors.active} text-white shadow-md scale-105` : `${colors.bg} ${colors.text} opacity-60`
      }`}
    >
      {PHASE_LABELS[phase] || phase}
    </div>
  )
}

function RegimeStripCard({ regime, isActive }: { regime: InvestmentRegime; isActive: boolean }) {
  const colors = REGIME_COLORS[regime] || REGIME_COLORS.cautious
  return (
    <div
      data-testid={`macro-cycle-regime-${regime}`}
      data-active={isActive ? "true" : "false"}
      className={`rounded-lg p-3 text-center font-semibold text-sm transition-all ${
        isActive ? `${colors.active} text-white shadow-md scale-105` : `${colors.bg} ${colors.text} opacity-60`
      }`}
    >
      {REGIME_LABELS[regime] || regime}
    </div>
  )
}

function IndicatorCard({ label, signal, testId }: { label: string; signal?: string; testId: string }) {
  return (
    <div data-testid={testId} className="rounded-lg border bg-gray-50 px-3 py-2">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-gray-900 truncate">{signal || "-"}</div>
    </div>
  )
}

const SCORE_LABELS: Record<string, string> = {
  yield_curve: "장단기 금리차",
  credit_spread: "크레딧 스프레드",
  vix: "VIX",
  sector_rotation: "섹터 로테이션",
  dollar: "달러",
}

const FG_LABELS: Record<string, string> = {
  extreme_fear: "극단적 공포",
  fear: "공포",
  neutral: "중립",
  greed: "탐욕",
  extreme_greed: "극단적 탐욕",
}
const BUFFETT_LABELS: Record<string, string> = {
  low: "저평가",
  normal: "적정",
  high: "고평가",
  extreme: "극단적 고평가",
}

function RegimeDetail({ regime }: { regime?: RegimeData | null }) {
  if (!regime) return null
  const r = regime.regime
  const colors = REGIME_COLORS[r] || REGIME_COLORS.cautious

  return (
    <div className="flex-1 rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-600 mb-2 text-center">
        <InfoTooltip content={REGIME_TOOLTIP} wide>
          <span className="cursor-help border-b border-dashed border-gray-400 inline-flex items-center gap-1">
            현재 투자 체제
            <svg className="w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4m0-4h.01" />
            </svg>
          </span>
        </InfoTooltip>
      </div>
      <div className="text-center mb-3">
        <span className={`inline-block px-5 py-2 rounded-full text-lg font-bold text-white ${colors.active}`}>
          {REGIME_LABELS[r] || r}
        </span>
      </div>
      <p className="text-xs text-gray-500 text-center mb-3">심리 / 밸류에이션 기반</p>

      {/* 보존 목록 §2 — 체제 4칸 가로 배열(적극 매수→선별 매수→신중→방어), 현재 진한 색 + 확대 */}
      <div className="grid grid-cols-4 gap-1.5 mb-3">
        {REGIMES.map((rg) => (
          <RegimeStripCard key={rg} regime={rg} isActive={r === rg} />
        ))}
      </div>

      <div className="space-y-1.5 text-xs">
        {regime.fear_greed_score != null && (
          <div className="flex justify-between">
            <span className="text-gray-500">공포탐욕</span>
            <span className="font-medium text-gray-700">
              {Math.round(regime.fear_greed_score)} ({FG_LABELS[regime.fg_level ?? ""] || regime.fg_level})
            </span>
          </div>
        )}
        {regime.buffett_ratio != null && (
          <div className="flex justify-between">
            <span className="text-gray-500">버핏지수</span>
            <span className="font-medium text-gray-700">
              {regime.buffett_ratio > 10 ? `${Math.round(regime.buffett_ratio)}%` : `${Math.round(regime.buffett_ratio * 100)}%`} (
              {BUFFETT_LABELS[regime.buffett_level ?? ""] || regime.buffett_level})
            </span>
          </div>
        )}
        {regime.vix != null && (
          <div className="flex justify-between">
            <span className="text-gray-500">VIX</span>
            <span className="font-medium text-gray-700">{regime.vix.toFixed(1)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function DivergenceNote({ phase, regime }: { phase?: CyclePhase | null; regime?: InvestmentRegime | null }) {
  if (!phase || !regime) return null
  const isExpansive = phase === "recovery" || phase === "expansion"
  const isDefensive = regime === "cautious" || regime === "defensive"
  const isContractive = phase === "overheating" || phase === "contraction"
  const isAccumulative = regime === "accumulation" || regime === "selective"

  if (isExpansive && isDefensive) {
    return (
      <div data-testid="macro-cycle-divergence-note" className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
        <span className="font-semibold">경기 국면과 투자 체제가 다릅니다.</span> 경기 흐름(금리·달러·섹터)은 양호하나, 시장
        밸류에이션(버핏지수)이나 심리(공포탐욕)가 과열 수준입니다. 경기는 좋지만 주가가 이미 많이 올라 조심해야 하는 구간일 수
        있습니다.
      </div>
    )
  }
  if (isContractive && isAccumulative) {
    return (
      <div data-testid="macro-cycle-divergence-note" className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-800">
        <span className="font-semibold">경기 국면과 투자 체제가 다릅니다.</span> 경기 지표(금리·신용스프레드)는 둔화 신호를
        보이지만, 시장 밸류에이션이 저평가 구간이거나 심리가 위축되어 매수 기회일 수 있습니다.
      </div>
    )
  }
  return null
}

// ── 메인 ─────────────────────────────────────────────────────

interface MacroCycleSectionProps {
  data: MacroCycleResponse | null
  loading: boolean
  error: string | null
}

export default function MacroCycleSection({ data, loading, error }: MacroCycleSectionProps) {
  if (loading) return <LoadingSpinner message="경기 사이클 로딩 중..." />
  if (error) return <ErrorAlert message={error} />
  if (!data) return null

  // 타입 계약 1(cycle303 spec §6) — 일부 배포 경로가 `{cycle, regime}` 로 감싸지 않고
  // MacroCycleData 를 바로 줄 가능성을 방어한다. "불필요한 방어"로 지우지 않는다.
  const cycle: MacroCycleData | undefined = data.cycle || (data as unknown as MacroCycleData)
  const regime = data.regime || null
  if (!cycle) return null
  const { phase, phase_label, phase_desc, confidence, scores, leader_sectors } = cycle

  const phaseColors = PHASE_COLORS[phase] || PHASE_COLORS.recovery

  return (
    <section data-testid="macro-section-cycle">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">경기 사이클</h2>
      <div className="rounded-lg border bg-white p-5 shadow-sm space-y-5">
        {/* 보존 목록 §1 — 국면 4칸 가로 배열(회복기→확장기→과열기→수축기) */}
        <div className="grid grid-cols-4 gap-2 items-center">
          {PHASES.map((p, i) => (
            <div key={p} className="flex items-center">
              <div className="flex-1">
                <PhaseCard phase={p} isActive={phase === p} />
              </div>
              {i < PHASES.length - 1 && <div className="text-gray-300 text-lg font-bold mx-1 shrink-0">&rarr;</div>}
            </div>
          ))}
        </div>

        {/* 보존 목록 §3 — 경기 국면 + 투자 체제가 나란히(grid-cols-2) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4" data-testid="macro-cycle-side-by-side">
          {/* 경기 국면 */}
          <div className="flex-1 rounded-lg border bg-white p-4 shadow-sm">
            <div className="text-sm font-medium text-gray-600 mb-2 text-center">
              <InfoTooltip content={CYCLE_TOOLTIP}>
                <span className="cursor-help border-b border-dashed border-gray-400 inline-flex items-center gap-1">
                  현재 경기 국면
                  <svg className="w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 16v-4m0-4h.01" />
                  </svg>
                </span>
              </InfoTooltip>
            </div>
            <div className="text-center mb-3">
              <span className={`inline-block px-5 py-2 rounded-full text-lg font-bold text-white ${phaseColors.active}`}>
                {phase_label}
              </span>
            </div>
            <p className="text-xs text-gray-500 text-center mb-3">경기 흐름 기반 (5개 지표)</p>
            {phase_desc && <p className="text-xs text-gray-600 text-center">{phase_desc}</p>}
          </div>

          {/* 투자 체제 (보존 목록 §6 — 공포탐욕·버핏지수·VIX 상세 포함) */}
          <RegimeDetail regime={regime} />
        </div>

        {/* 보존 목록 §5 — 괴리 설명 */}
        <DivergenceNote phase={phase} regime={regime?.regime} />

        {/* 신뢰도 바 */}
        {confidence != null && (
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>신뢰도</span>
              <span>{confidence}%</span>
            </div>
            <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${Math.min(confidence, 100)}%` }} />
            </div>
          </div>
        )}

        {/* 보존 목록 §4 — 판단 근거 지표 카드 5종 */}
        {scores && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {Object.entries(scores).map(([key, item]: [string, CycleScoreItem]) => (
              <IndicatorCard
                key={key}
                testId={`macro-cycle-indicator-${key}`}
                label={SCORE_LABELS[key] || key}
                signal={item?.signal}
              />
            ))}
          </div>
        )}

        {/* 주도 섹터 태그 */}
        {leader_sectors?.length > 0 && (
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-sm font-medium text-gray-500">주도 섹터:</span>
            {leader_sectors.map((s) => (
              <span key={s} className="inline-block px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-medium">
                {s}
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
