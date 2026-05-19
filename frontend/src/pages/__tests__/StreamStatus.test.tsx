/**
 * StreamStatus 페이지 단위 테스트 (사이클 15-C-2, 2026-05-19).
 *
 * REST/WS/탈락 3 탭 + 새로고침 + 빈 상태 + 에러.
 *
 * 7 케이스:
 * 1. WS 탭 (기본) — ws 종목 행 렌더 + min_hold_remaining_secs 컬럼
 * 2. REST 탭 클릭 — rest 종목 행 렌더
 * 3. 탈락 탭 클릭 — dropped 종목 행 + cooldown_remaining_secs 컬럼
 * 4. 빈 카테고리 — EmptyMessage 노출
 * 5. 탭 카운트 표시 (REST=2, WS=3, 탈락=1)
 * 6. 새로고침 버튼 → refetch
 * 7. API 에러 → stream-error 노출
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import StreamStatus from "../StreamStatus";
import { TestProviders } from "../../test/providers";
import { server } from "../../test/server";

function setupMockResponse(payload: any) {
  server.use(
    http.get("/api/realtime/stream-status", () =>
      HttpResponse.json({ success: true, data: payload, message: "" }),
    ),
  );
}

const sampleData = {
  rest: [
    { ticker: "005930", strategy: "volatility_breakout", reason: "rest_observation", since_secs: 120 },
    { ticker: "000660", strategy: "long_tail_volatility", reason: "rest_observation", since_secs: 60 },
  ],
  ws: [
    {
      ticker: "079550",
      strategy: "volatility_breakout",
      reason: "distance_pct=0.2% (target=15830, current=15800)",
      since_secs: 30,
      min_hold_remaining_secs: 150,
    },
    {
      ticker: "066570",
      strategy: "long_tail_volatility",
      reason: "distance_pct=0.15%",
      since_secs: 90,
      min_hold_remaining_secs: 90,
    },
    {
      ticker: "035420",
      strategy: "bull_flag_breakout",
      reason: "distance_pct=0.3%",
      since_secs: 15,
      min_hold_remaining_secs: 165,
    },
  ],
  dropped: [
    {
      ticker: "012330",
      strategy: "vcp_breakout",
      reason: "signal_faded",
      since_secs: 60,
      cooldown_remaining_secs: 240,
    },
  ],
};


// ===========================================================================
// Case 1: WS 탭 (기본) — ws 종목 + min_hold_remaining_secs
// ===========================================================================
describe("StreamStatus page", () => {
  it("ws 탭 기본 렌더 + min_hold_remaining_secs 표시", async () => {
    setupMockResponse(sampleData);
    render(<StreamStatus />, { wrapper: TestProviders });

    // 기본 탭 = ws
    await waitFor(() => {
      expect(screen.getByTestId("stream-tab-ws")).toHaveAttribute("aria-selected", "true");
    });
    // ws 종목 3행 렌더
    expect(await screen.findByTestId("stream-row-ws-079550")).toBeInTheDocument();
    expect(screen.getByTestId("stream-row-ws-066570")).toBeInTheDocument();
    expect(screen.getByTestId("stream-row-ws-035420")).toBeInTheDocument();
    // min_hold_remaining_secs 컬럼 헤더
    expect(screen.getByText("최소 유지 남은시간")).toBeInTheDocument();
  });

  // =========================================================================
  // Case 2: REST 탭 클릭
  // =========================================================================
  it("REST 탭 클릭 → rest 종목 행", async () => {
    setupMockResponse(sampleData);
    render(<StreamStatus />, { wrapper: TestProviders });

    await screen.findByTestId("stream-tab-rest");
    fireEvent.click(screen.getByTestId("stream-tab-rest"));

    expect(await screen.findByTestId("stream-row-rest-005930")).toBeInTheDocument();
    expect(screen.getByTestId("stream-row-rest-000660")).toBeInTheDocument();
  });

  // =========================================================================
  // Case 3: 탈락 탭 클릭 — cooldown_remaining_secs 컬럼
  // =========================================================================
  it("탈락 탭 클릭 → dropped 행 + cooldown 컬럼", async () => {
    setupMockResponse(sampleData);
    render(<StreamStatus />, { wrapper: TestProviders });

    await screen.findByTestId("stream-tab-dropped");
    fireEvent.click(screen.getByTestId("stream-tab-dropped"));

    expect(await screen.findByTestId("stream-row-dropped-012330")).toBeInTheDocument();
    expect(screen.getByText("cooldown 남은시간")).toBeInTheDocument();
  });

  // =========================================================================
  // Case 4: 빈 카테고리
  // =========================================================================
  it("빈 카테고리 → EmptyMessage 노출", async () => {
    setupMockResponse({ rest: [], ws: [], dropped: [] });
    render(<StreamStatus />, { wrapper: TestProviders });

    // 기본 ws 탭 — 빈
    await screen.findByTestId("stream-tab-ws");
    expect(await screen.findByTestId("stream-empty-ws")).toBeInTheDocument();
  });

  // =========================================================================
  // Case 5: 탭 카운트 표시
  // =========================================================================
  it("탭 라벨에 카운트 노출 (REST=2, WS=3, 탈락=1)", async () => {
    setupMockResponse(sampleData);
    render(<StreamStatus />, { wrapper: TestProviders });

    await waitFor(() => {
      expect(screen.getByTestId("stream-tab-rest")).toHaveTextContent("(2)");
      expect(screen.getByTestId("stream-tab-ws")).toHaveTextContent("(3)");
      expect(screen.getByTestId("stream-tab-dropped")).toHaveTextContent("(1)");
    });
  });

  // =========================================================================
  // Case 6: 새로고침 버튼
  // =========================================================================
  it("새로고침 버튼 클릭 → refetch", async () => {
    let callCount = 0;
    server.use(
      http.get("/api/realtime/stream-status", () => {
        callCount += 1;
        return HttpResponse.json({ success: true, data: sampleData, message: "" });
      }),
    );

    render(<StreamStatus />, { wrapper: TestProviders });
    await screen.findByTestId("stream-refresh");
    const before = callCount;

    fireEvent.click(screen.getByTestId("stream-refresh"));

    await waitFor(() => {
      expect(callCount).toBeGreaterThan(before);
    });
  });

  // =========================================================================
  // Case 7: API 에러
  // =========================================================================
  it("API 500 → stream-error 노출", async () => {
    server.use(
      http.get("/api/realtime/stream-status", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );

    render(<StreamStatus />, { wrapper: TestProviders });

    expect(await screen.findByTestId("stream-error")).toBeInTheDocument();
  });
});
