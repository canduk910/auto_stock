import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen, fireEvent } from "@testing-library/react";
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

    // nav-sticky-wrapper 가 sticky 클래스를 가진다
    const stickyWrapper = screen.getByTestId("nav-sticky-wrapper");
    expect(stickyWrapper).not.toBeNull();
    expect(stickyWrapper.className).toContain("sticky");
    expect(stickyWrapper.className).toContain("top-0");
    // 다른 콘텐츠 위에 보이도록 z-50 (또는 그 이상의 z-index)
    expect(stickyWrapper.className).toMatch(/z-\d+/);
  });

  it("PC viewport: 네비게이션 메뉴 6개가 nav 안에 렌더링된다", () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(wrap({ env: "vts", running: false })),
      ),
    );

    render(withProviders(<App />));

    const nav = screen.getByRole("navigation", { name: "기본 네비게이션" });
    // 사이클 34 (2026-05-21) — "조건검색 추적" 메뉴 포함 6개
    for (const label of [
      "대시보드",
      "거래 내역",
      "전략수정 AI자문",
      "조건검색 추적",
      "로그",
      "설정",
    ]) {
      // PC 가로 메뉴와 모바일 드로어 양쪽에 링크가 존재 — getAllByRole 로 복수 허용
      const links = screen.getAllByRole("link", { name: label });
      expect(links.length).toBeGreaterThanOrEqual(1);
      expect(links.some((l) => nav.contains(l))).toBe(true);
    }
  });
});

// 사이클 81 영역 2 — 모바일 메뉴 회귀 가드
describe("AppShell — 모바일 햄버거 메뉴 (사이클 81)", () => {
  function setup(route = "/") {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(wrap({ env: "vts", running: false })),
      ),
    );
    render(withProviders(<App />, route));
  }

  it("M-1: 모바일 햄버거 버튼이 DOM에 존재한다", () => {
    setup();
    const btn = screen.getByTestId("mobile-menu-button");
    expect(btn).not.toBeNull();
  });

  it("M-2: 초기 상태에서 모바일 드로어가 숨겨져 있다", () => {
    setup();
    expect(screen.queryByTestId("mobile-menu-drawer")).toBeNull();
  });

  it("M-3: 햄버거 버튼 클릭 시 모바일 드로어가 열린다", () => {
    setup();
    const btn = screen.getByTestId("mobile-menu-button");
    fireEvent.click(btn);
    const drawer = screen.getByTestId("mobile-menu-drawer");
    expect(drawer).not.toBeNull();
  });

  it("M-4: 드로어 열린 상태에서 aria-expanded=true", () => {
    setup();
    const btn = screen.getByTestId("mobile-menu-button");
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
  });

  it("M-5: 드로어 안에 메뉴 6개 링크가 모두 존재한다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    for (const label of [
      "대시보드",
      "거래 내역",
      "전략수정 AI자문",
      "조건검색 추적",
      "로그",
      "설정",
    ]) {
      const links = Array.from(drawer.querySelectorAll("a")).filter(
        (a) => a.textContent?.trim() === label,
      );
      expect(links.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("M-6: 드로어 메뉴 링크 클릭 시 드로어가 닫힌다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    expect(screen.getByTestId("mobile-menu-drawer")).not.toBeNull();

    const drawer = screen.getByTestId("mobile-menu-drawer");
    const firstLink = drawer.querySelector("a");
    if (firstLink) fireEvent.click(firstLink);
    expect(screen.queryByTestId("mobile-menu-drawer")).toBeNull();
  });

  it("M-7: 드로어 열린 후 다시 버튼 클릭하면 닫힌다", () => {
    setup();
    const btn = screen.getByTestId("mobile-menu-button");
    fireEvent.click(btn); // 열기
    fireEvent.click(btn); // 닫기
    expect(screen.queryByTestId("mobile-menu-drawer")).toBeNull();
    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });

  it("M-8: 본문(main)이 nav-sticky-wrapper 와 별도 DOM 레벨에 존재한다 (overlap 없음)", () => {
    setup();
    const stickyWrapper = screen.getByTestId("nav-sticky-wrapper");
    const main = document.querySelector("main");
    expect(main).not.toBeNull();
    // main 이 sticky wrapper 의 자식이 아니어야 한다 (독립 영역)
    expect(stickyWrapper.contains(main)).toBe(false);
  });
});
