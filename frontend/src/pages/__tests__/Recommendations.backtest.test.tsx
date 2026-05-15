/**
 * Phase 4 (2026-05-16) — Recommendations 페이지가 backtest_summary 를 받으면
 * BacktestComparisonCard 를 자기 전략 카드에 노출하는지 검증.
 *
 * - backtest_summary null 이면 카드 placeholder (미실행 안내) 노출
 * - backtest_summary 있으면 정상 비교 카드 노출
 * - 기존 J4 자산 배정 카드는 회귀 없이 그대로 노출 유지
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Recommendations from "../Recommendations";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

function makeMetrics(over: Record<string, number> = {}) {
  return {
    total_return_pct: 10.0,
    cagr: 7.5,
    sharpe_ratio: 1.0,
    sortino_ratio: 1.2,
    max_drawdown: -8.0,
    win_rate: 0.5,
    profit_factor: 1.5,
    total_trades: 30,
    ...over,
  };
}

function makeRec(over: Record<string, unknown> = {}) {
  return {
    id: "R1",
    created_at: "2026-05-16T20:05:00+09:00",
    target_date: "2026-05-16",
    strategy_id: "momentum",
    status: "pending",
    current_params: { position_ratio: 0.25 },
    recommended_params: { position_ratio: 0.3 },
    applied_params: null,
    reasoning: "테스트 자문",
    metrics: { trades_count: 10, win_rate: 0.55 },
    applied_at: null,
    rejected_at: null,
    recommended_weight: null,
    code_review_notes: null,
    applied_weight: null,
    backtest_summary: null,
    ...over,
  };
}

function setupStrategies() {
  server.use(
    http.get("/api/strategies", () =>
      HttpResponse.json(
        wrap({
          momentum: {
            name: "모멘텀",
            enabled: true,
            weight: 0.25,
            params: {},
            invested_amount: 0,
            min_weight: 0,
            total_investment: 5_000_000,
          },
        }),
      ),
    ),
  );
}

describe("Recommendations 페이지 — Phase 4 백테스트 카드 통합", () => {
  it("backtest_summary == null 이면 placeholder 카드 노출 (미실행 안내)", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(wrap([makeRec({ backtest_summary: null })])),
      ),
    );

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("backtest-comparison-card-momentum")).toBeInTheDocument();
    });
    expect(screen.getByTestId("backtest-comparison-card-momentum").textContent).toMatch(
      /백테스트 미실행|진행중|아직/,
    );
  });

  it("backtest_summary 있으면 8 메트릭 비교 카드 정상 노출", async () => {
    setupStrategies();
    const summary = {
      current: { momentum: makeMetrics({ total_return_pct: 10.0 }) },
      recommended: { momentum: makeMetrics({ total_return_pct: 15.5 }) },
      diff: { momentum: { total_return_pct: 5.5 } },
    };
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(wrap([makeRec({ backtest_summary: summary })])),
      ),
    );

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    );

    await waitFor(() => {
      const card = screen.getByTestId("backtest-comparison-card-momentum");
      expect(card.textContent).toContain("10.00");
      expect(card.textContent).toContain("15.50");
    });
  });

  it("backtest_summary + recommended_weight 동시 존재 — 두 카드 모두 노출 (J4 회귀)", async () => {
    setupStrategies();
    const summary = {
      current: { momentum: makeMetrics() },
      recommended: { momentum: makeMetrics({ total_return_pct: 13.5 }) },
      diff: { momentum: { total_return_pct: 3.5 } },
    };
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              backtest_summary: summary,
              recommended_weight: 0.35,
            }),
          ]),
        ),
      ),
    );

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    );

    await waitFor(() => {
      // 백테스트 비교 카드
      expect(screen.getByTestId("backtest-comparison-card-momentum")).toBeInTheDocument();
      // J4 자산 배정 카드 회귀 가드
      expect(screen.getByTestId("weight-card-R1")).toBeInTheDocument();
    });
  });
});
