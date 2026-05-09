/**
 * 테스트용 응답 팩토리.
 *
 * 백엔드 ApiResponse<T> 구조 = { success, data, message }.
 * 모든 MSW 핸들러와 단위 테스트가 일관된 모양을 쓰도록 wrap()을 거친다.
 */

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
