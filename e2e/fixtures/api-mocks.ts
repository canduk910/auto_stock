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
      params: {
        position_ratio: 0.25,
        max_positions: 4,
        // 사이클 104 — Strategies.tsx 4 임계 가시화 mock (strategies.spec.ts H-ST2/M-ST5 영속)
        stop_loss_rate: -7.5,
        daily_loss_limit: -5.0,
        trailing_stop_rate: -2.0,
      },
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
  // 사이클 F — TE(트레이딩 예지치)/RR(손익비) 성과 mock override (tester-cycleF 인계: e2e 표본 게이트 3분기 커버리지 갭)
  teMetrics?: AnyJson[];
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
  // 사이클 F — TE(트레이딩 예지치)/RR(손익비) 성과 (관찰 전용, F-FE6). 구체 라우트 —
  // 광범위 wildcard 부재 영역이라 LIFO 영향 없음(사이클 80 hotfix #3 패턴 참고).
  // opts.teMetrics 로 시나리오별(표본 게이트 3분기) override 가능.
  await page.route("**/api/strategies/te*", (route) =>
    route.fulfill({ json: envelope(opts.teMetrics ?? []) }),
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

  // 사이클 104 hotfix — Playwright glob `**/api/logs*` 는 `http://localhost:3000/src/api/logs.ts`
  // (Vite 모듈 요청, resourceType='script') 도 intercept → JSON 반환 → MIME 타입 불일치 →
  // `RealtimeHealth.tsx` 동적 import 실패 → 빈 화면. resourceType 가드로 script 요청은 통과.
  await page.route("**/api/logs*", (route) => {
    if (route.request().resourceType() === "script") return route.continue();
    return route.fulfill({ json: envelope([]) });
  });

  // 사이클 80 hotfix #3 — Playwright route 매칭 규칙은 **LIFO** ("latest registered route wins").
  // 따라서 wildcard `**/api/system/**` 를 다른 system/ 라우트 *전* 에 먼저 등록 = fallback 역할.
  // 사이클 65 hotfix #2 주석 의도 ("구체 라우트를 와일드카드 보다 앞에 등록") 는 FIFO 가정이었으나,
  // 실제 Playwright 는 LIFO → 구체 라우트가 *나중* 등록되어야 wildcard 보다 우선 매칭. 영역 재배치.
  await page.route("**/api/system/**", (route) =>
    route.fulfill({ json: envelope({}) }),
  );

  // 사이클 64 가격 필터 (2026-06-06) — Settings 진입 시 PriceFilterCard 마운트
  // 와일드카드 *후* 구체 라우트 등록 (LIFO 우선 매칭) — envelope({}) min_price 미정의 → React controlled input throw 차단
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
        // 사이클 D-FE (2026-07-31) — 레짐 가드 무력 배너 타입 정합.
        // 기존 e2e 시나리오는 guard_inert 배너를 검증하지 않으므로 false 고정(미렌더).
        data_available: false,
        guard_inert: false,
      }),
    }),
  );

  // KisQuoteAccountsCard — /api/integrations/quote-accounts (와일드카드 suffix)
  await page.route("**/api/integrations/quote-accounts*", (route) =>
    route.fulfill({ json: envelope([]) }),
  );

  // 사이클 112 (2026-06-12) — KrxOpenApiCard /api/integrations/krx-open-api GET/PUT
  // LIFO 정합 의무 (사이클 80 hotfix #3 영속) — 구체 라우트는 와일드카드 *후* 등록.
  // 본 라우트는 wildcard 와 무관 (단일 구체 path) — 등록 순서만 답습.
  await page.route("**/api/integrations/krx-open-api", (route) =>
    route.fulfill({
      json: envelope({
        enabled: false,
        base_url: "https://data-dbg.krx.co.kr/svc/apis",
        key_masked: "****",
      }),
    }),
  );

  // 사이클 77 hotfix — Dashboard 영역 endpoint 추가 (settings.spec.ts 진입 시 react-router prefetch
  // 또는 lazy import 로 MarketRegimeCard / ScanMonitor (Dashboard 컴포넌트) useQuery 발화 →
  // /api/market-regime/current + /api/realtime/subscriptions ECONNREFUSED.
  // 사이클 75 G-AST1~AST3 (Settings 한정) 영역 한계 노출 → 사이클 77 = Dashboard 영역 확장.
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

  // 사이클 186 (2026-06-29) — 장운영상태 (VI/거래정지/종목상태 + 서킷브레이커 휴리스틱).
  // `**/api/realtime/**` 와일드카드 부재 → 단일 구체 path (LIFO 영향 없음). 0건 정상 기본.
  await page.route("**/api/realtime/market-operation", (route) =>
    route.fulfill({
      json: envelope({
        vi_active_count: 0,
        halt_active_count: 0,
        last_event_count: 0,
        iscd_stat_active_count: 0,
        vi_active_sample: [],
        halt_active_sample: [],
        circuit_breaker: {
          suspected: false,
          reasons: [],
          halt_ratio: 0,
          halted: 0,
          observed: 0,
          representative_mkop_cls_code: "",
          halt_reasons_sample: [],
        },
        details: [],
      }),
    }),
  );

  // 사이클 80 hotfix #3 — 함수 끝 wildcard `**/api/system/**` 제거 (LIFO 라 가장 우선 매칭되어
  // L196 price-filter / L201 trade-amount-filter 구체 라우트 무효화 → PriceFilterCard 가 envelope({}) 응답
  // 받아 min_price undefined → React controlled input throw → Error Boundary 없음 → 전체 페이지 unmount).
  // Wildcard fallback 은 L190 (구체 라우트 *전* 등록) 만 유지 — LIFO 라 fallback 역할 정확.

  // 사이클 85 (2026-06-09) — StockMaster 페이지 5 endpoint.
  // 사이클 124 Q1=A / Q3=A — stats 8 키 + 일봉 라우트 신규.
  // Playwright route 매칭 = LIFO ("latest registered route wins").
  // wildcard 를 *먼저* 등록 (fallback 역할) → 구체 라우트를 *후* 등록 (LIFO 우선 매칭).
  // 사이클 80 hotfix #3 LIFO 정합 패턴 100% 답습.
  await page.route("**/api/stock-master/**", (route) =>
    route.fulfill({ json: envelope({}) }),
  );

  // 구체 라우트 — wildcard 후 등록 (LIFO 라 우선 매칭).
  // 사이클 124 Q3=A: stats 4 → 8 키.
  await page.route("**/api/stock-master/stats", (route) =>
    route.fulfill({
      json: envelope({
        count_all: 29,
        bfdy_clpr_present: 27,
        nxt_tradable_count: 12,
        top_10_recent: [],
        with_hts_avls: 2800,
        with_acml_tr_pbmn: 2700,
        total_daily_rows: 84000,
        last_daily_load_at: "2026-06-13T20:00:00+09:00",
      }),
    }),
  );
  // 사이클 128 — list 응답 schema {items, total, limit, offset} envelope.
  // 사이클 80 hotfix #3 Playwright LIFO 정합 (구체 라우트 후 등록).
  await page.route("**/api/stock-master/list*", (route) =>
    route.fulfill({
      json: envelope({ items: [], total: 0, limit: 100, offset: 0 }),
    }),
  );
  await page.route("**/api/stock-master/scan-pool/summary", (route) =>
    route.fulfill({ json: envelope({ eager_refresh_today: 0 }) }),
  );
  // 사이클 169 — migration 036 (사이클 150) 신 스키마 (seq/raw). seq0 최신본 / seq1 직전본.
  await page.route("**/api/stock-master/*/history*", (route) =>
    route.fulfill({
      json: envelope([
        {
          ticker: "005930",
          seq: 0,
          change_type: "UPDATE",
          raw: { bfdy_clpr: 75000 },
          changed_at: "2026-06-09T09:05:00+09:00",
        },
        {
          ticker: "005930",
          seq: 1,
          change_type: "UPDATE",
          raw: { bfdy_clpr: 74000 },
          changed_at: "2026-06-09T09:05:00+09:00",
        },
      ]),
    }),
  );
  // 사이클 124 Q1=A — 일봉 라우트 (history 후 등록 = LIFO 우선, /*catch-all 보다 앞).
  await page.route("**/api/stock-master/*/daily*", (route) =>
    route.fulfill({
      json: envelope(
        Array.from({ length: 5 }, (_, i) => ({
          bas_dd: `202606${(13 - i).toString().padStart(2, "0")}`,
          open_price: 74000 + i * 100,
          high_price: 75500 + i * 100,
          low_price: 73500 + i * 100,
          close_price: 75000 + i * 100,
          volume: 1000000 + i * 50000,
          trade_value: 75000000000,
          change_rate: parseFloat((1.2 - i * 0.3).toFixed(2)),
        })),
      ),
    }),
  );
  await page.route("**/api/stock-master/*", (route) =>
    route.fulfill({
      json: envelope({
        ticker: "005930",
        name: "삼성전자",
        excg_dvsn_cd: "01",
        nxt_tradable: true,
        krx_halted: false,
        admin_item: false,
        refreshed_at: "2026-06-09T09:00:00+09:00",
        raw: {},
      }),
    }),
  );

  // 사이클 127 (2026-06-13) — POST 3 라우트 fire-and-forget (202 Accepted).
  // LIFO 정합: wildcard (**/api/stock-master/**) 보다 *후* 등록 → 우선 매칭.
  // 사이클 80 hotfix #3/#4 Playwright LIFO 정합 패턴 영속.
  await page.route("**/api/stock-master/refresh-universe", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 202,
        json: envelope({ status: "started", task_key: "universe" }),
      });
    }
    return route.continue();
  });

  await page.route("**/api/stock-master/basics/refresh", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 202,
        json: envelope({ status: "started", task_key: "basics" }),
      });
    }
    return route.continue();
  });

  await page.route("**/api/stock-master/daily/refresh", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 202,
        json: envelope({ status: "started", task_key: "daily" }),
      });
    }
    return route.continue();
  });

  // 사이클 129 — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 적재
  // LIFO 정합: wildcard (**/api/stock-master/**) 보다 *후* 등록 → 우선 매칭.
  await page.route("**/api/stock-master/master/refresh", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 202,
        json: envelope({ status: "started", task_key: "master" }),
      });
    }
    return route.continue();
  });

  // 사이클 127 — GET refresh-progress (5초 폴링, RefreshProgressBanner).
  // LIFO 정합: wildcard (**/api/stock-master/**) 보다 *후* 등록 → 우선 매칭.
  const idleProgress = {
    status: "idle" as const,
    total: 0,
    processed: 0,
    updated: 0,
    skipped: 0,
    failed: 0,
    started_at: null,
    finished_at: null,
    elapsed_ms: 0,
    error_message: null,
  };
  await page.route("**/api/stock-master/refresh-progress", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        json: envelope({
          universe: idleProgress,
          basics: idleProgress,
          daily: idleProgress,
          master: idleProgress,  // 사이클 129 — master 4번째 작업
        }),
      });
    }
    return route.continue();
  });

  // 사이클 103 (2026-06-11) — 실시간 건강 모니터링 + 전략 현황 endpoint mock.
  // Playwright route 매칭 = LIFO ("latest registered route wins").
  // 사이클 80 hotfix #3 LIFO 정합 패턴 영속: 구체 라우트를 *후* 등록 (LIFO 우선 매칭).

  // logs/search — 실시간 건강 4 카드 기반 endpoint
  await page.route("**/api/logs/search*", (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q") ?? "";
    const emptyLogs = envelope({ logs: [], total: 0, has_more: false });
    if (
      q.includes("[dispatch_drop_summary]") ||
      q.includes("[callback_exception]") ||
      q.includes("[stale_force_retry]") ||
      q.includes("[ws_auto_restart]")
    ) {
      return route.fulfill({ json: emptyLogs });
    }
    return route.fulfill({ json: emptyLogs });
  });

  // 사이클 104 — /api/strategies GET 플랫 형식은 L103 기존 핸들러(status.strategies)가 처리.
  // Strategies.tsx 는 data?.strategies ?? data fallback 으로 플랫 형식에서도 카드 렌더.
  // 사이클 103 내포 형식 핸들러 = 사이클 104 에서 삭제 (settings.spec.ts 회귀 차단).
}
