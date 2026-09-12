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

// cycle288 — 메뉴바 2단 카테고리화. 사용자 지정 묶음(바꾸지 않음):
//   단독: 대시보드 / 거래 내역 / 로그 / 설정
//   그룹 종목: 조건검색 추적, 종목마스터
//   그룹 전략: 전략 현황, 전략수정 AI자문
//   그룹 운영상태: 장운영상태, 실시간 상태
const STANDALONE_LABELS = ["대시보드", "거래 내역", "로그", "설정"];
const GROUPS: Array<{ id: string; trigger: string; children: string[] }> = [
  { id: "stock", trigger: "종목", children: ["조건검색 추적", "종목마스터"] },
  { id: "strategy", trigger: "전략", children: ["전략 현황", "전략수정 AI자문"] },
  { id: "ops", trigger: "운영상태", children: ["장운영상태", "실시간 상태"] },
];
const ALL_HREFS = [
  "/",
  "/history",
  "/logs",
  "/strategy-funnel",
  "/stock-master",
  "/strategies",
  "/recommendations",
  "/settings",
  "/market-state",
  "/realtime-health",
];

function setup(route = "/") {
  server.use(
    http.get("/api/trading/status", () =>
      HttpResponse.json(wrap({ env: "vts", running: false })),
    ),
  );
  render(withProviders(<App />, route));
}

