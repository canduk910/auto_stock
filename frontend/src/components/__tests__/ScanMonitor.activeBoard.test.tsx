/**
 * ScanMonitor — 활성 보드 자동 결정 (PR-G P3, 2026-05-15)
 *
 * 결함 (사용자 화면 캡처 KST 19:40):
 * - POST_NXT 활성 시간(15:30~20:00)인데 UI 토글이 잘못 표시
 * - 백엔드 boards: { post_nxt: ... } 만 반환 → main 데이터 없음 → 시가/타겟 "-" 표시
 *
 * Fix 사양:
 * 1. 백엔드 응답 boards keys 가 1개면 그 키를 자동 활성 보드로 결정
 * 2. boards keys 가 여러 개면 KST 시각 매핑 (기존 동작)
 * 3. boards 가 비었거나 fallback 시에도 KST 시각 매핑 (기존 동작 보존)
 *
 * 검증 포인트 — activeBoardCode 결정 결과는 row 정렬/현재가 pct 계산/chip 강조에 영향.
 * 본 테스트는 chip 의 활성 표시 (`●`) 를 통해 결정 결과를 간접 검증.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import ScanMonitor from "../ScanMonitor";

function makeStatus(boards: Record<string, { open_price: number; target_price: number; target_offset: number; confirmed: boolean }>) {
  return wrap({
    running: true,
    env: "vts",
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    phase: "post_nxt_trading",
    scan: {
      filtered_tickers: [],
      filtered_count: 0,
      subscribed_tickers: ["005930"],
      subscribed_count: 1,
      last_scan_time: "2026-05-15T19:40:00",
      ticker_names: { "005930": "삼성전자" },
      ticker_prices: {
        "005930": { current_price: 80000, open_price: 80000, change_rate: 0, prev_close: 80000 },
      },
      ticker_market_info: {},
      tick_coverage_total: 1,
      tick_coverage_acked: 1,
      tick_coverage_fresh: 1,
      tick_coverage_stale: 0,
    },
    positions_detail: {},
    orders: {
      pending_buy_tickers: [],
      pending_buy_orders: {},
      fills: {},
      pending_cancels: [],
    },
    strategy: {
      buy_disabled: false,
      daily_realized_pnl: 0,
      total_investment: 0,
      buy_signals: [],
    },
    strategies: {
      volatility_breakout: {
        name: "변동성 돌파",
        enabled: true,
        weight: 0.3,
        total_investment: 1000000,
        invested_amount: 0,
        positions: 0,
        positions_detail: {},
        params: {},
        daily_realized_pnl: 0,
        signal_count_today: 0,
        order_attempt_today: 0,
        fill_count_today: 0,
        buy_signals: [],
        scan_stats: {},
        targets: {
          "005930": {
            k: 0.5,
            target_price: 80500,
            open_price: 79000,
            target_offset: 500,
            boards,
          },
        },
      },
    },
  });
}

async function renderWithStatus(status: ReturnType<typeof makeStatus>) {
  server.use(
    http.get("/api/trading/status", () => HttpResponse.json(status)),
  );

  render(
    <TestProviders>
      <TradingStatusProvider>
        <ScanMonitor selectedStrategy="volatility_breakout" />
      </TradingStatusProvider>
    </TestProviders>,
  );

  await waitFor(() =>
    expect(
      screen.queryByText(/타겟 가격/) || screen.queryByText(/스캔된 종목 없음/),
    ).toBeTruthy(),
  );
}

describe("ScanMonitor — 활성 보드 자동 결정 (PR-G P3, 2026-05-15)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Case 1: boards={post_nxt:..} 단독 → KST 시각 무관 자동 post_nxt 선택
  // -------------------------------------------------------------------------
  it("boards={post_nxt} 만 응답 → activeBoardCode=post_nxt 자동 선택 (시각 무관)", async () => {
    // KST 09:30 — MAIN 시간대지만 백엔드는 post_nxt 만 반환
    vi.setSystemTime(new Date("2026-05-15T00:30:00Z"));

    await renderWithStatus(
      makeStatus({
        post_nxt: { open_price: 79000, target_price: 80500, target_offset: 500, confirmed: true },
      }),
    );

    await screen.findByText(/삼성전자\(005930\)/);
    // 헤더 chip 영역에서 "애프터 ●" — 활성 표시는 ` ●` 접미사
    // BOARD_META.post_nxt.label === '애프터'
    const chipText = await screen.findAllByText((_, el) => {
      return !!el && el.tagName === "SPAN" && /애프터\s*●/.test(el.textContent ?? "");
    });
    expect(chipText.length).toBeGreaterThanOrEqual(1);
  });

  // -------------------------------------------------------------------------
  // Case 2: boards={main:..} 단독 → activeBoardCode=main (시각 무관)
  // -------------------------------------------------------------------------
  it("boards={main} 만 응답 → activeBoardCode=main 자동 선택 (시각 무관)", async () => {
    // KST 19:40 — POST_NXT 시간대지만 백엔드는 main 만 반환
    vi.setSystemTime(new Date("2026-05-15T10:40:00Z"));

    await renderWithStatus(
      makeStatus({
        main: { open_price: 79500, target_price: 81000, target_offset: 1500, confirmed: true },
      }),
    );

    await screen.findByText(/삼성전자\(005930\)/);
    // 헤더 chip "메인 ●" 활성 표시
    const chipText = await screen.findAllByText((_, el) => {
      return !!el && el.tagName === "SPAN" && /메인\s*●/.test(el.textContent ?? "");
    });
    expect(chipText.length).toBeGreaterThanOrEqual(1);
  });

  // -------------------------------------------------------------------------
  // Case 3: boards 키 여러 개 → KST 시각 매핑 (기존 동작 보존)
  //   KST 19:40 + boards={main, post_nxt} → activeBoardCode=post_nxt (시각 매핑)
  // -------------------------------------------------------------------------
  it("boards 키 여러 개 + KST POST_NXT 시간대 → KST 시각 매핑으로 post_nxt", async () => {
    vi.setSystemTime(new Date("2026-05-15T10:40:00Z")); // KST 19:40

    await renderWithStatus(
      makeStatus({
        main: { open_price: 79500, target_price: 81000, target_offset: 1500, confirmed: true },
        post_nxt: { open_price: 79000, target_price: 80500, target_offset: 500, confirmed: true },
      }),
    );

    await screen.findByText(/삼성전자\(005930\)/);
    // KST 19:40 → post_nxt 활성 → "애프터 ●"
    const chipText = await screen.findAllByText((_, el) => {
      return !!el && el.tagName === "SPAN" && /애프터\s*●/.test(el.textContent ?? "");
    });
    expect(chipText.length).toBeGreaterThanOrEqual(1);
  });

  // -------------------------------------------------------------------------
  // Case 4: boards 비어 있음 → KST 시각 매핑 (기존 동작 보존)
  // -------------------------------------------------------------------------
  it("boards={} + KST MAIN 시간대 → KST 시각 매핑으로 main", async () => {
    vi.setSystemTime(new Date("2026-05-15T00:30:00Z")); // KST 09:30 = MAIN

    await renderWithStatus(makeStatus({}));

    // 종목 row 자체는 backwards-compat 으로 단일 row 렌더 (Case 2 of ScanMonitor.boards.test.tsx)
    await screen.findByText(/삼성전자\(005930\)/);
    // 헤더 chip "메인 ●" 노출 — KST 시각 fallback 매핑
    const chipText = await screen.findAllByText((_, el) => {
      return !!el && el.tagName === "SPAN" && /메인\s*●/.test(el.textContent ?? "");
    });
    expect(chipText.length).toBeGreaterThanOrEqual(1);
  });
});
