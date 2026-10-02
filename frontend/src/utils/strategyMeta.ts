// 전략 표시명 중앙 정본 (cycle395, 2026-10-02 사용자 요청).
//
// 배경: 화면마다 전략명이 제각각이었다 — 백엔드 API `name` 원문을 그대로 쓰는 화면
// (Settings/Strategies/StrategyParamsEditor), 컴포넌트마다 다른 로컬 `STRATEGY_NAMES`
// 사본(TradePnLGrid/TradeHistoryGrid/BalanceTable, 서로 다른 표기 — "변동성돌파" vs
// "변동성 돌파", "20일 신고가 스윙" vs "돈키언 추세 스윙"), id 원문을 그대로 찍는 화면
// (BacktestComparisonCard, LlmEvaluationModal) 이 공존했다.
//
// 표시명 정본(사용자 09-27 확정 3개 + 기존 4개, 10-02 전수 통일 + cycle403 etf_trend 추가)
// — 이 표가 유일한 출처다. 8 전략은 **백엔드 API 가 주는 `name` 보다 이 표가 항상 우선**
// 한다(백엔드 응답마다 이름이 다르다 — 예: params-schema 는 momentum 을 "상한가 모멘텀"으로,
// 다른 경로는 "모멘텀"으로 부른다). 화면에 전략 id 를 사람에게 보일 일이 있으면 반드시
// `strategyLabel(id, apiName?)` 을 거친다 — id 리터럴이나 지역 사본을 새로 만들지 않는다.
export const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  momentum: '모멘텀',
  volatility_breakout: '변동성 돌파',
  long_tail_volatility: '롱테일 변동성',
  donchian_swing: '돈키언 추세 스윙',
  bull_flag_breakout: '추세 눌림목 돌파',
  vcp_breakout: 'VCP 변동성 수축',
  kojiro: '고지로 대순환',
  // cycle403 (2026-10-03) — ETF 추세 전략. L1 = "ETF 추세"(섀도 모드로 시작, 비중 0).
  etf_trend: 'ETF 추세',
}

/**
 * 전략 id → 화면 표시명.
 *
 * 위 8 전략은 `apiName` 과 무관하게 이 표의 값을 우선한다. 표에 없는(향후 추가될) 전략
 * id 는 `apiName` 이 있으면 그것을, 없으면 id 원문을 그대로 돌려준다 — "총합" 같은 비전략
 * 집계 키(`total` 등)는 이 함수로 보내지 않고 호출부가 기존 표시를 유지한다.
 */
export function strategyLabel(id: string, apiName?: string | null): string {
  return STRATEGY_DISPLAY_NAMES[id] ?? apiName ?? id
}
