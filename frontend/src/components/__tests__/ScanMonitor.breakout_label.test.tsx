/**
 * 사이클 18 (2026-05-19) Red — "돌파" 라벨 매매 가능 시간대 컨텍스트.
 *
 * 배경:
 * - 2026-05-19 운영 사례: 한화에어로스페이스(012450) 16:43 "돌파" 표시되나 매수 0건
 * - VB `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main")` 보드 가드 skip (정상 정책)
 * - UI 가 *매매 가능 여부* 표시 안 함 → 운영자 혼란 ("왜 안 사지?")
 *
 * 변경:
 * - 활성 보드 ∩ 전략 tradable_boards ≠ ∅ → 기존 빨강 "돌파" 라벨 (매매 시간대 정상)
 * - 활성 보드 ∩ 전략 tradable_boards = ∅ → 회색 "돌파 (대기 — {보드라벨})" 라벨
 *   * 매매 불가 시간대임을 운영자가 즉시 인지
 *   * 보드라벨 = 한글 (프리/메인/애프터 등)
 *
 * 회귀 가드 (5 케이스):
 * - C18-B1: VB + PRE_NXT 시간 + curPrice >= target → 빨강 "돌파"
 * - C18-B2: VB + POST_NXT 시간 + curPrice >= target → 회색 "돌파 (대기 — 프리/메인)"
 * - C18-B3: LTV + KRX 메인 시간 → 빨강 "돌파" (LTV tradable=[pre_nxt, main])
 * - C18-B4: BFB + POST_NXT 시간 → 회색 "돌파 (대기 — 메인)" (BFB tradable=[main])
 * - C18-B5: tradable_boards 미존재 (백엔드 미반영) → 기존 빨강 "돌파" fallback (안전 회귀)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import ScanMonitor from "../ScanMonitor";

function makeBreakoutStatus(opts: {
  strategyKey: string;
  strategyName: string;
  ticker: string;
  curPrice: number;
  targetPrice: number;
  openPrice: number;
  board: string;  // "main" | "pre_nxt" | "post_nxt"
  tradableBoards: string[] | undefined;
  phase?: string;
}) {
  return wrap({
    running: true,
    env: "vts",
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    phase: opts.phase ?? "main_trading",
    scan: {
      filtered_tickers: [],
      filtered_count: 0,
      subscribed_tickers: [opts.ticker],
      subscribed_count: 1,
      last_scan_time: "2026-05-19T10:00:00",
      ticker_names: { [opts.ticker]: "테스트종목" },
      ticker_prices: {
        [opts.ticker]: {
          current_price: opts.curPrice,
          open_price: opts.openPrice,
          change_rate: 0,
          prdy_ctrt: 0,
        },
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
    strategy: { buy_disabled: false, daily_realized_pnl: 0, total_investment: 0, buy_signals: [] },
    strategies: {
      [opts.strategyKey]: {
        name: opts.strategyName,
        enabled: true,
        weight: 0.3,
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
        scanned_count: 1,
        scanned_tickers: [opts.ticker],
        scan_stats: {},
        ...(opts.tradableBoards !== undefined && { tradable_boards: opts.tradableBoards }),
        targets: {
          [opts.ticker]: {
            k: 1.0,
            target_price: opts.targetPrice,
            open_price: opts.openPrice,
            target_offset: opts.targetPrice - opts.openPrice,
            boards: {
              [opts.board]: {
                open_price: opts.openPrice,
                target_price: opts.targetPrice,
                target_offset: opts.targetPrice - opts.openPrice,
                confirmed: true,
              },
            },
            open_confirmed: { [opts.board]: true },
          },
        },
        pending_buy_tickers: [],
      },
    },
  });
}

async function renderScanMonitor(selectedStrategy: string) {
  render(
    <TestProviders>
      <TradingStatusProvider>
        <ScanMonitor selectedStrategy={selectedStrategy} />
      </TradingStatusProvider>
    </TestProviders>,
  );
  await waitFor(() =>
    expect(screen.queryByText(/활성 보드/) || screen.queryByText(/조건검색 현황/)).toBeTruthy(),
  );
}

describe("ScanMonitor — 돌파 라벨 매매 가능 컨텍스트 (사이클 18)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  // C18-B1: VB + PRE_NXT 시간 + 돌파 → 빨강 "돌파" (교집합 ∋)
  it("C18-B1: VB PRE_NXT 시간 + curPrice >= target → 빨강 '돌파' 라벨", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T23:30:00Z")); // 다음날 KST 08:30 PRE_NXT

    const status = makeBreakoutStatus({
      strategyKey: "volatility_breakout",
      strategyName: "변동성 돌파",
      ticker: "005930",
      curPrice: 85000,
      targetPrice: 80000,
      openPrice: 79000,
      board: "pre_nxt",
      tradableBoards: ["pre_nxt", "main"],
      phase: "pre_nxt_trading",
    });
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("volatility_breakout");

    // 빨강 "돌파" 라벨 (대기 가 없음)
    const dolpa = await screen.findByText("돌파");
    expect(dolpa.className).toMatch(/red/);
  });

  // C18-B2: VB POST_NXT 시간 + 돌파 → 회색 "돌파 (대기 — 프리/메인)"
  it("C18-B2: VB POST_NXT 시간 → 회색 '돌파 (대기 — 프리/메인)' 라벨", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T07:43:00Z")); // KST 16:43 POST_NXT

    const status = makeBreakoutStatus({
      strategyKey: "volatility_breakout",
      strategyName: "변동성 돌파",
      ticker: "012450",
      curPrice: 1500000,
      targetPrice: 1450000,
      openPrice: 1400000,
      board: "post_nxt",
      tradableBoards: ["pre_nxt", "main"],  // POST_NXT 불포함 = 매매 시간 외
      phase: "post_nxt_trading",
    });
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("volatility_breakout");

    // "돌파 (대기" 텍스트 + 회색 클래스
    const dolpaWait = await screen.findByText(/돌파 \(대기/);
    expect(dolpaWait.className).toMatch(/gray/);
    // 매매 가능 보드 라벨 — 프리/메인
    expect(dolpaWait.textContent).toMatch(/프리|메인/);
  });

  // C18-B3: LTV + KRX 메인 시간 + 돌파 → 빨강 (LTV tradable=[pre_nxt, main])
  it("C18-B3: LTV KRX 메인 시간 + curPrice >= target → 빨강 '돌파'", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T03:00:00Z")); // KST 12:00 MAIN

    const status = makeBreakoutStatus({
      strategyKey: "long_tail_volatility",
      strategyName: "롱테일 변동성",
      ticker: "005930",
      curPrice: 85000,
      targetPrice: 80000,
      openPrice: 79000,
      board: "main",
      tradableBoards: ["pre_nxt", "main"],
      phase: "main_trading",
    });
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("long_tail_volatility");

    const dolpa = await screen.findByText("돌파");
    expect(dolpa.className).toMatch(/red/);
  });

  // C18-B4: BFB + POST_NXT → 회색 "돌파 (대기 — 메인)"
  it("C18-B4: BFB POST_NXT 시간 → 회색 '돌파 (대기 — 메인)' 라벨", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T07:43:00Z")); // KST 16:43 POST_NXT

    const status = makeBreakoutStatus({
      strategyKey: "bull_flag_breakout",
      strategyName: "눌림목 돌파",
      ticker: "005930",
      curPrice: 85000,
      targetPrice: 80000,
      openPrice: 79000,
      board: "post_nxt",
      tradableBoards: ["main"],  // BFB MAIN only
      phase: "post_nxt_trading",
    });
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("bull_flag_breakout");

    const dolpaWait = await screen.findByText(/돌파 \(대기/);
    expect(dolpaWait.className).toMatch(/gray/);
    expect(dolpaWait.textContent).toMatch(/메인/);
  });

  // C18-B5: tradable_boards 미존재 → 기존 빨강 "돌파" fallback (안전 회귀)
  it("C18-B5: tradable_boards 미반영 시 기존 빨강 '돌파' fallback", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T07:43:00Z")); // KST 16:43 POST_NXT

    const status = makeBreakoutStatus({
      strategyKey: "volatility_breakout",
      strategyName: "변동성 돌파",
      ticker: "005930",
      curPrice: 85000,
      targetPrice: 80000,
      openPrice: 79000,
      board: "post_nxt",
      tradableBoards: undefined,  // 백엔드 미반영 시점 호환
      phase: "post_nxt_trading",
    });
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("volatility_breakout");

    // 기존 동작 보존: 빨강 "돌파" (대기 없음)
    const dolpa = await screen.findByText("돌파");
    expect(dolpa.className).toMatch(/red/);
  });
});
