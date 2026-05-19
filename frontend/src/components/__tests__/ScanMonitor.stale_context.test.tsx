/**
 * 사이클 18 (2026-05-19) Red — 끊김 종목 시간대 컨텍스트 + 펼치기 last_tick 시각.
 *
 * 배경:
 * - 2026-05-19 운영 진단에서 NXT 애프터 시간대 "끊김 19종목" 이 시스템 결함처럼 보임
 * - 실제로는 거래량 부족에 따른 자연 stale (한산 시간) — 운영자 혼란 유발
 *
 * 변경:
 * - 끊김 배지 옆 시간대 컨텍스트 라벨 추가:
 *   * KRX 메인 (09:00~15:30): "결함 가능" 빨강 — 즉시 점검 필요
 *   * PRE_NXT (08:00~09:00): "거래량 적음, 관찰" 노랑 — 경계
 *   * 그 외 (시간 외 / NXT 애프터): "한산 시 정상" 회색 — 정상 휴면
 * - 끊김 종목 펼치기 토글 → `last_tick_map` 기반 종목별 "마지막: HH:MM:SS" 표시
 *
 * 회귀 가드 (5 케이스):
 * - C18-S1: KRX 메인 시간 + stale>0 → "결함 가능" 빨강 컨텍스트 라벨
 * - C18-S2: NXT 애프터 시간 + stale>0 → "한산 시 정상" 회색 컨텍스트 라벨
 * - C18-S3: PRE_NXT 시간 + stale>0 → "거래량 적음" 노랑 컨텍스트 라벨
 * - C18-S4: stale=0 → 컨텍스트 라벨 미노출
 * - C18-S5: 끊김 펼치기 토글 → last_tick_map 기반 종목별 시각 표시
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import ScanMonitor from "../ScanMonitor";

function makeStatusWithStale(staleCount: number, freshCount: number = 0) {
  const total = staleCount + freshCount;
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
      subscribed_tickers: [],
      subscribed_count: total,
      last_scan_time: "2026-05-19T16:00:00",
      ticker_names: {},
      ticker_prices: {},
      ticker_market_info: {},
      tick_coverage_total: total,
      tick_coverage_acked: total,
      tick_coverage_fresh: freshCount,
      tick_coverage_stale: staleCount,
    },
    positions_detail: {},
    orders: {
      pending_buy_tickers: [],
      pending_buy_orders: {},
      fills: {},
      pending_cancels: [],
    },
    strategy: { buy_disabled: false, daily_realized_pnl: 0, total_investment: 0, buy_signals: [] },
    strategies: {},
  });
}

function makeSubscriptionsResponse(staleTickers: string[], lastTickMap: Record<string, string | null>) {
  return {
    success: true,
    data: {
      total: staleTickers.length,
      acked: staleTickers.length,
      fresh_60s: 0,
      stale_60s: staleTickers.length,
      limit: 41,
      tickers: {
        subscribed: staleTickers,
        acked: staleTickers,
        fresh: [],
        stale: staleTickers,
      },
      last_tick_map: lastTickMap,
      reconnect_count: 0,
      ws_connected: true,
      sessions: [
        {
          label: "main",
          subscribed: staleTickers.length,
          acked: staleTickers.length,
          fresh: 0,
          stale: staleTickers.length,
          limit: 41,
          ws_connected: true,
          reconnect_count: 0,
        },
      ],
    },
    message: "",
  };
}

async function renderScanMonitor(selectedStrategy: string = "all") {
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

describe("ScanMonitor — 끊김 시간대 컨텍스트 (사이클 18)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  // C18-S1: KRX 메인 시간 + stale=5 → "결함" 빨강 컨텍스트
  it("C18-S1: KRX 메인 시간 stale>0 → '결함 가능' 빨강 컨텍스트 라벨", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T01:00:00Z")); // KST 10:00

    const status = makeStatusWithStale(5, 10);
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("all");

    await waitFor(() =>
      expect(screen.getByTestId("stale-context-label")).toBeInTheDocument(),
    );
    const label = screen.getByTestId("stale-context-label");
    expect(label).toHaveTextContent(/결함/);  // "결함 가능" 또는 유사
    expect(label.className).toMatch(/red/);
  });

  // C18-S2: NXT 애프터 시간 + stale=19 → "한산" 회색 컨텍스트
  it("C18-S2: NXT 애프터 시간 stale>0 → '한산 시 정상' 회색 컨텍스트 라벨", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T07:40:00Z")); // KST 16:40

    const status = makeStatusWithStale(19, 5);
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("all");

    await waitFor(() =>
      expect(screen.getByTestId("stale-context-label")).toBeInTheDocument(),
    );
    const label = screen.getByTestId("stale-context-label");
    expect(label).toHaveTextContent(/한산|정상/);
    expect(label.className).toMatch(/gray/);
  });

  // C18-S3: PRE_NXT 시간 + stale=3 → 노랑
  it("C18-S3: PRE_NXT 시간 stale>0 → '거래량 적음' 노랑 컨텍스트 라벨", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T23:30:00Z")); // KST 08:30 다음날 08:30 (UTC 23:30 5/19)
    // Wait — 정확히 PRE_NXT (08:00~09:00) 시간. UTC 23:30 = KST +1 day 08:30. OK.

    const status = makeStatusWithStale(3, 7);
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("all");

    await waitFor(() =>
      expect(screen.getByTestId("stale-context-label")).toBeInTheDocument(),
    );
    const label = screen.getByTestId("stale-context-label");
    expect(label).toHaveTextContent(/거래량|관찰/);
    expect(label.className).toMatch(/yellow/);
  });

  // C18-S4: stale=0 → 컨텍스트 라벨 미노출
  it("C18-S4: stale=0 → 컨텍스트 라벨 미노출", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T01:00:00Z")); // KST 10:00 메인

    const status = makeStatusWithStale(0, 15);
    server.use(http.get("/api/trading/status", () => HttpResponse.json(status)));

    await renderScanMonitor("all");

    // tick-coverage-badge 는 노출되나, stale-context-label 은 미노출
    await waitFor(() =>
      expect(screen.queryByTestId("tick-coverage-badge")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("stale-context-label")).not.toBeInTheDocument();
  });

  // C18-S5: 끊김 펼치기 토글 → last_tick_map 기반 종목별 시각 표시
  it("C18-S5: 끊김 펼치기 → last_tick_map 종목별 마지막 시각 표시", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-05-19T07:40:00Z")); // KST 16:40 NXT 애프터

    const status = makeStatusWithStale(2, 0);
    const subsResp = makeSubscriptionsResponse(
      ["005930", "000660"],
      {
        "005930": "2026-05-19T15:25:43+09:00",
        "000660": null,  // 미수신
      },
    );
    server.use(
      http.get("/api/trading/status", () => HttpResponse.json(status)),
      http.get("/api/realtime/subscriptions", () => HttpResponse.json(subsResp)),
    );

    await renderScanMonitor("all");

    // 펼치기 토글 찾고 클릭
    const expandBtn = await screen.findByTestId("stale-list-toggle");
    await userEvent.click(expandBtn);

    // 005930 → 마지막 15:25:43 (KST hh:mm:ss)
    await waitFor(() => {
      const row5930 = screen.getByTestId("stale-row-005930");
      expect(row5930).toHaveTextContent(/005930/);
      expect(row5930).toHaveTextContent(/15:25:43/);
    });
    // 000660 → 마지막 "—"
    const row660 = screen.getByTestId("stale-row-000660");
    expect(row660).toHaveTextContent(/000660/);
    expect(row660).toHaveTextContent(/—/);
  });
});
