/**
 * Playwright 용 백엔드 API 모킹 헬퍼.
 *
 * 각 시나리오 시작 시 `installApiMocks(page)` 를 호출해 19+ 엔드포인트의
 * 기본 응답을 등록한다. 시나리오별 오버라이드는 추가 page.route 로.
 */

import type { Page } from "@playwright/test";
// cycle278 — 전략 파라미터 카탈로그 스키마 골든 픽스처(param_catalog.py 에서 기계 생성).
import { PARAM_SCHEMA_FIXTURE } from "./param-schema.fixture";
// cycle282 — 장운영상태(표 + 커서) 골든 픽스처(market_state.py 에서 기계 생성).
import { MARKET_STATE_FIXTURE } from "./market-state.fixture";

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
  // cycle276 — 체결 목의 각 항목은 실제 응답처럼 `order_no` 를 실어야 한다.
  // "AI 자문" 버튼의 키가 `order_no` 라, 목이 그것을 빼면 버튼이 없는 화면을 보고도
  // 시나리오가 초록으로 통과한다(cycle266 §C-3 계열 부정직).
  trades?: AnyJson[];
  // cycle276 — AI 매수평가 기록. **픽스처 입력**의 키 = 주문번호(테스트 편의), 값 =
  // `GET /api/llm-evaluations/{order_no}` 상세 응답 전문. 배치 요약 응답의 키는 실 라우트와
  // 같은 `날짜|주문번호` 복합 키로 만들어 나간다. 배치 요약은 이 맵에서
  // **있는 주문만** 요약으로 사영해 돌려준다(없는 주문은 키 자체가 없다 = 버튼 비활성).
  llmEvaluations?: Record<string, AnyJson>;
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

  // ⚠️ cycle276 Green 실측 — `**/api/history*` 글롭은 vite 모듈 요청
  //    `http://localhost:3000/src/api/history.ts` 까지 잡는다. JSON 을 돌려주면 MIME
  //    불일치로 `History.tsx` 동적 import 가 통째로 죽어 **빈 화면**이 된다(사이클 104 가
  //    `**/api/logs*` 에서 고친 것과 같은 계열). 거래기록 화면을 실브라우저로 밟는 spec 이
  //    cycle276 에서 처음 생겨 이 구멍이 드러났다 — 그 전에는 아무 spec 도 /history 를
  //    열지 않아 3개월 넘게 무증상이었다.
  //    판정은 **경로가 진짜 `/api/` 인지**로 한다(resourceType 보다 확실하다).
  const isRealApiCall = (url: string) => new URL(url).pathname.startsWith("/api/");
  await page.route("**/api/history*", (route) => {
    if (!isRealApiCall(route.request().url())) return route.continue();
    return route.fulfill({
      json: envelope({
        trades: opts.trades ?? [],
        page: 1,
        size: 20,
        total: opts.trades?.length ?? 0,
        total_pages: 1,
      }),
    });
  });
  await page.route("**/api/history/pnl*", (route) => {
    if (!isRealApiCall(route.request().url())) return route.continue();
    return route.fulfill({
      json: envelope({
        pairs: [],
        page: 1,
        size: 50,
        total: 0,
        total_pages: 0,
        summary: {
          realized_total_krw: 0,
          realized_rate_pct: 0,
          win_count: 0,
          loss_count: 0,
          even_count: 0,
          win_rate_pct: 0,
          closed_count: 0,
        },
      }),
    });
  });

  // cycle276 — AI 매수평가(LLM) 기록.
  // Playwright 는 **LIFO** 이므로 배치(fallback)를 **먼저**, 단건(구체)을 **나중에** 등록한다.
  // ⚠️ 사이클 104 hotfix 답습 — `**/api/llm-evaluations*` 글롭은 vite 모듈 요청
  //    `http://localhost:3000/src/api/llm-evaluations.ts` 까지 잡아 JSON 을 돌려주면
  //    MIME 불일치로 모듈 로드가 죽는다(실측 `resourceType()==='script'`).
  //    경로 가드(`/api/` 로 시작하는가)를 정본으로 두고 resourceType 은 보조로 남긴다.
  const llmEvaluations = opts.llmEvaluations ?? {};
  const summaryKeys = [
    "order_no",
    "trade_date",
    "ticker",
    "strategy_id",
    "result",
    "reason",
    "score",
    "min_score",
    "would_block",
    "evaluated_at",
  ];
  await page.route("**/api/llm-evaluations*", (route) => {
    if (!isRealApiCall(route.request().url())) return route.continue();
    if (route.request().resourceType() === "script") return route.continue();
    const url = new URL(route.request().url());
    const orderNos = (url.searchParams.get("order_nos") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const data: AnyJson = {};
    for (const no of orderNos) {
      const rec = llmEvaluations[no];
      if (!rec) continue;                       // 기록 없음 = 키 자체가 없다
      const summary: AnyJson = {};
      for (const k of summaryKeys) summary[k] = rec[k];
      // 응답 맵의 키는 **`날짜|주문번호` 복합 키**다(라우트 `summary_key()`).
      // 주문번호 단독 키는 같은 번호의 다른 날짜 평가를 지운다 — 실 라우트와 같은 형태로
      // 돌려주지 않으면 목이 "의도한 계약" 만 담고 실제 응답을 담지 않게 된다(cycle266).
      data[`${rec["trade_date"] ?? ""}|${no}`] = summary;
    }
    return route.fulfill({ json: envelope(data) });
  });
  await page.route("**/api/llm-evaluations/*", (route) => {
    if (!isRealApiCall(route.request().url())) return route.continue();
    if (route.request().resourceType() === "script") return route.continue();
    const orderNo = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    const rec = llmEvaluations[orderNo];
    if (!rec) {
      return route.fulfill({
        status: 404,
        json: { success: false, data: null, message: `order_no=${orderNo} 평가 기록 없음` },
      });
    }
    return route.fulfill({ json: envelope(rec) });
  });

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
  // 사이클 I (2026-08-03) — 지수ETF 레짐(관찰) 계산 토글 (5번째 토글)
  await page.route("**/api/integrations/etf-regime", (route) =>
    route.fulfill({
      json: envelope({ enabled: false, source: "db", env_value: false, db_value: false }),
    }),
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
  // 사이클 I (2026-08-03) — 지수ETF 레짐 4 필드 추가 (etf_kospi_stage/etf_kosdaq_stage/
  // etf_defensive/etf_enabled). buy_blocked 는 항상 false (레짐 매수 게이트 제거).
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
        etf_kospi_stage: null,
        etf_kosdaq_stage: null,
        etf_defensive: null,
        etf_enabled: false,
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

  // 사이클 I (2026-08-03) — 포트폴리오 리스크 관찰 카드 (PortfolioRiskCard, Phase 1,
  // 매수 배제 없음). Dashboard 마운트 시 발화 — 빈 스냅샷 기본.
  await page.route("**/api/portfolio/risk", (route) =>
    route.fulfill({
      json: envelope({
        total_notional_won: 0,
        total_open_risk_won: 0,
        open_risk_pct_of_net: 0,
        concurrent_positions: 0,
        by_strategy: {},
        by_sector: {},
        top_sector: null,
      }),
    }),
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
  // ⚠️ LIFO 순서는 cycle266 이 건드리지 않는다 (사이클 80 hotfix #3 영속,
  //    가드 = tests/unit/e2e_mocks/test_cycle124_api_mocks_daily_route.py).
  // cycle266 §C-3 — 종전 목은 `change_rate` 를 전부 진짜 number 로, `bas_dd` 를
  // `YYYYMMDD` 로 만들어 **의도한 계약**만 담고 **실제 응답**을 담지 않았다. 그래서
  // 일봉 탭이 프로덕션에서 3개월 넘게 흰 화면인 동안 목 셋은 계속 초록이었다.
  // 실제 응답: `change_rate`/`prtt_rate` = NUMERIC(8,4) → asyncpg Decimal →
  // pydantic v2 JSON **문자열** / `bas_dd` = DATE 컬럼 → `YYYY-MM-DD`.
  // ⇒ 문자열 행(시정 전 모양)과 숫자 행(A-1 시정 후 모양)을 **함께** 담는다.
  // 가드 = tests/unit/e2e_mocks/test_cycle266_mock_string_change_rate.py
  await page.route("**/api/stock-master/*/daily*", (route) =>
    route.fulfill({
      json: envelope([
        {
          bas_dd: "2026-09-05",
          open_price: 74000,
          high_price: 75500,
          low_price: 73500,
          close_price: 75000,
          volume: 1000000,
          trade_value: 75000000000,
          change_rate: "1.2000",
          prtt_rate: "0.0000",
        },
        {
          bas_dd: "2026-09-04",
          open_price: 74100,
          high_price: 75600,
          low_price: 73600,
          close_price: 75100,
          volume: 1050000,
          trade_value: 75000000000,
          change_rate: 0.9,
          prtt_rate: "0.0000",
        },
        {
          bas_dd: "2026-09-03",
          open_price: 74200,
          high_price: 75700,
          low_price: 73700,
          close_price: 75200,
          volume: 1100000,
          trade_value: 75000000000,
          change_rate: "0.6000",
          prtt_rate: "0.0000",
        },
        {
          bas_dd: "2026-09-02",
          open_price: 74300,
          high_price: 75800,
          low_price: 73800,
          close_price: 75300,
          volume: 1150000,
          trade_value: 75000000000,
          change_rate: 0.3,
          prtt_rate: "0.0000",
        },
        {
          bas_dd: "2026-09-01",
          open_price: 74400,
          high_price: 75900,
          low_price: 73900,
          close_price: 75400,
          volume: 1200000,
          trade_value: 75000000000,
          change_rate: "0.0000",
          prtt_rate: "0.0000",
        },
      ]),
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

  // ── cycle278 (2026-09-11) — 전략 파라미터 카탈로그 편집 ──────────────────────
  // 사이클 80 hotfix #3 LIFO 정합: 위쪽 `**/api/strategies/*/params`(무조건 200) 보다
  // **후** 등록해야 422 분기가 살아난다. 미등록이면 vite proxy → ECONNREFUSED → timeout.
  //
  // 스키마 본문은 손으로 쓴 요약이 아니라 `param_catalog.py` 에서 생성한 골든 픽스처다
  // (목이 *의도한 계약*만 담고 *실제 응답*을 안 담아 3개월 초록이던 cycle266 재발 차단).
  await page.route("**/api/strategies/params-schema", (route) =>
    route.fulfill({ json: envelope(PARAM_SCHEMA_FIXTURE) }),
  );

  // PUT 검증 시나리오 — 종목당 비중(비율 저장)이 1.0 을 넘으면 백엔드가 422 `out_of_range`.
  // 그 외에는 200 + applied. 비-PUT 은 앞서 등록된 기존 라우트로 넘긴다(fallback).
  await page.route("**/api/strategies/*/params", async (route) => {
    const request = route.request();
    if (request.method() !== "PUT") return route.fallback();
    const body = (request.postDataJSON() ?? {}) as { params?: Record<string, unknown> };
    const params = body.params ?? {};
    const ratio = params["position_ratio"];
    if (typeof ratio === "number" && ratio > 1.0) {
      return route.fulfill({
        status: 422,
        json: {
          detail: [
            {
              key: "position_ratio",
              code: "out_of_range",
              msg: `종목당 비중은 0.01 ~ 1.0 이어야 합니다 — 받은 값 ${ratio} (비율 저장, 화면 표시는 %)`,
              strategy_id: "momentum",
              given: ratio,
              expected: { min: 0.01, max: 1.0, type: "percent", range_src: "param_ranges" },
            },
          ],
        },
      });
    }
    return route.fulfill({
      json: envelope({ applied: params, warnings: [] }, "파라미터 저장 완료"),
    });
  });

  // ── cycle282 (2026-09-11) — 장운영상태(거래소 실제 장 운영 상태) ────────────
  // 표와 커서가 **한 응답**에서 나온다(M9). 미등록이면 vite proxy → 백엔드 미기동
  // → ECONNREFUSED → 페이지 timeout 이다(사이클 65 H3 계열).
  // 시나리오별 다른 시각/미리보기가 필요하면 이 호출 **뒤에** page.route 를 덧등록한다
  // (Playwright LIFO — 나중 등록이 이긴다).
  //
  // ⚠️ 사이클 104 hotfix 와 **같은 함정** — glob `**/api/market-state*` 는 vite dev 의 모듈
  // 요청 `http://localhost:3000/src/api/market-state.ts`(resourceType='script') 까지 잡아
  // JSON 으로 응답한다. 그러면 MIME 불일치로 `MarketState.tsx` 동적 import 가 통째로 실패해
  // 화면이 빈 채로 남는다(실측: "Failed to fetch dynamically imported module").
  // `**/api/logs*` 가 `src/api/logs.ts` 때문에 이미 같은 가드를 달고 있다 — 프론트 API
  // 모듈 파일명이 endpoint 이름과 같으면 항상 이 충돌이 난다.
  await page.route("**/api/market-state*", (route) => {
    if (route.request().resourceType() === "script") return route.continue();
    return route.fulfill({ json: envelope(MARKET_STATE_FIXTURE) });
  });

  // ── cycle285 (2026-09-13) — 야간작업 현황(오늘 완료현황 타임라인) ──────────────
  // `/api/market-state` 와 별도 엔드포인트다(표는 코드 상수, 이쪽은 DB/메모리 산출물이라
  // 실패 도메인이 다르다). 같은 함정(vite 모듈 `src/api/market-ops.ts` 가 이 glob 에
  // 잡히는 것)이 있어 동일한 resourceType 가드를 단다.
  await page.route("**/api/market-ops*", (route) => {
    if (route.request().resourceType() === "script") return route.continue();
    return route.fulfill({
      json: envelope({
        as_of_kst: "2026-09-13T20:35:00+09:00",
        is_trading_day: true,
        trading_day_source: "kis",
        engine: { running: true, phase: "closing", heartbeat_at: "2026-09-13T20:34:40+09:00" },
        tasks: [
          {
            id: "stock_master_basics_refresh",
            label_ko: "종목마스터 기본정보 보강",
            scheduled_at: "16:10",
            status: "done",
            last_success_at: "2026-09-13T16:12:03+09:00",
            evidence: { total: 2700, updated: 2700 },
            note: null,
          },
          {
            id: "quote_token_refresh",
            label_ko: "보조 시세계정 토큰 강제 재발급",
            scheduled_at: "19:00",
            status: "unknown",
            last_success_at: null,
            evidence: {},
            note: "이 작업은 성공 마커를 남기지 않는다",
          },
          {
            id: "recommendation",
            label_ko: "AI 매매자문",
            scheduled_at: "20:00",
            status: "done",
            last_success_at: "2026-09-13T20:00:42+09:00",
            evidence: { recommendation_rows_today: 7 },
            note: null,
          },
          {
            id: "stock_master_daily_load",
            label_ko: "일봉(KIS) 적재",
            scheduled_at: "20:30",
            status: "scheduled",
            last_success_at: "2026-09-11T18:10:13+09:00",
            evidence: { daily_head: "2026-09-11" },
            note: null,
          },
          {
            id: "settlement",
            label_ko: "정산(전략별 실적 집계)",
            scheduled_at: "21:30",
            status: "scheduled",
            last_success_at: null,
            evidence: {},
            note: null,
          },
        ],
        evidence_errors: [],
      }),
    });
  });

  // ── cycle303 (2026-09-18) — macro_lite 이식 1단계 5 엔드포인트 ──────────────
  // 🔴 이 5개는 envelope() 를 쓰지 않는다 — macro 서비스는 독립 FastAPI 프로세스라
  // 원본 계약(`{ <section>, updated_at, errors }`)을 그대로 반환한다(우리 ApiResponse
  // 래퍼 밖). `frontend/src/test/handlers.ts` 의 MSW 목과 동일 값(실측 근거 =
  // `packaging/macro_lite/backend/macro_lite/{fetcher,cycle,regime}.py` 반환문 +
  // `packaging/macro_lite/backend/tests/test_service_router.py` mock 기본값).
  //
  // 사이클 80 hotfix #3 LIFO 정합: wildcard `**/api/macro/**` 를 먼저(fallback) 등록하고
  // 5개 구체 라우트를 그 후 등록한다. 구체 경로가 전부 trailing wildcard 없이 끝나
  // (`/yield-curve` 처럼) vite 모듈 요청 `/src/api/macro.ts` 와 겹치지 않는다 — resourceType
  // 가드가 불요하다(`**/api/logs*`/`**/api/market-state*` 와 다른 계열, "/" 로 끝나지 않는
  // segment 뒤에 바로 ".ts" 가 오지 않으면 glob 이 매칭하지 않는다).
  await page.route("**/api/macro/**", (route) =>
    route.fulfill({ json: { errors: ["mock not registered"] } }),
  );
  await page.route("**/api/macro/yield-curve", (route) =>
    route.fulfill({
      json: {
        yield_curve: {
          current: { "3m": 5.0, "5y": 4.0, "10y": 4.2, "30y": 4.5 },
          spread_10y_3m: -0.8,
          history: [
            { date: "2020-01-01", y3m: 1.5, y10y: 1.8, spread: 0.3 },
            { date: "2020-06-01", y3m: 1.4, y10y: 1.6, spread: 0.2 },
          ],
          inverted: true,
          events: { recessions: [], bear_markets: [] },
        },
        updated_at: "2026-09-18T09:00:00+09:00",
        errors: [],
      },
    }),
  );
  await page.route("**/api/macro/credit-spread", (route) =>
    route.fulfill({
      json: {
        credit_spread: {
          oas_current: 3.5,
          oas_history_10y: [{ date: "2020-01-01", oas: 3.5 }],
          oas_history_5y: [{ date: "2020-01-01", oas: 3.5 }],
          oas_history: [{ date: "2020-01-01", oas: 3.5 }],
          oas_stats: { p10: 2.5, p25: 3.0, p75: 5.0, p90: 6.5, mean: 4.0, max: 10.0, max_date: "2020-03-23" },
          oas_percentile: 40.0,
          oas_zscore: -0.2,
          oas_sentiment: "normal",
          ig_current: 1.2,
          hy_ig_spread: 2.3,
          partial_failure: [],
          events: { recessions: [], bear_markets: [] },
        },
        updated_at: "2026-09-18T09:00:00+09:00",
        errors: [],
      },
    }),
  );
  await page.route("**/api/macro/currencies", (route) =>
    route.fulfill({
      json: {
        currencies: [
          {
            symbol: "USDKRW=X",
            name: "USD/KRW",
            price: 1300.0,
            prev_close: 1290.0,
            change: 10.0,
            change_pct: 0.7,
            sparkline: [],
          },
        ],
        updated_at: "2026-09-18T09:00:00+09:00",
        errors: [],
      },
    }),
  );
  await page.route("**/api/macro/commodities", (route) =>
    route.fulfill({
      json: {
        commodities: [
          {
            symbol: "GC=F",
            name: "금",
            price: 2000.0,
            prev_close: 1990.0,
            change: 10.0,
            change_pct: 0.5,
            sparkline: [],
          },
        ],
        updated_at: "2026-09-18T09:00:00+09:00",
        errors: [],
      },
    }),
  );
  await page.route("**/api/macro/macro-cycle", (route) =>
    route.fulfill({
      json: {
        cycle: {
          phase: "expansion",
          phase_label: "확장기",
          phase_desc: "양의 수익률곡선, 낮은 VIX, 좁은 스프레드",
          confidence: 62,
          scores: {
            yield_curve: { score: 0.15, weight: 0.3, signal: "스프레드 +1.00%" },
            credit_spread: { score: 0.06, weight: 0.2, signal: "안정" },
            vix: { score: 0.06, weight: 0.2, signal: "18.0 (보통)" },
            sector_rotation: { score: 0.0375, weight: 0.15, signal: "혼합" },
            dollar: { score: 0.0375, weight: 0.15, signal: "보합" },
          },
          leader_sectors: ["XLK", "XLY"],
        },
        regime: {
          regime: "cautious",
          regime_desc: "신중 (방어 선별)",
          params: {},
          vix: 18.0,
          buffett_ratio: 1.5,
          fear_greed_score: 50,
          buffett_level: "high",
          fg_level: "neutral",
          credit_adjustment: null,
          credit_override: null,
        },
        updated_at: "2026-09-18T09:00:00+09:00",
        errors: [],
      },
    }),
  );
}
