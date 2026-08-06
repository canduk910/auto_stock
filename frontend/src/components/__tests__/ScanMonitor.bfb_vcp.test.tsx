/**
 * ScanMonitor — BFB(bull_flag_breakout) / VCP(vcp_breakout) 가시화 회귀 (사이클 13).
 *
 * 사이클 13 (2026-05-18) 변경:
 * - `BREAKOUT_KEYS` 4종으로 확장 (volatility_breakout / long_tail_volatility /
 *   bull_flag_breakout / vcp_breakout)
 * - `BREAKOUT_LABELS` "눌림목 돌파" / "VCP 변동성 수축" 신규 라벨
 * - 전체 탭에서 BFB/VCP 카운트 카드 노출
 * - 전략 탭 진입 시 BFB/VCP 도 운영시간 안내 + 타겟 가격 테이블 렌더 (VB/LTV 분기 재사용)
 *
 * 의미 전환 (2026-08-06) — C13-B/C13-C: BFB/VCP 전략 탭의 "타겟 가격" 테이블(VB/LTV 재사용)이
 * K값/보드별 시가가 무의미한 두 전략에 "K값 0.000 · 시가 -" 만 보여줘 "왜 안 사는가"에
 * 답하지 못했다 (VCP 후보 0 / BFB 후보 33% WebSocket 미구독 은폐). `BreakoutCandidateMonitor`
 * 전용 컴포넌트(구독 커버리지 + 돌파선 거리 + 상태 배지)로 대체 — VB/LTV 경로는 byte 동일
 * 보존. 아래 두 케이스는 "타겟 가격" 헤더 대신 신규 컴포넌트 렌더를 검증하도록 갱신.
 *
 * 회귀 가드 (3 케이스):
 * - C13-A: 전체 탭에서 BFB/VCP 카운트 카드 노출
 * - C13-B: BFB 전략 탭 진입 시 BreakoutCandidateMonitor 렌더 (타겟 가격 테이블 대체)
 * - C13-C: VCP 전략 탭 진입 시 BreakoutCandidateMonitor 렌더 (타겟 가격 테이블 대체)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import ScanMonitor from "../ScanMonitor";

function makeStatusWithBfbVcp() {
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
      subscribed_tickers: ["005930", "000660"],
      subscribed_count: 2,
      last_scan_time: "2026-05-18T10:00:00",
      ticker_names: { "005930": "삼성전자", "000660": "SK하이닉스" },
      ticker_prices: {
        "005930": { current_price: 80000, open_price: 79000, change_rate: 0, prdy_ctrt: 0 },
        "000660": { current_price: 150000, open_price: 148000, change_rate: 0, prdy_ctrt: 0 },
      },
      ticker_market_info: {},
      tick_coverage_total: 2,
      tick_coverage_acked: 2,
      tick_coverage_fresh: 2,
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
      bull_flag_breakout: {
        name: "눌림목 돌파",
        enabled: true,
        weight: 0.1,
        total_investment: 1_000_000,
        invested_amount: 0,
        positions: 0,
        pending_buys: 0,
        position_tickers: [],
        positions_detail: {},
        params: {},
        daily_realized_pnl: 0,
        buy_disabled: false,
        buy_signals: [],
        scanned_count: 5,
        scanned_tickers: ["005930"],
        scan_stats: {},
        targets: {
          "005930": {
            k: 1.0,
            target_price: 81000,
            open_price: 79000,
            target_offset: 2000,
            boards: {
              main: { open_price: 79000, target_price: 81000, target_offset: 2000, confirmed: true },
            },
            open_confirmed: { main: true },
          },
        },
        pending_buy_tickers: [],
      },
      vcp_breakout: {
        name: "VCP 변동성 수축",
        enabled: true,
        weight: 0.1,
        total_investment: 1_000_000,
        invested_amount: 0,
        positions: 0,
        pending_buys: 0,
        position_tickers: [],
        positions_detail: {},
        params: {},
        daily_realized_pnl: 0,
        buy_disabled: false,
        buy_signals: [],
        scanned_count: 3,
        scanned_tickers: ["000660"],
        scan_stats: {},
        targets: {
          "000660": {
            k: 1.0,
            target_price: 152000,
            open_price: 148000,
            target_offset: 4000,
            boards: {
              main: { open_price: 148000, target_price: 152000, target_offset: 4000, confirmed: true },
            },
            open_confirmed: { main: true },
          },
        },
        pending_buy_tickers: [],
      },
    },
  });
}

async function renderScanMonitor(selectedStrategy: string) {
  const status = makeStatusWithBfbVcp();
  server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

  render(
    <TestProviders>
      <TradingStatusProvider>
        <ScanMonitor selectedStrategy={selectedStrategy} />
      </TradingStatusProvider>
    </TestProviders>,
  );
  // 폴링 첫 응답 대기 — 활성 보드 배지 또는 phase 라벨
  await waitFor(() =>
    expect(screen.queryByText(/활성 보드/) || screen.queryByText(/조건검색 현황/)).toBeTruthy(),
  );
}

describe("ScanMonitor — BFB/VCP 가시화 (사이클 13)", () => {
  beforeEach(() => {
    // KST 10:00 — MAIN 활성 (BFB/VCP 모두 MAIN only)
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-18T01:00:00Z")); // UTC 01:00 = KST 10:00
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // C13-A: 전체 탭 → BFB/VCP 카운트 카드 노출
  it("C13-A: 전체 탭에서 BFB/VCP 스캔 카운트 카드 노출", async () => {
    await renderScanMonitor("all");

    // 4종 라벨 모두 노출 — "눌림목 돌파" + "VCP 변동성 수축"
    await screen.findByText(/눌림목 돌파/);
    await screen.findByText(/VCP 변동성 수축/);
    // 카운트 — BFB 5종목 / VCP 3종목
    expect(screen.getByText(/눌림목 돌파 스캔: 5종목/)).toBeInTheDocument();
    expect(screen.getByText(/VCP 변동성 수축 스캔: 3종목/)).toBeInTheDocument();
  });

  // C13-B: BFB 전략 탭 → BreakoutCandidateMonitor 렌더 (타겟 가격 테이블 대체, 2026-08-06)
  it("C13-B: BFB 전략 탭 진입 시 BreakoutCandidateMonitor 렌더 + 후보 종목 노출", async () => {
    await renderScanMonitor("bull_flag_breakout");

    expect(await screen.findByTestId("breakout-candidate-monitor")).toBeTruthy();
    expect(screen.getByTestId("breakout-candidate-row-005930")).toBeTruthy();
    // 종목명(scan.ticker_names 아닌 targets.name 부재 → ticker 폴백)
    expect(screen.getByTestId("breakout-candidate-row-005930").textContent).toContain("005930");
    // 돌파선 81,000 렌더
    expect(screen.getByText("81,000")).toBeInTheDocument();
  });

  // C13-C: VCP 전략 탭 → BreakoutCandidateMonitor 렌더 (타겟 가격 테이블 대체, 2026-08-06)
  it("C13-C: VCP 전략 탭 진입 시 BreakoutCandidateMonitor 렌더 + 후보 종목 노출", async () => {
    await renderScanMonitor("vcp_breakout");

    expect(await screen.findByTestId("breakout-candidate-monitor")).toBeTruthy();
    expect(screen.getByTestId("breakout-candidate-row-000660")).toBeTruthy();
    expect(screen.getByText("152,000")).toBeInTheDocument();
  });
});
