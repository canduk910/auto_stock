/**
 * cycle276 — AI 매수평가(LLM) 기록 타입.
 *
 * 정본 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §5.2 / §10.1.
 *
 * ⚠️ **계좌번호 원문 필드를 만들지 않는다.** 라우트가 `account_no_masked`(앞 4자리 + `****`)
 * 하나만 내보내고(C39/C40), 이 표면은 리포터 키(GET 전 경로 통과, cycle249)로도 읽힌다.
 * 원문 키를 타입에 추가하는 순간 구현이 그것을 채우려 들고 마스킹 계약이 무너진다.
 */

export interface LlmEvaluationSummary {
  order_no: string
  trade_date: string
  ticker: string
  strategy_id: string
  result: 'ok' | 'failed'
  reason: string | null
  score: number | null
  min_score: number
  would_block: boolean | null
  evaluated_at: string | null
}

export interface LlmEvaluation extends LlmEvaluationSummary {
  account_no_masked: string // ⚠️ 원문 계좌번호 필드는 만들지 않는다
  // cycle276 Green — 명세 §10.1 의 초안에는 없었으나 라우트 `_detail()` 사영이 실제로
  // 내보내는 3키다(`src/routes/llm_evaluations.py`). 타입이 실제 응답보다 좁으면 화면이
  // 쓸 수 있는 값을 못 보고, 목이 그 3키를 빼면 "계약만 담고 실제는 안 담는" 목이 된다
  // (cycle266 §C-3 — `change_rate` 문자열이 3개월간 초록이던 경로).
  ticker_name: string | null
  account_product: string | null
  created_at: string | null
  eval_kind: string
  mode: string
  rationale: string | null
  key_risks: unknown
  invalidations: unknown
  model: string | null
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  latency_ms: number | null
  verdict_lag_ms: number | null
  eval_to_order_lag_ms: number | null
  order_kst: string
  order_price_won: number
  ordered_qty: number
  order_notional_won: number
  order_division: string
  order_path: string
  exchange: string | null
  board: string
  current_price_won: number | null
  signal_matched: boolean
  signal_price_won: number | null
  /**
   * 전략이 신호에 찍은 시각 문자열(`HH:MM:SS`). **KST 를 보장하지 않는다** —
   * 원천이 6전략 `datetime.now()`(tz 없음)·kojiro `datetime.now(KST)` 이고,
   * EC2 컨테이너의 `TZ=Asia/Seoul` 전제에서만 KST 와 같다. 그래서 이름이 `_local` 이다.
   */
  signal_time_local: string | null
  strategy_board: string | null
  target_won: number | null
  k: number | null
  breakout_excess_bp: number | null
  post_order_drift_bp: number | null
  drift_price_won: number | null
  tick_age_s: number | null
  budget_total_won: number | null
  budget_remaining_after_won: number | null
  open_positions_n: number | null
  prompt_version: string | null
  feature_version: string | null
  bars_count: number | null
  input_payload: unknown
  raw_response: unknown
}

export type LlmEvaluationSummaryMap = Record<string, LlmEvaluationSummary>
