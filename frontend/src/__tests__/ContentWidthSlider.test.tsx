import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import App from "../App";
import { wrap } from "../test/factories";
import { server } from "../test/server";

/**
 * 나브바 화면 폭 슬라이더 — Red 테스트 (T1~T5).
 *
 * 스펙: content_width_slider_spec.md
 * - AppShell 이 widthLevel(0~100, 기본 100) 상태 소유.
 * - localStorage 키 `autostock.contentWidth` 저장/복원.
 * - <main> 인라인 style.maxWidth = contentMaxWidth(level) = `max(1024px, ${60 + level*0.4}%)`.
 *   · level 100 → max(1024px, 100%) (전체폭 기본값)
 *   · level 0   → max(1024px, 60%)
 *   · level 40  → max(1024px, 76%)
 * - 슬라이더: data-testid="content-width-slider", aria-label="화면 폭 조정",
 *   min 0 / max 100 / step 5. PC 나브 행(hidden sm:flex)에만 노출.
 *
 * 실행: npx vitest run src/__tests__/ContentWidthSlider.test.tsx
 * 기대(Red): T1~T4 는 슬라이더/인라인 maxWidth 미구현으로 실패,
 *            T5(회귀 가드)는 기존 구조라 green 유지.
 */

const STORAGE_KEY = "autostock.contentWidth";

/**
 * 결정론적 in-memory localStorage 목.
 * Node 25 실험 localStorage 글로벌이 jsdom Storage 를 가려 `clear` 가 없는 환경 대응 —
 * 테스트가 저장/복원 단언을 안정적으로 수행하도록 window/globalThis 에 재설치한다.
 * (Green 구현도 `window.localStorage` 를 런타임 참조하므로 동일 목을 공유)
 */
function createStorageMock(): Storage {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = String(value);
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
    get length() {
      return Object.keys(store).length;
    },
  } as Storage;
}

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

function renderApp(route = "/") {
  // AppShell + main 은 라우트 무관하게 항상 렌더 — 기존 AppShell.test.tsx 패턴 답습.
  server.use(
    http.get("/api/trading/status", () =>
      HttpResponse.json(wrap({ env: "vts", running: false })),
    ),
  );
  render(withProviders(<App />, route));
}

describe("ContentWidthSlider — 나브바 화면 폭 슬라이더", () => {
  beforeEach(() => {
    // 매 테스트 새 in-memory Storage 설치 → 저장/복원 단언 격리 + clear() 결정론 보장
    const mock = createStorageMock();
    Object.defineProperty(window, "localStorage", {
      value: mock,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, "localStorage", {
      value: mock,
      configurable: true,
      writable: true,
    });
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("T1: PC 나브에 화면 폭 슬라이더(range)가 aria-label 과 함께 존재한다", () => {
    renderApp();

    const slider = screen.queryByTestId("content-width-slider");
    expect(slider).not.toBeNull();
    // input type=range 는 암묵 role="slider"
    expect(slider).toHaveAttribute("aria-label", "화면 폭 조정");
    expect(screen.queryByRole("slider")).not.toBeNull();
  });

  it("T2: localStorage 가 비어있으면 기본 전체폭(level 100) — main maxWidth 100% + 슬라이더 value=100", () => {
    renderApp();

    const main = document.querySelector("main");
    expect(main).not.toBeNull();
    // contentMaxWidth(100) = max(1024px, 100%) → 전체폭
    expect(main!.style.maxWidth).toContain("100%");

    const slider = screen.getByTestId("content-width-slider") as HTMLInputElement;
    expect(slider.value).toBe("100");
  });

  it("T3: 슬라이더를 0 으로 조정하면 main maxWidth 가 60% 로 갱신 + localStorage 에 '0' 저장", () => {
    renderApp();

    const slider = screen.getByTestId("content-width-slider") as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "0" } });

    const main = document.querySelector("main");
    expect(main).not.toBeNull();
    // contentMaxWidth(0) = max(1024px, 60%)
    expect(main!.style.maxWidth).toContain("60%");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("0");
  });

  it("T4: localStorage 에 '40' 이 있으면 복원 — 슬라이더 value=40 + main maxWidth 76%", () => {
    window.localStorage.setItem(STORAGE_KEY, "40");
    renderApp();

    const slider = screen.getByTestId("content-width-slider") as HTMLInputElement;
    expect(slider.value).toBe("40");

    const main = document.querySelector("main");
    expect(main).not.toBeNull();
    // contentMaxWidth(40) = max(1024px, 76%)  (60 + 40*0.4 = 76)
    expect(main!.style.maxWidth).toContain("76%");
  });

  it("T5(회귀): main 이 존재하고 nav-sticky-wrapper 자식이 아니다 (기존 AppShell 구조 불변)", () => {
    renderApp();

    const main = document.querySelector("main");
    const stickyWrapper = screen.getByTestId("nav-sticky-wrapper");
    expect(main).not.toBeNull();
    // max-w-7xl 제거가 기존 sticky/main 분리 구조를 깨지 않는다 (AppShell.test.tsx M-8 영속)
    expect(stickyWrapper.contains(main)).toBe(false);
  });
});
