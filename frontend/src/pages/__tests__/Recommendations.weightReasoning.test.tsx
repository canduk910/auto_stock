/**
 * 사이클 1 (2026-05-17) — Recommendations 자산 배정 카드의 `weight_reasoning` 별도 영역.
 *
 * 요구 행위:
 * A. weight_reasoning 있으면 amber 배경 별도 영역 노출 (data-testid="weight-reasoning-{id}")
 * B. weight_reasoning=null 시 영역 미렌더
 * C. recommended_weight 가 null 이면 weight-card 자체 미노출 → reasoning 영역도 당연히 없음
 * D. 카드 순서 — 자산 배정 카드(weight-card)가 BacktestComparisonCard 보다 DOM 상 위에 있음
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Recommendations from "../Recommendations";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

function makeRec(overrides: Record<string, unknown> = {}) {
  return {
    id: "R1",
    created_at: "2026-05-17T20:00:00+09:00",
    target_date: "2026-05-17",
    strategy_id: "long_tail_volatility",
    status: "pending",
    current_params: { intraday_stop_loss: -3.0 },
    recommended_params: { intraday_stop_loss: -2.5 },
    applied_params: null,
    reasoning: "LTV 전략 점검",
    metrics: { trades_count: 8, win_rate: 0.5 },
    applied_at: null,
    rejected_at: null,
    recommended_weight: null,
    weight_reasoning: null,
    code_review_notes: null,
    applied_weight: null,
    backtest_summary: null,
    ...overrides,
  };
}

function setupStrategies() {
  server.use(
    http.get("/api/strategies", () =>
      HttpResponse.json(
        wrap({
          long_tail_volatility: {
            name: "LTV",
            enabled: true,
            weight: 0.26,
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

describe("Recommendations 사이클 1 — weight_reasoning 분리 표시", () => {
  it("A: weight_reasoning 이 있으면 amber 영역 별도 노출", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              recommended_weight: 0.18,
              weight_reasoning:
                "peer momentum/donchian 대비 누적 수익률 열위 + 손절률 증가로 본 전략 비중 0.26 → 0.18 축소 권고",
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
      expect(screen.getByTestId("weight-reasoning-R1")).toBeInTheDocument();
    });

    const reasoningEl = screen.getByTestId("weight-reasoning-R1");
    expect(reasoningEl.textContent).toContain("0.26");
    expect(reasoningEl.textContent).toContain("0.18");
    // amber 배경 클래스 확인 (정확한 클래스명 매칭)
    expect(reasoningEl.className).toMatch(/amber/);
  });

  it("B: weight_reasoning=null 이면 사유 영역 미렌더 (단, weight-card 자체는 노출)", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              recommended_weight: 0.18,
              weight_reasoning: null,
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

    // weight-card 노출 보장 (recommended_weight 있음)
    await waitFor(() => {
      expect(screen.getByTestId("weight-card-R1")).toBeInTheDocument();
    });
    // 사유 영역만 미렌더
    expect(screen.queryByTestId("weight-reasoning-R1")).not.toBeInTheDocument();
  });

  it("C: recommended_weight=null 이면 weight-card + reasoning 모두 미렌더", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              recommended_weight: null,
              weight_reasoning: null,
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
      // 자문 데이터 로드 완료 — 권고 파라미터 표가 렌더되면 자문 카드 자체는 렌더됨
      expect(screen.getByText(/권고 파라미터/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("weight-card-R1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("weight-reasoning-R1")).not.toBeInTheDocument();
  });

  it("D: weight-card 가 BacktestComparisonCard 보다 DOM 상 위에 위치한다 (카드 순서)", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              recommended_weight: 0.18,
              weight_reasoning: "축소 권고 사유",
              backtest_summary: {
                current: { long_tail_volatility: null },
                recommended: { long_tail_volatility: null },
                diff: {},
              },
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
      expect(screen.getByTestId("weight-card-R1")).toBeInTheDocument();
    });

    const weightCard = screen.getByTestId("weight-card-R1");
    const backtestCard = screen.getByTestId(
      "backtest-comparison-card-long_tail_volatility",
    );

    // DOMRect 비교 대신 compareDocumentPosition 사용 — jsdom 호환
    const position = weightCard.compareDocumentPosition(backtestCard);
    // weightCard 가 backtestCard 보다 먼저(앞에) 나와야 함
    // Node.DOCUMENT_POSITION_FOLLOWING = 4 — backtestCard 가 뒤에 있음
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("E: 1000자 weight_reasoning 도 영역에 표시(overflow 처리)", async () => {
    setupStrategies();
    const longText = "가".repeat(1000); // 정확히 1000자 (UTF-16 단위)
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              recommended_weight: 0.18,
              weight_reasoning: longText,
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
      expect(screen.getByTestId("weight-reasoning-R1")).toBeInTheDocument();
    });
    const el = screen.getByTestId("weight-reasoning-R1");
    expect(el.textContent && el.textContent.length).toBeGreaterThan(900);
    // max-h-32 + overflow-y-auto 클래스 적용
    expect(el.className).toMatch(/overflow-y-auto/);
    expect(el.className).toMatch(/max-h/);
  });
});
