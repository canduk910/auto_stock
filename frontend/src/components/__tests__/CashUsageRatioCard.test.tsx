/**
 * J3 Red (2026-05-12) — `CashUsageRatioCard` 컴포넌트.
 *
 * Settings 페이지 비중 슬라이더 *하단* 에 신설되는 카드.
 *
 * 요구 행위:
 * 1. 초기 로드 시 GET `/api/strategies/system/cash-usage-ratio` → 슬라이더 값에 반영.
 * 2. 슬라이더 range 50~100, step 5 — 5% 단위.
 * 3. 우측에 % 표시 (예: `80%`).
 * 4. 슬라이더 변경 + 저장(commit) 시 PUT `/api/strategies/system/cash-usage-ratio` 호출.
 * 5. 안내 문구 "다음 영업일부터 반영" 노출.
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import CashUsageRatioCard from "../CashUsageRatioCard";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("CashUsageRatioCard", () => {
  it("초기 로드 시 GET 호출 결과를 슬라이더 % 에 표시", async () => {
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 1.0 })),
      ),
    );
    render(
      <TestProviders>
        <CashUsageRatioCard />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("cash-usage-ratio-percent").textContent).toContain("100%");
    });
  });

  it("초기 ratio=0.8 → 슬라이더 80% 노출", async () => {
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 0.8 })),
      ),
    );
    render(
      <TestProviders>
        <CashUsageRatioCard />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("cash-usage-ratio-percent").textContent).toContain("80%");
    });
  });

  it("range 50~100, step 5 속성 확인", async () => {
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 1.0 })),
      ),
    );
    render(
      <TestProviders>
        <CashUsageRatioCard />
      </TestProviders>,
    );

    const slider = await screen.findByTestId("cash-usage-ratio-slider");
    expect(slider).toHaveAttribute("min", "50");
    expect(slider).toHaveAttribute("max", "100");
    expect(slider).toHaveAttribute("step", "5");
  });

  it("안내 문구 '다음 영업일부터 반영' 노출", async () => {
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 1.0 })),
      ),
    );
    render(
      <TestProviders>
        <CashUsageRatioCard />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getByText(/다음 영업일부터 반영/)).toBeInTheDocument();
    });
  });

  it("저장 버튼 클릭 시 PUT 호출 + 응답 ratio 반영", async () => {
    let putCalled = false;
    let receivedBody: unknown = null;
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 1.0 })),
      ),
      http.put("/api/strategies/system/cash-usage-ratio", async ({ request }) => {
        putCalled = true;
        receivedBody = await request.json();
        return HttpResponse.json(wrap({ ratio: 0.8 }));
      }),
    );

    render(
      <TestProviders>
        <CashUsageRatioCard />
      </TestProviders>,
    );

    const slider = await screen.findByTestId("cash-usage-ratio-slider");
    fireEvent.change(slider, { target: { value: "80" } });

    const saveBtn = screen.getByTestId("cash-usage-ratio-save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(putCalled).toBe(true);
    });
    expect(receivedBody).toEqual({ ratio: 0.8 });
  });
});
