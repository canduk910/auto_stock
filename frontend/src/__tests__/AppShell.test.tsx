import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import App from "../App";
import { wrap } from "../test/factories";
import { server } from "../test/server";

function withProviders(children: ReactNode, route = "/") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AppShell — 상단 메뉴바 sticky", () => {
  it("환경 배너 + 네비게이션을 감싸는 컨테이너에 sticky/top-0/z-50 클래스가 적용된다", () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(wrap({ env: "vts", running: false })),
      ),
    );

    render(withProviders(<App />));

    // 네비게이션 바 (role=navigation) 의 부모 wrapper 가 sticky 클래스를 가진다
    const nav = screen.getByRole("navigation");
    const stickyWrapper = nav.parentElement;
    expect(stickyWrapper).not.toBeNull();
    expect(stickyWrapper?.className).toContain("sticky");
    expect(stickyWrapper?.className).toContain("top-0");
    // 다른 콘텐츠 위에 보이도록 z-50 (또는 그 이상의 z-index)
    expect(stickyWrapper?.className).toMatch(/z-\d+/);
  });

  it("네비게이션 메뉴 5개가 sticky wrapper 안에 렌더링된다", () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(wrap({ env: "vts", running: false })),
      ),
    );

    render(withProviders(<App />));

    const nav = screen.getByRole("navigation");
    for (const label of [
      "대시보드",
      "거래 내역",
      "전략수정 AI자문",
      "일일 로그 분석",
      "설정",
    ]) {
      // 메뉴 링크가 nav 안에 있다
      const link = screen.getByRole("link", { name: label });
      expect(nav.contains(link)).toBe(true);
    }
  });
});