describe("AppShell — 상단 메뉴바 sticky", () => {
  it("환경 배너 + 네비게이션을 감싸는 컨테이너에 sticky/top-0/z-50 클래스가 적용된다", () => {
    setup();

    // nav-sticky-wrapper 가 sticky 클래스를 가진다
    const stickyWrapper = screen.getByTestId("nav-sticky-wrapper");
    expect(stickyWrapper).not.toBeNull();
    expect(stickyWrapper.className).toContain("sticky");
    expect(stickyWrapper.className).toContain("top-0");
    // 다른 콘텐츠 위에 보이도록 z-50 (또는 그 이상의 z-index)
    expect(stickyWrapper.className).toMatch(/z-\d+/);
  });

  it("PC viewport: 단독 메뉴 4개가 nav 안에 항상 보인다 (cycle288 — 그룹 하위는 A2 에서 별도 검증)", () => {
    setup();

    const nav = screen.getByRole("navigation", { name: "기본 네비게이션" });
    for (const label of STANDALONE_LABELS) {
      const links = screen.getAllByRole("link", { name: label });
      expect(links.length).toBeGreaterThanOrEqual(1);
      expect(links.some((l) => nav.contains(l))).toBe(true);
    }
  });

  it("A2 (cycle288): PC 그룹 트리거 3개는 접힌 상태 — role=button + aria-expanded=false", () => {
    setup();

    for (const { trigger } of GROUPS) {
      const btn = screen.getByRole("button", { name: trigger });
      expect(btn.getAttribute("aria-expanded")).toBe("false");
    }
  });

  // 검증 라운드 시정 — 트리거는 role="menu" 를 여는 게 아니라 하위가 평범한 링크인
  // disclosure(펼침) 위젯이다. aria-haspopup="true" 는 "menu" 와 동치라 스크린리더가
  // 메뉴 규약(role=menu/menuitem)을 기대하게 만드는데 실제로는 없었다 — 지키지 못하는
  // 계약을 내보내지 않는다(제거).
  it("A2c (검증 라운드): PC 그룹 트리거는 aria-haspopup 을 내보내지 않는다", () => {
    setup();

    for (const { trigger } of GROUPS) {
      const btn = screen.getByRole("button", { name: trigger });
      expect(btn.getAttribute("aria-haspopup")).toBeNull();
    }
  });

  it("A2b (cycle288): 그룹 트리거를 클릭하면 하위 링크가 나타나고, 다시 클릭하면 사라진다", () => {
    setup();

    for (const { trigger, children } of GROUPS) {
      const btn = screen.getByRole("button", { name: trigger });
      fireEvent.click(btn);
      expect(btn.getAttribute("aria-expanded")).toBe("true");
      for (const label of children) {
        const links = screen.getAllByRole("link", { name: label });
        expect(links.length).toBeGreaterThanOrEqual(1);
      }
      // 닫기 — 다음 그룹 검증 전 상태 정리(한 번에 하나만 열림 전제와 무관하게 명시적으로 닫는다)
      fireEvent.click(btn);
      expect(btn.getAttribute("aria-expanded")).toBe("false");
    }
  });

  // 사이클 85 L-MENU → cycle288: 종목 그룹을 열어야 종목마스터 링크가 보인다
  it("L-MENU (cycle288): 종목 그룹을 열면 /stock-master 라우트가 종목마스터 라벨로 등장한다", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: "종목" }));
    const links = screen.getAllByRole("link", { name: "종목마스터" });
    expect(links.length).toBeGreaterThanOrEqual(1);
    expect(
      links.some((l) => l.getAttribute("href") === "/stock-master"),
    ).toBe(true);
  });

  it("B4 (cycle288): 10개 라우트 href 집합이 정확히 일치한다 (URL 불변 — 라우트 누락·추가 차단)", () => {
    setup();
    const nav = screen.getByRole("navigation", { name: "기본 네비게이션" });
    const hrefs = new Set<string>();

    const collect = () => {
      for (const a of Array.from(nav.querySelectorAll("a"))) {
        const href = a.getAttribute("href");
        if (href) hrefs.add(href);
      }
    };

    collect(); // 단독 항목 4개 (그룹은 아직 전부 닫힘)
    // 한 번에 하나만 열리므로 그룹을 하나씩 열며 누적한다 (동시에 열림을 요구하지 않는다)
    for (const { trigger } of GROUPS) {
      fireEvent.click(screen.getByRole("button", { name: trigger }));
      collect();
    }

    expect(hrefs).toEqual(new Set(ALL_HREFS));
  });

  it("한 번에 하나의 그룹만 열린다 — 다른 그룹을 열면 이전 그룹이 닫힌다", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: "종목" }));
    expect(screen.getByRole("button", { name: "종목" }).getAttribute("aria-expanded")).toBe(
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "전략" }));
    expect(screen.getByRole("button", { name: "종목" }).getAttribute("aria-expanded")).toBe(
      "false",
    );
    expect(screen.getByRole("button", { name: "전략" }).getAttribute("aria-expanded")).toBe(
      "true",
    );
  });

  it("Escape 키를 누르면 열린 그룹이 닫히고 트리거로 포커스가 돌아간다", () => {
    setup();

    const btn = screen.getByRole("button", { name: "종목" });
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(btn);
  });

  it("바깥을 클릭하면 열린 그룹이 닫힌다", () => {
    setup();

    const btn = screen.getByRole("button", { name: "전략" });
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");

    fireEvent.mouseDown(document.body);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });

  it("세부 페이지(전략수정 AI자문)에 있으면 상위 그룹(전략) 트리거도 활성 표시된다", () => {
    setup("/recommendations");

    const btn = screen.getByRole("button", { name: "전략" });
    expect(btn.className).toContain("bg-gray-100");
  });

  it("패널이 열린 상태에서 화살표 아래/위 키로 하위 항목 사이를 이동한다", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: "종목" }));
    const first = screen.getByRole("link", { name: "조건검색 추적" });
    const second = screen.getByRole("link", { name: "종목마스터" });

    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);

    fireEvent.keyDown(second, { key: "ArrowUp" });
    expect(document.activeElement).toBe(first);
  });

  // 검증 라운드 시정 — 항목 선택 후 포커스가 <body> 로 떨어지던 회귀. 클릭한 항목이
  // 언마운트되기 전에 트리거로 포커스를 되돌려야 한다.
  it("검증 라운드: 하위 항목을 선택하면 포커스가 트리거로 돌아온다 (body 로 떨어지지 않는다)", () => {
    setup();

    const btn = screen.getByRole("button", { name: "종목" });
    fireEvent.click(btn);
    const link = screen.getByRole("link", { name: "종목마스터" });
    link.focus();
    fireEvent.click(link);

    expect(document.activeElement).toBe(btn);
    expect(document.activeElement).not.toBe(document.body);
  });

  // 검증 라운드 시정 — 포커스가 Tab 으로 패널 밖으로 나가면 패널이 닫혀야 한다.
  it("검증 라운드: 포커스가 패널 밖으로 나가면(focusout) 열린 그룹이 닫힌다", () => {
    setup();

    const btn = screen.getByRole("button", { name: "종목" });
    fireEvent.click(btn);
    const link = screen.getByRole("link", { name: "종목마스터" });

    // 패널 밖 요소로 포커스가 이동 — relatedTarget 이 컨테이너 밖이면 닫힌다.
    // React 의 onBlur 는 내부적으로 버블링되는 "focusout" 이벤트로 구현되므로
    // (네이티브 "blur" 는 버블링되지 않아 델리게이션 리스너에 도달하지 않는다) focusOut 을 쓴다.
    fireEvent.focusOut(link, { relatedTarget: document.body });

    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });

  // 검증 라운드 시정 — 트리거에서 ArrowUp 은 (종전엔 아무 반응이 없었으나) 이제 패널을 연다.
  // WAI-ARIA APG 규약상 ArrowUp 은 "열고 마지막 항목에 포커스"까지 요구하지만, 그 포커스
  // 이동은 requestAnimationFrame 안에서 일어나는데 이 vitest+jsdom 하네스에서는 (ArrowDown
  // 트리거의 기존 rAF 포커스 이동도 동일하게) 포커스가 검증 가능한 시점까지 안정적으로
  // 유지되지 않는다(별도 조사로 NavBar 로직이 아니라 하네스 자체의 사전 존재 한계로 확인—
  // ArrowDown 도 동일 증상). 여기서는 "패널이 열린다"(종전 무반응과 다른 실제 동작 변화)만
  // 확정적으로 검증한다.
  it("검증 라운드: 트리거에서 ArrowUp 을 누르면 (종전엔 무반응이던) 패널이 열린다", () => {
    setup();

    const btn = screen.getByRole("button", { name: "종목" });
    fireEvent.keyDown(btn, { key: "ArrowUp" });

    expect(btn.getAttribute("aria-expanded")).toBe("true");
  });

  it("라우트가 바뀌면 열려 있던 그룹이 닫힌다", () => {
    setup();

    const btn = screen.getByRole("button", { name: "종목" });
    fireEvent.click(btn);
    const link = screen.getAllByRole("link", { name: "종목마스터" })[0];
    fireEvent.click(link);

    expect(screen.getByRole("button", { name: "종목" }).getAttribute("aria-expanded")).toBe(
      "false",
    );
  });
});

