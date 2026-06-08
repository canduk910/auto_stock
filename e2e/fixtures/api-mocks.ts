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

  // 사이클 64 가격 필터 (2026-06-06) — Settings 진입 시 PriceFilterCard 마운트
  // 와일드카드 `**/api/system/**` *전* 구체 라우트 등록 의무 (envelope({}) 가 min_price 미정의 → React controlled input 결함)
  await page.route("**/api/system/price-filter", (route) =>
    route.fulfill({ json: envelope({ min_price: 0, max_price: 0 }) }),
  );

  // 사이클 65 거래대금 동행 필터 (2026-06-06) — TradeAmountFilterCard 마운트
  await page.route("**/api/system/trade-amount-filter", (route) =>
    route.fulfill({ json: envelope({ min_amount: 0 }) }),
  );

  // 사이클 75 카드 #19' (2026-06-08) — 7 endpoint group 누락 → settings.spec.ts timeout 차단.
  // 사이클 65 hotfix #2 패턴 답습: 구체 라우트를 와일드카드 `**/api/system/**` 보다 앞에 등록.

  // CashUsageRatioCard — /api/strategies/system/cash-usage-ratio
  await page.route("**/api/strategies/system/cash-usage-ratio", (route) =>
    route.fulfill({ json: envelope({ ratio: 1.0 }) }),
  );

  // IntegrationToggleCard 4 토글
  await page.route("**/api/integrations/dkstock-regime", (route) =>
    route.fulfill({ json: envelope({ enabled: false, source: "env" }) }),
  );
  await page.route("**/api/integrations/kis-mcp", (route) =>
    route.fulfill({ json: envelope({ enabled: false, source: "env" }) }),
  );
  await page.route("**/api/integrations/auto-regime-adjust", (route) =>
    route.fulfill({ json: envelope({ enabled: true, source: "db" }) }),
  );
  await page.route("**/api/integrations/auto-apply", (route) =>
    route.fulfill({ json: envelope({ enabled: false, source: "db" }) }),
  );

  // BuyBlockSection — /api/integrations/buy-block (GET) + /api/integrations/buy-block/thresholds
  await page.route("**/api/integrations/buy-block/thresholds", (route) =>
    route.fulfill({
      json: envelope({ vix: 25, fg_high: 85, fg_low: 15, defensive: true }),
    }),
  );
  await page.route("**/api/integrations/buy-block", (route) =>
    route.fulfill({
      json: envelope({
        mode: "HARD",
        blocked: false,
        reasons: [],
        soft_multiplier: 0.5,
        thresholds: {
          vix_threshold: 25,
          fg_high_threshold: 85,
          fg_low_threshold: 15,
          defensive_enabled: true,
        },
      }),
    }),
  );

  // KisQuoteAccountsCard — /api/integrations/quote-accounts (와일드카드 suffix)
  await page.route("**/api/integrations/quote-accounts*", (route) =>
    route.fulfill({ json: envelope([]) }),
  );

  // 사이클 77 hotfix — Dashboard 영역 endpoint 추가 (settings.spec.ts 진입 시 react-router prefetch
  // 또는 lazy import 트리거로 MarketRegimeCard / ScanMonitor 컴포넌트 useQuery 발화. 사이클 75 G-AST1
  // 가드 영역 (Settings 한정) 한계 노출 → 사이클 77 = Dashboard 영역 매핑 확장)
  // 사이클 77 hotfix #2 — MarketRegimeCurrent interface 정확 매칭 (frontend/src/types/market_regime.ts)
  // 5 필수 필드 (buy_blocked / block_reason / auto_regime_adjust / cash_usage_ratio / enabled) 추가
  await page.route("**/api/market-regime/current", (route) =>
    route.fulfill({
      json: envelope({
        regime: "neutral",
        regime_desc: "중립",
        cycle_phase: null,
        vix: 18.0,
        fear_greed_score: 50,
        buffett_ratio: 100.0,
        cash_min: 30,
        buy_blocked: false,
        block_reason: null,
        auto_regime_adjust: true,
        cash_usage_ratio: 1.0,
        enabled: false,
      }),
    }),
  );
  await page.route("**/api/market-regime/history*", (route) =>
    route.fulfill({ json: envelope([]) }),
  );
  await page.route("**/api/market-regime/auto-adjust", (route) =>
    route.fulfill({ json: envelope({ enabled: true }) }),
  );
  await page.route("**/api/realtime/subscriptions", (route) =>
    route.fulfill({ json: envelope({ sessions: [], total_count: 0 }) }),
  );

  await page.route("**/api/system/**", (route) =>
    route.fulfill({ json: envelope({}) }),
  );
}
