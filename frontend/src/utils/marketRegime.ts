/**
 * cycle315 (2026-09-19): 시장 레짐 표시 상수 — 단일 진실원.
 *
 * 값의 출처는 **우리 macro 컨테이너**(`macro/macro_lite/`)다. 외부 dkstock.cloud 는
 * 2026-08-18 철거됐고, 되살릴 계획이 없다. env 이름(`DKSTOCK_REGIME_ENABLED`)과 DB 키만
 * 옛 이름을 물려받았을 뿐 데이터는 우리 것이다.
 *
 * 컴포넌트 파일(`components/MarketRegimeCard.tsx`)이 아니라 여기 두는 이유 = 상수를
 * 컴포넌트와 같은 파일에서 export 하면 vite fast-refresh 가 깨진다(`utils/contentWidth.ts`
 * 선례와 같은 처리).
 */

/**
 * 실재 레짐 4종 — `macro/macro_lite/regime.py::REGIME_MATRIX` 가 낼 수 있는 값의 전부다.
 * 종전 화면이 갖고 있던 `neutral`·`aggressive` 는 어느 경로에서도 나오지 않는 죽은 키였고,
 * 그래서 실제로 오는 accumulation·selective·cautious 가 전부 "비활성" 폴백으로 떨어졌다.
 *
 * 색은 `/macro` 화면(`macro/components/MacroCycleSection.tsx::REGIME_COLORS`) 계열을 따르되
 * accumulation 만 emerald → sky 로 바꿨다 — `index.css` 의 Tailwind v4 별칭이 emerald 를
 * blue 로 재정의해서 emerald(accumulation)와 blue(selective)의 **실제 hex 가 같아진다**.
 */
export const REGIME_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  accumulation: { bg: 'bg-sky-100', text: 'text-sky-800', label: '적극 매수' },
  selective: { bg: 'bg-blue-100', text: 'text-blue-800', label: '선별 매수' },
  cautious: { bg: 'bg-amber-100', text: 'text-amber-800', label: '신중' },
  defensive: { bg: 'bg-red-100', text: 'text-red-800', label: '방어' },
}

/** `macro/macro_lite/cycle.py` 4국면. 영문 원문이 화면에 그대로 새는 것을 막는다. */
export const CYCLE_LABEL: Record<string, string> = {
  recovery: '회복기',
  expansion: '확장기',
  overheating: '과열기',
  contraction: '수축기',
}

/**
 * 자금 사다리 — `macro/macro_lite/regime.py::REGIME_PARAMS` 의 cash_min 정본값(퍼센트 정수).
 * 자금 사용률은 백엔드 자동 조정식 `clamp((100 − cash_min) / 100, 0.0, 1.0)` 과 같다.
 */
export const REGIME_CASH_LADDER: Array<{ regime: string; cashMin: number }> = [
  { regime: 'accumulation', cashMin: 25 },
  { regime: 'selective', cashMin: 35 },
  { regime: 'cautious', cashMin: 50 },
  { regime: 'defensive', cashMin: 75 },
]

/**
 * 버핏지수 단위 계약 = **비율**(시총 / GDP, 예: 2.626). 화면은 ×100 해서 퍼센트로 쓴다.
 *
 * 🔴 값 크기로 단위를 추측해 조용히 나누지 않는다 — 계약을 어긴 값은 변환해서 그럴듯하게
 *    만들지 말고 드러낸다(시총이 GDP 의 10배가 되는 세계는 없으므로 이 상한을 넘는 값은
 *    단위가 어긋난 것이고, 그 사실이 화면에 보여야 고칠 수 있다).
 */
export const BUFFETT_RATIO_MAX = 10

export function formatBuffettRatio(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  if (v > BUFFETT_RATIO_MAX) return `${v} ⚠단위`
  return `${Math.round(v * 100)}%`
}

/** cash_min(%) → 자금 사용률(%). 백엔드 자동 조정식과 같은 계산이다. */
export function usagePctFromCashMin(cashMin: number): number {
  return Math.min(100, Math.max(0, 100 - cashMin))
}
