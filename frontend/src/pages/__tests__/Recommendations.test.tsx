/**
 * Phase J4 (2026-05-12) — Recommendations 페이지의 자산 배정 + 로직 자문 카드.
 *
 * 요구 행위:
 * 1. recommended_weight 가 null 아니면 "자산 배정" 카드 노출 — 현재→추천 weight + 변경량(%p) + "weight 적용" 체크박스.
 * 2. recommended_weight 가 null 이면 자산 배정 카드 미노출.
 * 3. code_review_notes 가 null 아니면 "로직/파라미터 자문" 카드 노출 — 자유 텍스트.
 * 4. code_review_notes 가 null 이면 자문 카드 미노출.
 * 5. weight 적용 체크박스 토글 시 apply 호출의 apply_weight 옵션 true 로 전달.
 * 6. applied_weight 가 있으면 적용 결과 표시.
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Recommendations from "../Recommendations";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

function makeRec(overrides: Record<string, unknown> = {}) {
  return {
    id: "R1",
    created_at: "2026-05-12T16:00:00+09:00",
    target_date: "2026-05-12",
    strategy_id: "momentum",
    status: "pending",
    current_params: { position_ratio: 0.25 },
    recommended_params: { position_ratio: 0.3 },
    applied_params: null,
    reasoning: "비중을 올리는 것을 추천",
    metrics: { trades_count: 10, win_rate: 0.6 },
    applied_at: null,
    rejected_at: null,
    recommended_weight: null,
    code_review_notes: null,
    applied_weight: null,
    ...overrides,
  };
}

function setupStrategies() {
  // 백엔드는 `{momentum: {...}, ...}` 객체 형태로 반환 — getStrategies가 배열로 변환
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

describe("Recommendations — Phase J4 자산 배정 + 로직 자문 카드", () => {
  it("recommended_weight 가 있으면 자산 배정 카드가 노출된다", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({ recommended_weight: 0.35 }),
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
    // 현재 weight 와 추천 weight 모두 노출
    const card = screen.getByTestId("weight-card-R1");
    expect(card.textContent).toContain("25");  // 현재 weight 25%
    expect(card.textContent).toContain("35");  // 추천 weight 35%
  });

  it("recommended_weight 가 null 이면 자산 배정 카드가 노출되지 않는다", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(wrap([makeRec({ recommended_weight: null })])),
      ),
    );

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    );

    await waitFor(() => {
      // 페이지 로드 후 자문 표시는 됨 (강제 대기용)
      expect(screen.getByText(/모멘텀/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("weight-card-R1")).not.toBeInTheDocument();
  });

  it("code_review_notes 가 있으면 로직 자문 카드가 노출된다", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              code_review_notes: "신규 파라미터 도입 권고\n- ATR 기반 trailing\n- 변동성 컷오프",
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
      expect(screen.getByTestId("code-review-card-R1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("code-review-card-R1").textContent).toContain(
      "신규 파라미터 도입 권고",
    );
  });

  it("code_review_notes 가 null 이면 로직 자문 카드가 노출되지 않는다", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(wrap([makeRec({ code_review_notes: null })])),
      ),
    );

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getByText(/모멘텀/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("code-review-card-R1")).not.toBeInTheDocument();
  });

  it("weight 적용 체크박스 토글 시 apply 호출에 apply_weight=true 가 전달된다", async () => {
    setupStrategies();
    let capturedApplyBody: any = null;
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([makeRec({ recommended_weight: 0.35 })]),
        ),
      ),
      http.post("/api/recommendations/:id/apply", async ({ request }) => {
        capturedApplyBody = await request.json();
        return HttpResponse.json(wrap(null, "적용 완료"));
      }),
    );

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    );

    // 자산 배정 카드의 weight 체크박스 토글
    const weightCheckbox = await screen.findByTestId("weight-apply-checkbox-R1");
    fireEvent.click(weightCheckbox);

    // 적용 버튼 클릭
    const applyBtn = await screen.findByRole("button", { name: /선택 항목 적용/ });
    fireEvent.click(applyBtn);

    // ConfirmModal 의 확인 버튼 (정확히 "확인" — "선택 항목 적용" 과 중복 매칭 차단)
    const confirmBtn = await screen.findByRole("button", { name: "확인" });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(capturedApplyBody).not.toBeNull();
    });
    expect(capturedApplyBody.apply_weight).toBe(true);
  });

  it("applied_weight 가 있으면 적용 결과로 표시된다", async () => {
    setupStrategies();
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(
          wrap([
            makeRec({
              recommended_weight: 0.35,
              applied_weight: 0.35,
              status: "applied",
              applied_at: "2026-05-12T20:30:00+09:00",
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
      const card = screen.getByTestId("weight-card-R1");
      expect(card.textContent).toMatch(/적용됨|applied/i);
      expect(card.textContent).toContain("35");
    });
  });
});
