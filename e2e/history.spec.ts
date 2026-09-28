/**
 * cycle276 (2026-09-11) — 거래기록 "AI 자문" 팝업 E2E spec (G-E2E-10).
 *
 * 사용자 지시 = "UI의 거래기록(체결, 매매손익)에서 각 행에 AI매매자문 버튼을 달고
 * 버튼 선택 시 팝업형태로 확인가능하도록 함."
 * 명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §10 / §11.2(F29~F31).
 *
 * 왜 E2E 가 필요한가 — cycle266 은 종목마스터 "일봉" 탭이 **한 번도 동작한 적이 없는데도**
 * 3개월 넘게 초록이던 것을 실브라우저 케이스(G-E2E-9)로 잡았다. 단위 테스트의 목은
 * 개발자가 의도한 계약을 담고, 실브라우저는 그 계약이 실제로 화면에 서는지를 잰다.
 *
 * production 코드 변경 0 — spec + 목 픽스처만.
 * 사이클 65 hotfix #3 답습 — 모든 `toBeVisible()` 에 명시 timeout.
 * 사이클 80 hotfix #3 답습 — Playwright route 매칭은 **LIFO**(나중 등록이 이긴다).
 *
 * RED: "AI 자문" 열·버튼·모달이 아직 없다 → 3 케이스 전부 실패.
 */

import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

const BUY_ORDER_WITH_EVAL = "0000123456";
const BUY_ORDER_NO_EVAL = "0000222222";
const PAIR_BUY_1 = "0000200001";
const PAIR_BUY_2 = "0000200002";

function evaluation(overrides: Record<string, unknown> = {}) {
  return {
    trade_date: "2026-09-11",
    account_no_masked: "5011****",
    account_product: "01",
    created_at: "2026-09-11T09:01:34.612000+09:00",
    ticker: "005930",
    ticker_name: "삼성전자",
    order_no: BUY_ORDER_WITH_EVAL,
    eval_kind: "order",
    strategy_id: "volatility_breakout",
    mode: "shadow",
    result: "ok",
    reason: null,
    score: 62,
    min_score: 70,
    would_block: true,
    rationale: "거래량 동반 돌파이나 지수 약세가 상방을 제한한다.",
    key_risks: ["지수 약세"],
    invalidations: ["목표가 하회 마감"],
    model: "gpt-5.6-luna",
    tokens_in: 3120,
    tokens_out: 210,
    cost_usd: 0.00438,
    latency_ms: 3120,
    verdict_lag_ms: 3480,
    eval_to_order_lag_ms: 3480,
    order_kst: "2026-09-11T09:01:31.032000+09:00",
    evaluated_at: "2026-09-11T09:01:34.512000+09:00",
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
    raw_response: { content: '{"score":62}' },
    ...overrides,
  };
}

function trade(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    timestamp: "2026-09-11T09:01:33+09:00",
    ticker: "005930",
    ticker_name: "삼성전자",
    trade_type: "BUY",
    price: 71800,
    quantity: 3,
    profit_loss: 0,
    status: "COMPLETED",
    strategy: "volatility_breakout",
    order_no: BUY_ORDER_WITH_EVAL,
    ...overrides,
  };
}

