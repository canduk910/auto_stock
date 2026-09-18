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
 * 🔴 두 단계이동 스트립은 **각자의 카드 안 같은 자리**에 있다(cycle306, 사용자 지시).
 * 국면 4칸은 원래 카드 **밖 맨 위**에 있어 카드 **안**에 있는 체제 4칸과 위치가 어긋났다.
 * 지금은 둘 다 「제목 → 큰 배지 → 부제 → 4칸 스트립 → 상세」 순서를 공유한다 — 한쪽만
 * 옮기면 그 어긋남이 되살아나므로, 한쪽 순서를 바꿀 땐 다른 쪽도 같이 바꾼다.
 * 스트립 마크업도 `grid-cols-4 gap-1.5 mb-3` 로 동일하다. 국면 쪽에 있던 화살표(→)는
 * 뺐다 — 반쪽 폭 카드에서 화살표가 자리를 60px 먹어 4칸 라벨이 찌그러진다.
 *
 * 🔴 **새 testid 에 `macro-cycle-phase-` · `macro-cycle-indicator-` 접두사를 쓰지 않는다.**
 * 위 보존 가드가 그 두 접두사를 정규식으로 세기 때문에, 접두사를 물려받는 순간 "국면 4칸" 이
 * 11칸이 되고 "지표 카드 5종" 이 10종이 된다. 점수차 블록은 `macro-cycle-gap*`,
 * 기여 줄은 `macro-cycle-contrib-{key}` 를 쓴다(cycle306 에서 실제로 밟고 고쳤다).
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