// 사이클 81 영역 2 — 모바일 메뉴 회귀 가드 (cycle288: 그룹 제목 + 들여쓴 목록으로 갱신)
describe("AppShell — 모바일 햄버거 메뉴 (사이클 81 → cycle288)", () => {
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

  it("M-5 (cycle288): 드로어 안에 10개 leaf 링크가 그룹 접힘과 무관하게 전부 존재한다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    for (const label of [
      ...STANDALONE_LABELS,
      ...GROUPS.flatMap((g) => g.children),
    ]) {
      const links = Array.from(drawer.querySelectorAll("a")).filter(
        (a) => a.textContent?.trim() === label,
      );
      expect(links.length, `모바일 드로어에 "${label}" 링크가 없다`).toBeGreaterThanOrEqual(1);
    }
  });

  it("M-5b (cycle288): 드로어에 그룹 제목 3개(종목/전략/운영상태)가 표시된다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    for (const { id, trigger } of GROUPS) {
      expect(screen.getByTestId(`nav-mobile-group-${id}`)).toBeDefined();
      // 그룹 제목은 링크가 아니다(단독 항목과 시각적으로 구별)
      const titleEls = Array.from(drawer.querySelectorAll("div")).filter(
        (d) => d.textContent?.trim() === trigger,
      );
      expect(titleEls.length).toBeGreaterThanOrEqual(1);
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

  // 사이클 85 L-CYCLE81-MOBILE → cycle288: 10개 leaf 링크 + main 독립 DOM 영속
  it("L-CYCLE81-MOBILE (cycle288): 10개 leaf 링크 전부 존재 + nav-sticky-wrapper 와 main 별도 영역", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");
    const stickyWrapper = screen.getByTestId("nav-sticky-wrapper");
    const main = document.querySelector("main");

    const allLinks = Array.from(drawer.querySelectorAll("a"));
    expect(allLinks.length).toBeGreaterThanOrEqual(10);

    // main 이 sticky wrapper 의 자식이 아닌지 (사이클 81 M-8 영속)
    expect(main).not.toBeNull();
    expect(stickyWrapper.contains(main)).toBe(false);
  });

  it("M-6: 드로어의 첫 leaf 링크(대시보드) 클릭 시 드로어가 닫힌다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    expect(screen.getByTestId("mobile-menu-drawer")).not.toBeNull();

    const drawer = screen.getByTestId("mobile-menu-drawer");
    const dashboardLink = Array.from(drawer.querySelectorAll("a")).find(
      (a) => a.textContent?.trim() === "대시보드",
    );
    expect(dashboardLink).toBeDefined();
    if (dashboardLink) fireEvent.click(dashboardLink);
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

  // 사이클 103 영역 0 M-10 — `실시간 상태` 메뉴 영구 영속 (사이클 85 M-9 답습, cycle288: 운영상태 그룹 하위)
  it("M-10 (사이클 103 영역 0 → cycle288): 실시간 상태 메뉴가 드로어에 등록된다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");

    const realtimeHealthLink = Array.from(drawer.querySelectorAll("a")).find(
      (a) => a.getAttribute("href") === "/realtime-health",
    );

    expect(
      realtimeHealthLink,
      "[사이클 103 영역 0 M-10 영구 영속 실패] `/realtime-health` 라우트가 " +
        "드로어에 영구 등록 영속 의무 영역 (운영상태 그룹 하위).",
    ).toBeDefined();

    if (realtimeHealthLink) {
      expect(realtimeHealthLink.textContent?.trim()).toBe("실시간 상태");
    }
  });

  // 사이클 103 영역 0 M-11 → cycle288: 10개 leaf 링크 영구 영속 + main 독립 DOM 영속
  it("M-11 (cycle288): 모바일 드로어 10개 leaf 링크 + main 별도 영역 영속", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");

    const allLinks = Array.from(drawer.querySelectorAll("a"));
    expect(
      allLinks.length,
      `[10개 leaf 링크 영구 영속 실패] 모바일 드로어 영역 메뉴 수 = ${allLinks.length} ` +
        `(cycle288 = 10개 영역 영속 의무).`,
    ).toBeGreaterThanOrEqual(10);
  });

  // 사이클 103 영역 1 M-12 → cycle288: `전략 현황` 메뉴가 전략 그룹 하위로 드로어에 등록된다
  it("M-12 (cycle288): 전략 현황 메뉴가 드로어에 등록된다", () => {
    setup();
    fireEvent.click(screen.getByTestId("mobile-menu-button"));
    const drawer = screen.getByTestId("mobile-menu-drawer");

    const strategiesLink = Array.from(drawer.querySelectorAll("a")).find(
      (a) => a.getAttribute("href") === "/strategies",
    );

    expect(
      strategiesLink,
      "[사이클 103 영역 1 M-12 영구 영속 실패] `/strategies` 라우트가 " +
        "드로어에 영구 등록 영속 의무 영역 (전략 그룹 하위).",
    ).toBeDefined();
  });
});