test.describe("G-E2E-10 (HIGH) — 거래기록 AI 자문 팝업", () => {
  test("F29 체결 탭에서 AI 자문 버튼을 눌러 모달을 연다", async ({ page }) => {
    await installApiMocks(page, {
      trades: [
        trade(),
        trade({ id: 2, order_no: BUY_ORDER_NO_EVAL, ticker: "000660", ticker_name: "SK하이닉스" }),
      ],
      llmEvaluations: { [BUY_ORDER_WITH_EVAL]: evaluation() },
    });
    await page.goto("/history");

    const btn = page.getByTestId(`llm-eval-btn-${BUY_ORDER_WITH_EVAL}`);
    await expect(btn).toBeVisible({ timeout: 20000 });
    await btn.click();

    const modal = page.getByTestId("llm-eval-modal");
    await expect(modal).toBeVisible({ timeout: 20000 });

    // 점수·임계가 화면에 선다.
    await expect(page.getByTestId("llm-eval-score")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("llm-eval-score")).toContainText("62");
    await expect(page.getByTestId("llm-eval-score")).toContainText("70");
    // 계좌번호는 마스킹된 값만.
    await expect(modal).toContainText("5011****");
    // 숫자 변환 결함(cycle266 흰 화면 계열)의 흔적이 없어야 한다.
    await expect(modal).not.toContainText("NaN");
  });

  test("F30 매매손익 탭에서 다중 주문 페어의 탭이 보인다", async ({ page }) => {
    await installApiMocks(page, {
      llmEvaluations: {
        [PAIR_BUY_1]: evaluation({ order_no: PAIR_BUY_1, ticker: "042700", score: 77 }),
        [PAIR_BUY_2]: evaluation({ order_no: PAIR_BUY_2, ticker: "042700", score: 81 }),
      },
    });
    // LIFO — installApiMocks 의 pnl 라우트를 **나중 등록**으로 덮는다.
    await page.route("**/api/history/pnl*", (route) =>
      route.fulfill({
        json: {
          success: true,
          message: "",
          data: {
            pairs: [
              {
                buy_date: "2026-09-11",
                buy_time: "09:01:33",
                sell_date: "2026-09-11",
                sell_time: "14:22:10",
                ticker: "042700",
                ticker_name: "한미반도체",
                buy_price: 90000,
                buy_qty: 4,
                sell_price: 91000,
                sell_qty: 4,
                profit_loss: 4000,
                profit_rate: 1.11,
                status: "closed",
                strategy: "volatility_breakout",
                buy_order_nos: [PAIR_BUY_1, PAIR_BUY_2],
                sell_order_nos: ["0000200099"],
                pair_key: `volatility_breakout:042700:${PAIR_BUY_1}`,
              },
            ],
            page: 1,
            size: 30,
            total: 1,
            total_pages: 1,
            summary: {
              realized_total_krw: 4000,
              realized_rate_pct: 1.11,
              win_count: 1,
              loss_count: 0,
              even_count: 0,
              win_rate_pct: 100,
              closed_count: 1,
            },
          },
        },
      }),
    );

    await page.goto("/history");
    await page.getByRole("button", { name: "매매손익" }).click();

    const btn = page.getByTestId(
      `llm-eval-btn-pair-volatility_breakout:042700:${PAIR_BUY_1}`,
    );
    await expect(btn).toBeVisible({ timeout: 20000 });
    // 매수 주문 2건 = (2) 배지
    await expect(btn).toContainText("(2)");
    await btn.click();

    await expect(page.getByTestId("llm-eval-modal")).toBeVisible({ timeout: 20000 });
    // 주문별 탭 2개 + 첫 매수 주문 기준 고지
    await expect(page.getByTestId(`llm-eval-order-tab-${PAIR_BUY_1}`)).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByTestId(`llm-eval-order-tab-${PAIR_BUY_2}`)).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByTestId("llm-eval-modal")).toContainText("첫 매수 주문");
  });

  test("F31 평가 기록 없는 행의 버튼은 비활성이다", async ({ page }) => {
    await installApiMocks(page, {
      trades: [
        trade(),
        trade({ id: 2, order_no: BUY_ORDER_NO_EVAL, ticker: "000660", ticker_name: "SK하이닉스" }),
        trade({
          id: 3,
          order_no: "0000333333",
          trade_type: "SELL",
          profit_loss: 2100,
        }),
      ],
      llmEvaluations: { [BUY_ORDER_WITH_EVAL]: evaluation() },
    });
    await page.goto("/history");

    // 기록 있는 매수 행 = 활성
    await expect(page.getByTestId(`llm-eval-btn-${BUY_ORDER_WITH_EVAL}`)).toBeEnabled({
      timeout: 20000,
    });
    // 기록 없는 매수 행 = 비활성
    await expect(page.getByTestId(`llm-eval-btn-${BUY_ORDER_NO_EVAL}`)).toBeDisabled({
      timeout: 20000,
    });
    // 매도 행 = 비활성(열 폭 유지용 자리)
    await expect(page.getByTestId("llm-eval-btn-0000333333")).toBeDisabled({
      timeout: 20000,
    });
  });
});

