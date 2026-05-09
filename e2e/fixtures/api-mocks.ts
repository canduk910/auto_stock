/**
 * Playwright 용 백엔드 API 모킹 헬퍼.
 *
 * 각 시나리오 시작 시 `installApiMocks(page)` 를 호출해 19+ 엔드포인트의
 * 기본 응답을 등록한다. 시나리오별 오버라이드는 추가 page.route 로.
 */

import type { Page } from "@playwright/test";

type AnyJson = Record<string, unknown>;

function envelope<T>(data: T, message = "") {
  return { success: true, data, message };
}

const defaultStatus = {
  running: false,
  is_running: false,  // backwards-compat
  env: "vts",
  board: "main",
  phase: "idle",
  positions: 0,
  pending_buys: 0,
  position_tickers: [] as string[],
  positions_detail: {} as AnyJson,
  orders: {
    pending_buy_orders: {} as AnyJson,
    pending_buy_tickers: [] as string[],
    pending_cancels: [] as string[],
    fills: {} as AnyJson,
  },
  scan: {
    candidates: [] as unknown[],
    last_scan_time: "",
    targets: {} as AnyJson,
    scan_stats: null,
  },
  strategy: "all" as string,
  strategies: {
    momentum: {
      name: "상한가 모멘텀",
      enabled: true,
      weight: 0.5,
      params: { position_ratio: 0.25, max_positions: 4 },
      total_investment: 50_000_000,
      invested_amount: 0,
      min_weight: 0,
      positions: 0,
      pending_buys: 0,
      position_tickers: [],
      positions_detail: {},
      pending_buy_tickers: [],
      buy_signals: [],
      buy_disabled: false,
      daily_realized_pnl: 0,
      scanned_tickers: [],
      scanned_count: 0,
      targets: {},
      scan_stats: null,
      invested_amount: 0,
      min_weight: 0,
    },
  },
};

export interface MockOptions {
  isRunning?: boolean;
  trades?: AnyJson[];
  recommendations?: AnyJson[];
  logReports?: AnyJson[];
}

export async function installApiMocks(page: Page, opts: MockOptions = {}) {
  const isRunning = opts.isRunning ?? false;
  const status = { ...defaultStatus, running: isRunning, is_running: isRunning };

  // /api/trading/status 는 ControlPanel/EnvBanner 가 5초 폴링
  await page.route("**/api/trading/status*", (route) =>
    route.fulfill({ json: envelope(status) }),
  );
  await page.route("**/api/trading/positions", (route) =>
    route.fulfill({
      json: envelope({ position_tickers: [], positions_detail: {} }),
    }),
  );
  await page.route("**/api/trading/orders", (route) =>
    route.fulfill({ json: envelope({}) }),
  );
  await page.route("**/api/trading/start", (route) => {
    status.running = true;
    status.is_running = true;
    return route.fulfill({ json: envelope(null, "매매 시작") });
  });
  await page.route("**/api/trading/stop", (route) => {
    status.running = false;
    status.is_running = false;
    return route.fulfill({ json: envelope(null, "매매 중지") });
  });
  await page.route("**/api/trading/restart", (route) =>
    route.fulfill({ json: envelope(null, "매매 재기동") }),
  );

  await page.route("**/api/strategies", (route) =>
    route.fulfill({ json: envelope(status.strategies) }),
  );
  await page.route("**/api/strategies/weights", (route) =>
    route.fulfill({ json: envelope(status.strategies, "비중 업데이트 완료") }),
  );
  await page.route("**/api/strategies/*/params", (route) =>
    route.fulfill({ json: envelope(status.strategies, "파라미터 업데이트 완료") }),
  );
  await page.route("**/api/strategies/system/auto-start", (route) =>
    route.fulfill({ json: envelope({ auto_start: false }) }),
  );

  await page.route("**/api/balance", (route) =>
    route.fulfill({
      json: envelope({
        holdings: [],
        summary: {
          deposit: 10_000_000,
          stock_eval_amount: 0,
          total_eval_amount: 10_000_000,
          net_asset: 10_000_000,
          purchase_total: 0,
          eval_total: 0,
          profit_loss_total: 0,
        },
      }),
    }),
  );

  await page.route("**/api/performance/summary*", (route) =>
    route.fulfill({
      json: envelope({
        total_days: 0,
        total_profit_rate: 0,
        avg_daily_profit_rate: 0,
        latest_asset: 10_000_000,
        strategy: "total",
      }),
    }),
  );
  await page.route("**/api/performance/daily*", (route) =>
    route.fulfill({ json: envelope([]) }),
  );

  await page.route("**/api/history*", (route) =>
    route.fulfill({
      json: envelope({
        trades: opts.trades ?? [],
        page: 1,
        size: 20,
        total: opts.trades?.length ?? 0,
        total_pages: 1,
      }),
    }),
  );
  await page.route("**/api/history/pnl*", (route) =>
    route.fulfill({
      json: envelope({
        pairs: [],
        page: 1,
        size: 50,
        total: 0,
        total_pages: 0,
      }),
    }),
  );

  await page.route("**/api/recommendations", (route) =>
    route.fulfill({ json: envelope(opts.recommendations ?? []) }),
  );
  await page.route("**/api/recommendations/**", (route) =>
    route.fulfill({ json: envelope(null, "OK") }),
  );

  await page.route("**/api/log-reports*", (route) =>
    route.fulfill({ json: envelope(opts.logReports ?? []) }),
  );

  await page.route("**/api/logs*", (route) =>
    route.fulfill({ json: envelope([]) }),
  );

  await page.route("**/api/system/**", (route) =>
    route.fulfill({ json: envelope({}) }),
  );
}
