/**
 * ScanMonitor tick_coverage 색상 표시 (G3 프론트, 2026-05-12).
 *
 * 기존 `구독 중인 종목: N개` 표시 보존 + 옆/하단에 보조 정보 추가:
 *   `fresh: 23 / stale: 4 / acked: 25 / limit: 41`
 *
 * 색상 규칙(stale 카운트 기반):
 *   stale === 0  → 기본 (회색/검정)
 *   stale 1~5    → yellow 배지 (Tailwind `bg-yellow-*` / `text-yellow-*`)
 *   stale > 5    → red 배지   (Tailwind `bg-red-*` / `text-red-*`)
 *
 * 한도 근접도 진행바 (선택):
 *   total/limit 비율, 80%+ 면 amber 톤
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import ScanMonitor from "../ScanMonitor";

function makeStatus(overrides: { stale?: number; fresh?: number; acked?: number; total?: number } = {}) {
  const total = overrides.total ?? 27;
  const stale = overrides.stale ?? 0;
  const fresh = overrides.fresh ?? Math.max(0, total - stale);
  const acked = overrides.acked ?? Math.max(0, total - 2);
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
      last_scan_time: "2026-05-12T09:30:00",
      ticker_names: {},
      ticker_prices: {},
      ticker_market_info: {},
      tick_coverage_total: total,
      tick_coverage_acked: acked,
      tick_coverage_fresh: fresh,
      tick_coverage_stale: stale,
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
    strategies: {},
  });
}

async function renderScanMonitor(scenarioStatus: ReturnType<typeof makeStatus>) {
  server.use(
    http.get("/api/trading/status", () => HttpResponse.json(scenarioStatus))
  );

  render(
    <TestProviders>
      <TradingStatusProvider>
        <ScanMonitor selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>
  );

  // 폴링 첫 응답 도착 대기
  await screen.findByText(/구독 중/);
}

describe("ScanMonitor — tick_coverage 색상 표시 (G3)", () => {
  // -------------------------------------------------------------------------
  // Case L — stale=0 → 노랑/빨강 배지 없음
  // -------------------------------------------------------------------------
  it("Case L: stale=0 이면 노란/빨간 배지가 보이지 않는다", async () => {
    await renderScanMonitor(makeStatus({ total: 30, stale: 0, fresh: 30, acked: 28 }));

    // stale 카운트가 텍스트로 노출되어야 함 (보조 정보)
    const staleText = await screen.findByText(/stale:\s*0/i);
    expect(staleText).toBeInTheDocument();

    // 색상 배지는 yellow/red 클래스 미포함 — 부모 컨테이너의 className 검증
    const badge = staleText.closest('[data-testid="tick-coverage-badge"]') as HTMLElement | null;
    expect(badge).not.toBeNull();
    if (badge) {
      expect(badge.className).not.toMatch(/yellow/);
      expect(badge.className).not.toMatch(/red/);
    }
  });

  // -------------------------------------------------------------------------
  // Case M — stale=3 → yellow 배지
  // -------------------------------------------------------------------------
  it("Case M: stale=3 이면 yellow 배지가 적용된다", async () => {
    await renderScanMonitor(makeStatus({ total: 30, stale: 3, fresh: 27, acked: 26 }));

    const staleText = await screen.findByText(/stale:\s*3/i);
    const badge = staleText.closest('[data-testid="tick-coverage-badge"]') as HTMLElement | null;
    expect(badge).not.toBeNull();
    if (badge) {
      expect(badge.className).toMatch(/yellow/);
      expect(badge.className).not.toMatch(/red/);
    }
  });

  // -------------------------------------------------------------------------
  // Case N — stale=10 → red 배지
  // -------------------------------------------------------------------------
  it("Case N: stale=10 이면 red 배지가 적용된다", async () => {
    await renderScanMonitor(makeStatus({ total: 30, stale: 10, fresh: 20, acked: 20 }));

    const staleText = await screen.findByText(/stale:\s*10/i);
    const badge = staleText.closest('[data-testid="tick-coverage-badge"]') as HTMLElement | null;
    expect(badge).not.toBeNull();
    if (badge) {
      expect(badge.className).toMatch(/red/);
    }
  });

  // -------------------------------------------------------------------------
  // Case O — 진행바 amber 톤 (total/limit ≥ 80%)
  // -------------------------------------------------------------------------
  it("Case O: total/limit ≥ 80% 면 진행바 amber 톤", async () => {
    // limit=41, total=33 → 33/41 ≈ 80.5%
    await renderScanMonitor(makeStatus({ total: 33, stale: 0, fresh: 33, acked: 33 }));

    // 진행바는 data-testid="tick-coverage-progress" 노출
    const progress = await screen.findByTestId("tick-coverage-progress");
    expect(progress).toBeInTheDocument();
    expect(progress.className).toMatch(/amber/);
  });

  // -------------------------------------------------------------------------
  // 기존 `구독 중인 종목: N개` 표시 보존 (회귀 가드)
  // -------------------------------------------------------------------------
  it("기존 subscribed_count 표시는 보존된다 (회귀 가드)", async () => {
    await renderScanMonitor(makeStatus({ total: 27, stale: 0, fresh: 27, acked: 25 }));

    // "구독 중" 레이블이 그대로 노출되어야 함 (기존 표시 보존)
    expect(screen.getByText(/구독 중/)).toBeInTheDocument();
    // 27 카운트는 텍스트가 분리되어 노출되므로 (예: 'fresh: 27'),
    // findByText 로 polling 응답 도착 대기 후 검증.
    await screen.findByText(/fresh:\s*27/i);
  });
});
