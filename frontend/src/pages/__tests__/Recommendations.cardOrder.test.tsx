/**
 * 사이클 1 (2026-05-17) — Recommendations 카드 순서 회귀 가드.
 *
 * 변경 전: BacktestComparison → 자산 배정 → 로직 자문 → 파라미터
 * 변경 후: 자산 배정 → BacktestComparison → 로직 자문 → 파라미터
 *
 * 자산 배정 카드를 최상단으로 이동 — 5/18 월 20:00 첫 자문 검수 시
 * 가장 먼저 보이는 운영 의사결정 지점은 비중 변경 권고이기 때문.
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Recommendations from "../Recommendations";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

function makeRichRec() {
  return {
    id: "R1",
    created_at: "2026-05-17T20:00:00+09:00",
    target_date: "2026-05-17",
    strategy_id: "momentum",
    status: "pending",
    current_params: { buy_threshold: 29.0 },
    recommended_params: { buy_threshold: 27.0 },
    applied_params: null,
    reasoning: "전략 점검",
    metrics: { trades_count: 5, win_rate: 0.6 },
    applied_at: null,
    rejected_at: null,
    // 4 카드 모두 렌더되도록 모든 필드 채움
    recommended_weight: 0.08,
    weight_reasoning: "비중 상향 권고",
    code_review_notes: "신규 파라미터 도입 권고",
    applied_weight: null,
    backtest_summary: {
      current: { momentum: null },
      recommended: { momentum: null },
      diff: {},
    },
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
            weight: 0.06,
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

describe("Recommendations 사이클 1 — 카드 순서", () => {
  it("자산 배정 → BacktestComparison → 로직 자문 → 파라미터 순서로 렌더된다", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(wrap([makeRichRec()])),
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
    const backtestCard = screen.getByTestId("backtest-comparison-card-momentum");
    const codeReviewCard = screen.getByTestId("code-review-card-R1");

    // weightCard < backtestCard
    expect(
      weightCard.compareDocumentPosition(backtestCard) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    // backtestCard < codeReviewCard
    expect(
      backtestCard.compareDocumentPosition(codeReviewCard) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    // 파라미터 표 — "권고 파라미터" 문자열 노드 찾아 비교
    const paramsHeading = screen.getByText(/권고 파라미터/);
    expect(
      codeReviewCard.compareDocumentPosition(paramsHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("자산 배정 카드 없어도 BacktestComparison → 로직 자문 → 파라미터 순서 유지", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            {
              ...makeRichRec(),
              recommended_weight: null,
              weight_reasoning: null,
            },
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
      expect(
        screen.getByTestId("backtest-comparison-card-momentum"),
      ).toBeInTheDocument();
    });

    const backtestCard = screen.getByTestId("backtest-comparison-card-momentum");
    const codeReviewCard = screen.getByTestId("code-review-card-R1");

    expect(
      backtestCard.compareDocumentPosition(codeReviewCard) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    // weight-card 는 미존재
    expect(screen.queryByTestId("weight-card-R1")).not.toBeInTheDocument();
  });
});