// =======================================================================
// cycle387 (2026-09-28) — 행 더블클릭 → 종목 차트 모달 (G-E2E-11)
//
// 사용자 요청 = 「잔고내역과 거래내역(주문체결내역, 매매손익)에서 종목을 더블클릭하면
// KLineChart를 사용한 주식차트조회를 최근 5년치에 대해 일봉/주봉/월봉으로 제공」.
// 명세 = `_workspace/red/cycle387_stock_chart_spec.md` §3.3(F32·F33).
//
// 왜 E2E 가 필요한가 — 단위 테스트는 jsdom 에 canvas 가 없어 `klinecharts` 를 가짜로 바꿔 끼운다.
// 실제 라이브러리가 모달 안에 캔버스를 세우고, lazy 청크가 로드되고, 기간 토글이 새 요청을 내는지는
// 실브라우저에서만 잰다. 잔고 표(대시보드)는 vitest O1·O2 가 맡는다.
//
// RED: 행 testid·더블클릭·모달·목 라우트가 없다 → 두 케이스 전부 실패.
// =======================================================================

test.describe("G-E2E-11 (cycle387) — 거래기록 행 더블클릭 종목 차트", () => {
  test("F32 체결 행 더블클릭 → 캔버스 · 메타 · 주봉 요청 · ESC 닫기", async ({ page }) => {
    await installApiMocks(page, { trades: [trade()] });
    await page.goto("/history");

    const row = page.getByTestId("trade-row-0");
    await expect(row).toBeVisible({ timeout: 20000 });
    await row.getByText("삼성전자").dblclick();

    const modal = page.getByTestId("stock-chart-modal");
    await expect(modal).toBeVisible({ timeout: 20000 });
    await expect(modal.locator("canvas").first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("stock-chart-meta")).toContainText("수정주가", { timeout: 20000 });
    await expect(page.getByTestId("stock-chart-title")).toContainText("005930", { timeout: 20000 });

    const weekly = page.waitForRequest((req) => {
      if (!req.url().includes("/api/stock-chart/candles")) return false;
      const u = new URL(req.url());
      return u.searchParams.get("period") === "W" && u.searchParams.get("ticker") === "005930";
    });
    await page.getByTestId("stock-chart-period-W").click();
    await weekly;
    await expect(page.getByTestId("stock-chart-period-W")).toHaveAttribute("aria-pressed", "true", {
      timeout: 20000,
    });

    await expect(modal).not.toContainText("NaN");
    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden({ timeout: 20000 });
  });

  test("F33 매매손익 탭 행 더블클릭 → 그 행의 종목 차트", async ({ page }) => {
    await installApiMocks(page);
    // LIFO — installApiMocks 의 pnl 라우트를 **나중 등록**으로 덮는다(F30 과 같은 방식).
    await page.route("**/api/history/pnl*", (route) => {
      if (!new URL(route.request().url()).pathname.startsWith("/api/")) return route.continue();
      return route.fulfill({
        json: {
          success: true,
          message: "",
          data: {
            pairs: [
              {
                buy_date: "2026-09-11",
                buy_time: "09:01:33",
                sell_date: "2026-09-11",
                sell_time: "14:22:10",
                ticker: "042700",
                ticker_name: "한미반도체",
                buy_price: 90000,
                buy_qty: 4,
                sell_price: 91000,
                sell_qty: 4,
                profit_loss: 4000,
                profit_rate: 1.11,
                status: "closed",
                strategy: "volatility_breakout",
                buy_order_nos: [PAIR_BUY_1],
                sell_order_nos: ["0000200099"],
                pair_key: `volatility_breakout:042700:${PAIR_BUY_1}`,
              },
            ],
            page: 1,
            size: 30,
            total: 1,
            total_pages: 1,
            summary: {
              realized_total_krw: 4000,
              realized_rate_pct: 1.11,
              win_count: 1,
              loss_count: 0,
              even_count: 0,
              win_rate_pct: 100,
              closed_count: 1,
            },
          },
        },
      });
    });

    await page.goto("/history");
    await page.getByRole("button", { name: "매매손익" }).click();

    const row = page.getByTestId("pnl-row-0");
    await expect(row).toBeVisible({ timeout: 20000 });
    const request = page.waitForRequest(
      (req) =>
        req.url().includes("/api/stock-chart/candles") &&
        new URL(req.url()).searchParams.get("ticker") === "042700",
    );
    await row.getByText("한미반도체").dblclick();
    await request;

    await expect(page.getByTestId("stock-chart-modal")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("stock-chart-title")).toContainText("한미반도체", { timeout: 20000 });
    await expect(page.getByTestId("stock-chart-title")).toContainText("042700", { timeout: 20000 });
  });
});
