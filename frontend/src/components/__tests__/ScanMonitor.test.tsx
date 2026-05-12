/**
 * ScanMonitor tick_coverage 색상 표시 (G3 프론트, 2026-05-12).
 *
 * 기존 `구독 중인 종목: N개` 표시 보존 + 옆/하단에 보조 정보 추가:
 *   `정상 23종목 · 끊김 4종목 · 등록 25종목` + 진행바 우측에 `27 / 41`
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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

    // 끊김 카운트가 한글 라벨로 노출되어야 함 (보조 정보)
    const staleText = await screen.findByText(/끊김\s*0종목/);
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

    const staleText = await screen.findByText(/끊김\s*3종목/);
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

    const staleText = await screen.findByText(/끊김\s*10종목/);
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
    // 한글 라벨 "정상 N종목" 노출 검증.
    await screen.findByText(/정상\s*27종목/);
    // 진행바 우측 한도 카운트 노출.
    expect(screen.getByText(/27\s*\/\s*41/)).toBeInTheDocument();
  });
});

// ===========================================================================
// J2 (2026-05-12) — stale 재구독 인라인 버튼
// ===========================================================================
describe("ScanMonitor — J2 stale 재구독 버튼", () => {
  // -------------------------------------------------------------------------
  // Case J2-F1 — stale > 0 일 때 재구독 버튼 노출
  // -------------------------------------------------------------------------
  it("Case J2-F1: stale=3 이면 '재구독' 버튼이 amber 톤으로 노출된다", async () => {
    await renderScanMonitor(makeStatus({ total: 30, stale: 3, fresh: 27, acked: 26 }));

    const button = await screen.findByRole("button", { name: /재구독/ });
    expect(button).toBeInTheDocument();
    // amber 톤 (border-amber 또는 text-amber)
    expect(button.className).toMatch(/amber/);
  });

  // -------------------------------------------------------------------------
  // Case J2-F2 — stale === 0 이면 버튼 미노출
  // -------------------------------------------------------------------------
  it("Case J2-F2: stale=0 이면 재구독 버튼이 노출되지 않는다", async () => {
    await renderScanMonitor(makeStatus({ total: 30, stale: 0, fresh: 30, acked: 28 }));

    // 끊김 0종목 텍스트는 보임 — 회귀 가드
    await screen.findByText(/끊김\s*0종목/);
    // 버튼은 절대 없음
    expect(screen.queryByRole("button", { name: /재구독/ })).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Case J2-F3 — 클릭 시 mutation 호출 + 성공 메시지 노출
  // -------------------------------------------------------------------------
  it("Case J2-F3: 버튼 클릭 시 POST /api/realtime/resubscribe 호출 + 완료 메시지", async () => {
    let postCalled = 0;
    server.use(
      http.post("/api/realtime/resubscribe", () => {
        postCalled += 1;
        return HttpResponse.json(
          wrap({ resubscribed: 3, tickers: ["000660", "005930", "035720"] })
        );
      })
    );

    await renderScanMonitor(makeStatus({ total: 30, stale: 3, fresh: 27, acked: 26 }));

    const button = await screen.findByRole("button", { name: /재구독/ });
    const user = userEvent.setup();
    await user.click(button);

    await waitFor(() => expect(postCalled).toBe(1));
    // 인라인 성공 메시지
    await screen.findByText(/3종목 재구독 완료/);
  });

  // -------------------------------------------------------------------------
  // Case J2-F4 — pending 중 disabled
  // -------------------------------------------------------------------------
  it("Case J2-F4: 호출 진행 중에는 버튼이 disabled 상태가 된다", async () => {
    let resolveResponse!: () => void;
    server.use(
      http.post("/api/realtime/resubscribe", async () => {
        await new Promise<void>((res) => {
          resolveResponse = res;
        });
        return HttpResponse.json(wrap({ resubscribed: 1, tickers: ["005930"] }));
      })
    );

    await renderScanMonitor(makeStatus({ total: 30, stale: 1, fresh: 29, acked: 28 }));

    const button = await screen.findByRole("button", { name: /재구독/ });
    const user = userEvent.setup();
    await user.click(button);

    // pending 중 disabled
    await waitFor(() =>
      expect((button as HTMLButtonElement).disabled).toBe(true)
    );

    // 응답 해제 후 정상 활성화 복귀(메시지 노출)
    resolveResponse();
    await screen.findByText(/1종목 재구독 완료/);
  });
});
