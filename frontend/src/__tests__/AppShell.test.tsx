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

  it("PC viewport: 네비게이션 메뉴 7개가 nav 안에 렌더링된다 (사이클 85 종목마스터 추가)", () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(wrap({ env: "vts", running: false })),
      ),
    );

    render(withProviders(<App />));

    const nav = screen.getByRole("navigation", { name: "기본 네비게이션" });
    // 사이클 85 (2026-06-09) — "종목마스터" 메뉴 포함 7개 (사이클 81 6 → 7 압축)
    for (const label of [
      "대시보드",
      "거래 내역",
      "전략수정 AI자문",
      "조건검색 추적",
      "종목마스터",
      "로그",
      "설정",
    ]) {
      // PC 가로 메뉴와 모바일 드로어 양쪽에 링크가 존재 — getAllByRole 로 복수 허용
      const links = screen.getAllByRole("link", { name: label });
      expect(links.length).toBeGreaterThanOrEqual(1);
      expect(links.some((l) => nav.contains(l))).toBe(true);
    }
  });

  // 사이클 85 L-MENU — 7번째 메뉴 `/stock-master` → `종목마스터` 라우트 존재
  it("L-MENU (사이클 85): /stock-master 라우트가 종목마스터 라벨로 navItems 에 등록된다", () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(wrap({ env: "vts", running: false })),
      ),
    );
    render(withProviders(<App />));

    // 명시적으로 href="/stock-master" 와 텍스트 "종목마스터" 모두 검증
    const links = screen.getAllByRole("link", { name: "종목마스터" });
    expect(links.length).toBeGreaterThanOrEqual(1);
    expect(
      links.some((l) => l.getAttribute("href") === "/stock-master"),
    ).toBe(true);
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

  it("M-5: 드로어 안에 메뉴 7개 링크가 모두 존재한다 (사이클 85 종목마스터 추가)", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    // 사이클 85 — 6 → 7 압축. "종목마스터" 신규 추가 (사이클 81 G-M5 영속 패턴 답습)
    for (const label of [
      "대시보드",
      "거래 내역",
      "전략수정 AI자문",
      "조건검색 추적",
      "종목마스터",
      "로그",
      "설정",
    ]) {
      const links = Array.from(drawer.querySelectorAll("a")).filter(
        (a) => a.textContent?.trim() === label,
      );
      expect(links.length).toBeGreaterThanOrEqual(1);
    }
  });

  // 사이클 85 M-9 — `종목마스터` 라벨 모바일 드로어 클릭 후 close (사이클 81 M-6 답습)
  it("M-9 (사이클 85): 종목마스터 메뉴 클릭 시 드로어가 닫힌다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    const stockMasterLink = Array.from(drawer.querySelectorAll("a")).find(
      (a) => a.textContent?.trim() === "종목마스터",
    );
    expect(stockMasterLink).toBeDefined();
    if (stockMasterLink) fireEvent.click(stockMasterLink);
    expect(screen.queryByTestId("mobile-menu-drawer")).toBeNull();
  });

  // 사이클 85 L-CYCLE81-MOBILE — 사이클 81 햄버거 메뉴 영속 (7개 메뉴 + main 독립 DOM)
  it("L-CYCLE81-MOBILE (사이클 85): 7개 메뉴 압축 후에도 nav-sticky-wrapper 와 main 별도 영역", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    const stickyWrapper = screen.getByTestId("nav-sticky-wrapper");
    const main = document.querySelector("main");

    // drawer 안에 메뉴 7개 모두 존재 (사이클 85 종목마스터 포함)
    const allLinks = Array.from(drawer.querySelectorAll("a"));
    expect(allLinks.length).toBeGreaterThanOrEqual(7);

    // main 이 sticky wrapper 의 자식이 아닌지 (사이클 81 M-8 영속)
    expect(main).not.toBeNull();
    expect(stickyWrapper.contains(main)).toBe(false);
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

  // 사이클 103 영역 0 M-10 — `실시간 상태` 8번째 메뉴 영구 영속 (사이클 85 M-9 답습)
  it("M-10 (사이클 103 영역 0): 실시간 상태 메뉴가 navItems 에 등록된다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");

    // 사이클 103 영역 0 = 8번째 메뉴 = `/realtime-health` 영역 영속 의무
    const realtimeHealthLink = Array.from(drawer.querySelectorAll("a")).find(
      (a) => a.getAttribute("href") === "/realtime-health",
    );

    expect(
      realtimeHealthLink,
      "[사이클 103 영역 0 M-10 영구 영속 실패] `/realtime-health` 라우트가 " +
        "navItems 에 영구 등록 영속 의무 영역 (8번째 메뉴 영역).",
    ).toBeDefined();

    if (realtimeHealthLink) {
      expect(realtimeHealthLink.textContent?.trim()).toBe("실시간 상태");
    }
  });

  // 사이클 103 영역 0 M-11 — 8개 메뉴 영구 영속 + main 독립 DOM 영속 (사이클 85 L-CYCLE81-MOBILE 답습)
  it("M-11 (사이클 103 영역 0): 모바일 드로어 8개 메뉴 + main 별도 영역 영속", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");

    // 사이클 103 영역 0 = 8개 메뉴 영구 영속 (기존 7개 + 실시간 상태)
    const allLinks = Array.from(drawer.querySelectorAll("a"));
    expect(
      allLinks.length,
      `[8개 메뉴 영구 영속 실패] 모바일 드로어 영역 메뉴 수 = ${allLinks.length} ` +
        `(사이클 103 영역 0 = 8개 영역 영속 의무).`,
    ).toBeGreaterThanOrEqual(8);
  });

  // 사이클 103 영역 1 M-12 — `전략 임계` 9번째 메뉴 영구 영속 (영역 1 통합)
  it("M-12 (사이클 103 영역 1): 전략 임계 메뉴가 navItems 에 등록된다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");

    // 사이클 103 영역 1 = 9번째 메뉴 = `/strategies` 영역 영속 의무
    const strategiesLink = Array.from(drawer.querySelectorAll("a")).find(
      (a) => a.getAttribute("href") === "/strategies",
    );

    expect(
      strategiesLink,
      "[사이클 103 영역 1 M-12 영구 영속 실패] `/strategies` 라우트가 " +
        "navItems 에 영구 등록 영속 의무 영역 (9번째 메뉴 영역).",
    ).toBeDefined();
  });
});
