/**
 * 테스트용 응답 팩토리.
 *
 * 백엔드 ApiResponse<T> 구조 = { success, data, message }.
 * 모든 MSW 핸들러와 단위 테스트가 일관된 모양을 쓰도록 wrap()을 거친다.
 */

import type {
  LlmEvaluation,
  LlmEvaluationSummary,
} from "../types/llm-evaluation";
import type { TradePair } from "../types/trading";

export function wrap<T>(data: T, message = "") {
  return { success: true, data, message };
}

export function failed(message = "error") {
  return { success: false, data: null, message };
}

export function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    ticker: "005930",
    ticker_name: "삼성전자",
    quantity: 10,
    buy_price: 70000,
    current_price: 72000,
    eval_amount: 720000,
    profit_loss: 20000,
    profit_rate: 2.86,
    strategy: "momentum",
    ...overrides,
  };
}

export function makeStrategy(overrides: Partial<Strategy> = {}): Strategy {
  return {
    strategy_id: "momentum",
    enabled: true,
    weight: 0.5,
    params: {},
    invested_amount: 0,
    min_weight: 0,
    total_investment: 5000000,
    ...overrides,
  };
}

export function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    id: 1,
    timestamp: "2026-05-08T15:00:00+09:00",
    ticker: "005930",
    ticker_name: "삼성전자",
    trade_type: "BUY",
    price: 70000,
    quantity: 10,
    profit_loss: 0,
    status: "COMPLETED",
    strategy: "momentum",
    order_no: "0000123456",
    ...overrides,
  };
}

export interface Position {
  ticker: string;
  ticker_name: string;
  quantity: number;
  buy_price: number;
  current_price: number;
  eval_amount: number;
  profit_loss: number;
  profit_rate: number;
  strategy: string;
}

export interface Strategy {
  strategy_id: string;
  enabled: boolean;
  weight: number;
  params: Record<string, unknown>;
  invested_amount: number;
  min_weight: number;
  total_investment: number;
}

export interface Trade {
  id: number;
  timestamp: string;
  ticker: string;
  ticker_name: string;
  trade_type: "BUY" | "SELL";
  price: number;
  quantity: number;
  profit_loss: number;
  status: "PENDING" | "COMPLETED" | "PARTIAL" | "CANCELLED";
  strategy: string;
  order_no: string;
}

// ---------------------------------------------------------------------------
// cycle276 — AI 매수평가(LLM) 기록 팩토리.
//
// 실제 라우트 응답(`_workspace/red/cycle276_order_time_llm_eval_spec.md` §5.2)의
// **모든 키**를 담는다. 목이 계약의 일부만 담으면 "의도한 계약"만 검증되고 실제 응답은
// 검증되지 않는다(cycle266 §C-3 — `change_rate` 문자열이 3개월간 초록이던 그 결함).
// ⚠️ 계좌번호는 마스킹된 `account_no_masked` 하나뿐 — 원문 키를 되살리지 말 것.
// ---------------------------------------------------------------------------

export function makeLlmEvaluationSummary(
  overrides: Partial<LlmEvaluationSummary> = {},
): LlmEvaluationSummary {
  return {
    order_no: "0000123456",
    trade_date: "2026-09-11",
    ticker: "005930",
    strategy_id: "volatility_breakout",
    result: "ok",
    reason: null,
    score: 62,
    min_score: 70,
    would_block: true,
    evaluated_at: "2026-09-11T09:01:34.512000+09:00",
    ...overrides,
  };
}

export function makeLlmEvaluation(
  overrides: Partial<LlmEvaluation> = {},
): LlmEvaluation {
  return {
    ...makeLlmEvaluationSummary(),
    account_no_masked: "5011****",
    ticker_name: "삼성전자",
    account_product: "01",
    created_at: "2026-09-11T09:01:34.612000+09:00",
    eval_kind: "order",
    mode: "shadow",
    rationale: "직전 고점 돌파 직후 거래량이 실렸으나 지수 약세가 상방을 제한한다.",
    key_risks: ["지수 약세", "돌파 폭 과소"],
    invalidations: ["목표가 하회 마감", "거래량 급감"],
    model: "gpt-5.6-luna",
    tokens_in: 3120,
    tokens_out: 210,
    cost_usd: 0.00438,
    latency_ms: 3120,
    verdict_lag_ms: 3480,
    eval_to_order_lag_ms: 3480,
    order_kst: "2026-09-11T09:01:31.032000+09:00",
    order_price_won: 71800,
    ordered_qty: 3,
    order_notional_won: 215400,
    order_division: "MARKET",
    order_path: "market",
    exchange: "KRX",
    board: "main",
    current_price_won: 71800,
    signal_matched: true,
    signal_price_won: 71800,
    signal_time_local: "09:01:31",
    strategy_board: "main",
    target_won: 71650,
    k: 0.5,
    breakout_excess_bp: 20.9,
    post_order_drift_bp: -13.9,
    drift_price_won: 71700,
    tick_age_s: 1.2,
    budget_total_won: 247949,
    budget_remaining_after_won: 32549,
    open_positions_n: 1,
    prompt_version: "a1b2c3d4e5f6",
    feature_version: "0f1e2d3c4b5a",
    bars_count: 59,
    input_payload: { payload: { ticker: "005930" }, tech: { rsi14: 58.2 }, bars30: [] },
    raw_response: { content: '{"score":62,"rationale":"…"}' },
    ...overrides,
  };
}

export function makeTradePair(overrides: Partial<TradePair> = {}): TradePair {
  return {
    buy_date: "2026-09-11",
    buy_time: "09:01:33",
    sell_date: "2026-09-11",
    sell_time: "14:22:10",
    ticker: "005930",
    ticker_name: "삼성전자",
    buy_price: 71800,
    buy_qty: 3,
    sell_price: 72500,
    sell_qty: 3,
    profit_loss: 2100,
    profit_rate: 0.97,
    status: "closed",
    strategy: "volatility_breakout",
    buy_order_nos: ["0000123456"],
    sell_order_nos: ["0000987654"],
    pair_key: "volatility_breakout:005930:0000123456",
    ...overrides,
  };
}
