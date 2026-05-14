/**
 * ScanMonitor — 활성 보드 필터 row 렌더링 (2026-05-13 작업 1).
 *
 * 명세 (`_workspace/00_leader_trading_rules.md` L420~466):
 * - `t.boards` 비지 않음 → 그대로 (백엔드가 활성 보드만 보냄)
 * - `t.boards` 빈 dict + `activeBoardCode` 있음 → backwards-compat 단일 row 렌더
 * - `t.boards` 빈 dict + `activeBoardCode` 없음(장 외) → 종목 row 자체 미렌더
 *
 * activeBoardCode 는 `activeBoards` 의 KST 시각 기반(`getKstMinutes`)으로 결정 →
 * `vi.useFakeTimers + vi.setSystemTime` 으로 09:30 (MAIN) / 21:00 (장 외) 시뮬레이션.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import ScanMonitor from "../ScanMonitor";

function makeStatusWithVBTarget(
  ticker: string,
  target: {
    k?: number;
    target_price?: number;
    open_price?: number;
    target_offset?: number;
    boards?: Record<
      string,
      { open_price: number; target_price: number; target_offset: number; confirmed: boolean }
    >;
    open_confirmed?: boolean | Record<string, boolean>;
  },
) {
  return wrap({
    running: true,
    env: "vts",
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    phase: "main_trading",
    scan: {
      filtered_tickers: [],
      filtered_count: 0,
      subscribed_tickers: [ticker],
      subscribed_count: 1,
      last_scan_time: "2026-05-13T09:30:00",
      ticker_names: { [ticker]: "삼성전자" },
      ticker_prices: {
        [ticker]: { current_price: 80000, open_price: 80000, change_rate: 0, prev_close: 80000 },
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
        targets: { [ticker]: { ...target } },
      },
    },
  });
}

async function renderScanMonitor(scenarioStatus: ReturnType<typeof makeStatusWithVBTarget>) {
  server.use(
    http.get("/api/trading/status", () => HttpResponse.json(scenarioStatus)),
  );

  render(
    <TestProviders>
      <TradingStatusProvider>
        <ScanMonitor selectedStrategy="volatility_breakout" />
      </TradingStatusProvider>
    </TestProviders>,
  );

  // 폴링 첫 응답 도착 대기 — VB 탭은 "타겟 가격" 헤더 / "스캔된 종목 없음" 중 하나
  await waitFor(() =>
    expect(
      screen.queryByText(/타겟 가격/) || screen.queryByText(/스캔된 종목 없음/),
    ).toBeTruthy(),
  );
}

describe("ScanMonitor — 활성 보드 필터 row 렌더링 (2026-05-13 작업 1)", () => {
  beforeEach(() => {
    // Date 만 fake — setTimeout / queueMicrotask 등은 real 유지해 React Query 폴링 살아있음
    vi.useFakeTimers({ toFake: ["Date"] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Case 1: boards 비지 않음 (예: {main}) — 그대로 렌더 (단일 row, 메인 라벨)
  // -------------------------------------------------------------------------
  it("boards={main: ...} + activeBoardCode=main → 단일 row 렌더 (메인 라벨)", async () => {
    // KST 09:30 — MAIN 활성
    vi.setSystemTime(new Date("2026-05-13T00:30:00Z")); // UTC 00:30 = KST 09:30

    await renderScanMonitor(
      makeStatusWithVBTarget("005930", {
        k: 0.5,
        target_price: 80500,
        open_price: 79000,
        target_offset: 500,
        boards: {
          main: { open_price: 79000, target_price: 80500, target_offset: 500, confirmed: true },
        },
        open_confirmed: { main: true },
      }),
    );

    // 종목명 셀 노출 (row 렌더 검증)
    await screen.findByText(/삼성전자\(005930\)/);
    // 메인 라벨 노출 — 헤더 chip + row 내부 시가 chip
    const mainChips = await screen.findAllByText("메인");
    expect(mainChips.length).toBeGreaterThanOrEqual(1);
    // 타겟가 셀 (80,500 — current_price 80000 과 구분되는 유니크 값)
    expect(screen.getByText("80,500")).toBeInTheDocument();
    // 시가 셀 (79,000 — 다른 셀과 충돌 없는 유니크 값)
    expect(screen.getByText("79,000")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Case 2: boards 빈 dict + activeBoardCode 있음(MAIN) → backwards-compat 단일 row
  // -------------------------------------------------------------------------
  it("boards={} + activeBoardCode=main → backwards-compat 단일 row 렌더", async () => {
    vi.setSystemTime(new Date("2026-05-13T00:30:00Z")); // KST 09:30 = MAIN 활성

    await renderScanMonitor(
      makeStatusWithVBTarget("005930", {
        k: 0.5,
        target_price: 81000,
        open_price: 79500,
        target_offset: 1500,
        boards: {}, // 빈 dict — 백엔드가 활성 보드 교집합 공집합 시 보낼 수도 있는 형태
        open_confirmed: false,
      }),
    );

    // backwards-compat — 종목 행 자체는 렌더되어야 함 (activeBoardCode 있음)
    await screen.findByText(/삼성전자\(005930\)/);
    // top-level open_price 79,500 / target_price 81,000 표시 (현재가 80,000 과 구분)
    expect(screen.getByText("79,500")).toBeInTheDocument();
    expect(screen.getByText("81,000")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Case 3: boards 빈 dict + activeBoardCode 없음(장 외 21:00) → row 미렌더
  // -------------------------------------------------------------------------
  it("boards={} + activeBoardCode 없음(장 외) → 종목 row 미렌더", async () => {
    // KST 21:00 = UTC 12:00 — 모든 보드 비활성
    vi.setSystemTime(new Date("2026-05-13T12:00:00Z"));

    await renderScanMonitor(
      makeStatusWithVBTarget("005930", {
        k: 0.5,
        target_price: 81000,
        open_price: 80000,
        target_offset: 1000,
        boards: {},
        open_confirmed: false,
      }),
    );

    // "타겟 가격" 헤더는 여전히 노출되지만, 종목 row 는 렌더되지 않아야 함
    // → "삼성전자" 텍스트가 화면에 없음
    expect(screen.queryByText(/삼성전자/)).not.toBeInTheDocument();
  });
});