function PhaseCard({ phase, isActive, score }: { phase: CyclePhase; isActive: boolean; score?: number | null }) {
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
      {/* 4국면 점수는 `final_scores` 가 왔을 때만 뜬다 — 없으면 이 줄이 없고 나머지는 byte 동일.
          이게 "5개 지표가 어느 국면 쪽으로 엎치락뒤치락했나" 를 보여 주는 유일한 자리다. */}
      {score != null && (
        <div className={`mt-0.5 text-[11px] font-medium tabular-nums ${isActive ? "text-white/80" : "opacity-80"}`}>
          {score.toFixed(2)}
        </div>
      )}
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

/**
 * 숫자 방어 변환 — 숫자·숫자 문자열만 유한수로 통과시키고 나머지는 `null`.
 * 이 리포는 미검증 값에 `toFixed`/`toLocaleString` 을 직접 불러 화면이 조용히 빈 사고를
 * 세 번 겪었다(`frontend/CLAUDE.md` 「테스트 규약」 5). 렌더는 이 함수를 지난 값에만 건다.
 */
function toNum(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/**
 * 지표 카드 — 신호 + **당선 국면에 보탠 점수**.
 *
 * 🔴 보여 주는 것은 `score`(당선 국면 기여)뿐이고 `score / weight`(지지율)는 **쓰지 않는다**.
 * 지표마다 한 국면에 줄 수 있는 상한이 다르기 때문이다 — 과열기 기준 상한이 금리차 0.80 ·
 * 나머지 넷 0.30 이라, 지지율을 나란히 세우면 "VIX 가 약하게 밀었다" 로 읽히지만 실은
 * VIX 가 과열기에 줄 수 있는 최대치가 원래 0.30 이다. 반면 `score` 는 전부 같은 국면에 보탠
 * 가중 기여라 서로 비교되고 **다 더하면 그 국면 총점**이 된다(실측: 0.34).
 */
function IndicatorCard({
  label,
  signal,
  testId,
  score,
  maxScore,
  phaseLabel,
}: {
  label: string
  signal?: string
  testId: string
  score: number | null
  maxScore: number | null
  phaseLabel?: string
}) {
  // 프론트가 볼 수 있는 결측 증거는 `signal === "-"` 하나뿐이고, 그나마 금리차·VIX 에만
  // 나타난다 — 크레딧·섹터·달러는 백엔드가 기본값 문자열("안정"/"혼합"/"보합")로 떨어뜨려
  // 결측을 구분할 수 없다. 없는 구분을 있는 척하지 않는다.
  const missing = !signal || signal.trim() === "-"
  const barPct = score !== null && maxScore !== null && maxScore > 0 ? Math.max(0, Math.min(100, (score / maxScore) * 100)) : null
  // 🔴 `${testId}-contrib` 로 만들면 보존 규약의 `macro-cycle-indicator-` 접두사에 걸려
  // "지표 카드 5종" 가드가 10개를 센다. 접두사를 공유하지 않는 이름을 따로 쓴다.
  const contribTestId = `macro-cycle-contrib-${testId.replace("macro-cycle-indicator-", "")}`

  return (
    <div data-testid={testId} data-missing={missing ? "true" : "false"} className="rounded-lg border bg-gray-50 px-3 py-2">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-gray-900 truncate">{signal || "-"}</div>

      {missing ? (
        <div data-testid={contribTestId} className="mt-1.5 text-[11px] text-gray-400">
          값 없음 — 집계에서 빠졌습니다
        </div>
      ) : score === null ? null : score === 0 ? (
        <div data-testid={contribTestId} className="mt-1.5 text-[11px] text-gray-500">
          다른 국면 쪽
        </div>
      ) : (
        <div data-testid={contribTestId} className="mt-1.5">
          <div className="flex items-baseline justify-between text-[11px] text-gray-500 mb-0.5">
            <span className="truncate">{phaseLabel ? `${phaseLabel}에 보탬` : "보탬"}</span>
            <span className="font-semibold text-gray-700 tabular-nums">+{score.toFixed(3)}</span>
          </div>
          {barPct !== null && (
            <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-gray-500" style={{ width: `${barPct}%` }} />
            </div>
          )}
        </div>
      )}
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

/**
 * 1·2위 점수차 블록 — 원본의 「신뢰도 N%」 막대를 대체한다.
 *
 * 🔴 이 값은 **맞을 가능성이 아니다.** `cycle.py:222` 의 `(1위 총점 − 2위 총점) × 200` 이고
 * 과거 적중률로 교정한 적이 없다. "신뢰도 14%" 라는 표기가 "14% 확률로 맞다" 로 읽히던 것이
 * 이 블록을 만든 이유다(사용자: "신뢰도가 잘 와닿지가 않아"). 그래서 셋을 함께 바꾼다 —
 * 이름을 뺄셈 결과(`1·2위 점수차`)로, 단위를 `%` 에서 `점` 으로, 눈금을 0~100% 차오르는
 * 게이지에서 **1위를 100% 로 잡은 상대 막대**로.
 *
 * 🔴 **0~1.00 공통 눈금을 쓰지 않는다.** 국면마다 도달 가능한 최대 총점이 다르기 때문이다 —
 * 입력 전수 탐색 실측으로 회복기 0.61 · 확장기 0.60 · **과열기 0.45** · 수축기 0.97 이다.
 * 1.00 을 만점으로 그리면 과열기가 1위인 날은 무슨 수를 써도 막대가 절반을 못 넘어,
 * "왜 낮은가" 를 설명하려던 화면이 "이 판정은 늘 부실하다" 를 그림으로 주장하게 된다.
 *
 * 구간 낱말(팽팽/보통/뚜렷)에 **고정 컷을 두지 않는다.** 그날의 실제 기여값에서 끌어낸다 —
 * 한 지표가 1위에서 2위로 돌아서면 격차는 그 기여의 **2배**만큼 줄므로, `2 × 기여 > 격차` 인
 * 지표가 곧 "혼자서 순위를 뒤집을 수 있는 지표" 다.
 */
const GAP_BANDS = {
  tight: { label: "팽팽", cls: "bg-amber-100 text-amber-800" },
  mid: { label: "보통", cls: "bg-gray-200 text-gray-700" },
  clear: { label: "뚜렷", cls: "bg-blue-100 text-blue-800" },
} as const

function PhaseGapBlock({
  confidence,
  scores,
  phase,
  phaseLabel,
  finalScores,
}: {
  confidence?: number | null
  scores?: Record<string, CycleScoreItem> | null
  phase: CyclePhase
  phaseLabel?: string
  finalScores?: Record<string, number> | null
}) {
  const conf = toNum(confidence)
  if (conf === null) return null

  const contributions = Object.values(scores ?? {})
    .map((item) => toNum(item?.score))
    .filter((v): v is number => v !== null)
  const positive = contributions.filter((v) => v > 0)

  // `final_scores` 가 오면 2위의 **이름과 점수를 그대로** 쓴다. 없으면 `Σscore − confidence/200`
  // 으로 역산하는데, `confidence` 가 정수 반올림이라 ±0.0075 오차를 안고 이름은 알 수 없다.
  const ranked = Object.entries(finalScores ?? {})
    .map(([k, v]) => [k, toNum(v)] as const)
    .filter((e): e is readonly [string, number] => e[1] !== null)
    .sort((a, b) => b[1] - a[1])
  const hasRanking = ranked.length >= 2
  const secondKey = hasRanking ? (ranked[1][0] as CyclePhase) : null
  const secondName = secondKey ? PHASE_LABELS[secondKey] || secondKey : null

  // 상한(100)에 걸렸는지는 역산 경로에서만 의미가 있다 — 실제 점수가 오면 격차도 실제값이다.
  const gap = hasRanking ? ranked[0][1] - ranked[1][1] : conf / 200
  const atCap = !hasRanking && conf >= 100
  const topTotal = hasRanking
    ? ranked[0][1]
    : contributions.length
      ? contributions.reduce((a, b) => a + b, 0)
      : null
  const secondTotal = hasRanking ? ranked[1][1] : topTotal !== null ? Math.max(0, topTotal - gap) : null
  const secondPct = topTotal !== null && topTotal > 0 && secondTotal !== null ? Math.min(100, (secondTotal / topTotal) * 100) : null

  // 혼자 돌아서면 순위를 뒤집는 지표 수
  const flippable = positive.filter((v) => 2 * v > gap).length
  const band = !positive.length ? "mid" : flippable === positive.length ? "tight" : flippable === 0 ? "clear" : "mid"
  const bandMeta = GAP_BANDS[band]

  const note = !positive.length
    ? null
    : flippable === 0
      ? "어느 지표 하나가 다른 국면 쪽으로 돌아서도 순위는 유지됩니다."
      : flippable === positive.length
        ? `지표 ${positive.length}개 중 **어느 하나**가 다른 국면 쪽으로 돌아서도 순위가 뒤집힙니다.`
        : `지표 ${positive.length}개 중 ${flippable}개는 혼자 돌아서면 순위를 뒤집습니다.`

  const phaseColors = PHASE_COLORS[phase] || PHASE_COLORS.recovery

  return (
    <div data-testid="macro-cycle-gap" className="rounded-lg border bg-gray-50 p-3">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-sm font-medium text-gray-600">1·2위 점수차</span>
        <div className="flex items-center gap-2">
          <span data-testid="macro-cycle-gap-band" className={`px-2 py-0.5 rounded-full text-xs font-semibold ${bandMeta.cls}`}>
            {bandMeta.label}
          </span>
          <span data-testid="macro-cycle-gap-value" className="text-lg font-bold text-gray-900 tabular-nums">
            {gap.toFixed(2)}
            <span className="text-xs font-medium text-gray-500 ml-0.5">{atCap ? "점 이상" : "점"}</span>
          </span>
        </div>
      </div>

      {topTotal !== null && topTotal > 0 && (
        <div className="space-y-1.5 mb-2.5">
          <div className="flex items-center gap-2" data-testid="macro-cycle-gap-top">
            <span className="w-24 shrink-0 text-xs text-gray-600 truncate">1위 {phaseLabel}</span>
            <div className="flex-1 h-2.5 bg-gray-200 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${phaseColors.active}`} style={{ width: "100%" }} />
            </div>
            <span className="w-12 shrink-0 text-right text-xs font-semibold text-gray-700 tabular-nums">{topTotal.toFixed(2)}</span>
          </div>
          <div className="flex items-center gap-2" data-testid="macro-cycle-gap-second">
            {/* `final_scores` 가 오면 2위 국면 이름을 그대로 적고, 없으면 이름을 **지어내지 않는다**
                — 점수만 알고 이름은 모르는 상태를 감추는 것이 더 나쁘다. */}
            <span className="w-24 shrink-0 text-xs text-gray-500 truncate">
              {secondName ? `2위 ${secondName}` : "2위 (이름 없음)"}
            </span>
            <div className="flex-1 h-2.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full bg-gray-400 ${atCap ? "opacity-60" : ""}`}
                style={{ width: `${secondPct ?? 0}%` }}
              />
            </div>
            <span className="w-12 shrink-0 text-right text-xs font-medium text-gray-500 tabular-nums">
              {secondTotal !== null ? `${atCap ? "≤" : ""}${secondTotal.toFixed(2)}` : "—"}
            </span>
          </div>
        </div>
      )}

      {note && (
        <p data-testid="macro-cycle-gap-note" className="text-xs text-gray-700 mb-1">
          {note.split("**").map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : part))}
        </p>
      )}
      <p data-testid="macro-cycle-gap-caveat" className="text-[11px] text-gray-400">
        1위와 2위가 벌어진 정도입니다 — 맞고 틀림과는 무관합니다. (내부값 {conf})
      </p>
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
  const { phase, phase_label, phase_desc, confidence, scores, leader_sectors, final_scores } = cycle

  const phaseColors = PHASE_COLORS[phase] || PHASE_COLORS.recovery

  // 지표 카드 막대의 기준자 — 다섯 기여 중 최대값. 하드코딩하지 않고 그날 값에서 뽑는다.
  const contribValues = Object.values(scores ?? {})
    .map((item) => toNum(item?.score))
    .filter((v): v is number => v !== null && v > 0)
  const maxContribution = contribValues.length ? Math.max(...contribValues) : null

  return (
    <section data-testid="macro-section-cycle">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">경기 사이클</h2>
      <div className="rounded-lg border bg-white p-5 shadow-sm space-y-5">
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

            {/* 보존 목록 §1 — 국면 4칸 가로 배열(회복기→확장기→과열기→수축기), 현재 진한 색 + 확대.
                체제 4칸 스트립과 같은 자리·같은 마크업이다(파일 상단 주석 참고) */}
            <div className="grid grid-cols-4 gap-1.5 mb-3">
              {PHASES.map((p) => (
                <PhaseCard key={p} phase={p} isActive={phase === p} score={toNum(final_scores?.[p])} />
              ))}
            </div>

            {phase_desc && <p className="text-xs text-gray-600 text-center">{phase_desc}</p>}
          </div>

          {/* 투자 체제 (보존 목록 §6 — 공포탐욕·버핏지수·VIX 상세 포함) */}
          <RegimeDetail regime={regime} />
        </div>

        {/* 보존 목록 §5 — 괴리 설명 */}
        <DivergenceNote phase={phase} regime={regime?.regime} />

        {/* 1·2위 점수차 (원본의 「신뢰도 N%」 막대를 대체) */}
        <PhaseGapBlock confidence={confidence} scores={scores} phase={phase} phaseLabel={phase_label} finalScores={final_scores} />

        {/* 보존 목록 §4 — 판단 근거 지표 카드 5종 */}
        {scores && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {Object.entries(scores).map(([key, item]: [string, CycleScoreItem]) => (
              <IndicatorCard
                key={key}
                testId={`macro-cycle-indicator-${key}`}
                label={SCORE_LABELS[key] || key}
                signal={item?.signal}
                score={toNum(item?.score)}
                maxScore={maxContribution}
                phaseLabel={phase_label}
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
