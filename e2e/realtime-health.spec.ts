/**
 * 사이클 104 (2026-06-11) — 실시간 건강 모니터링 E2E spec.
 *
 * 13 케이스 매트릭스 (HIGH 4 + MEDIUM 2 + LOW 2 = 8 케이스)
 *
 * 사이클 86 答습 패턴:
 *   - installApiMocks 영속 (사이클 103 logs/search 라우트 LIFO 등록 영속)
 *   - 사이클 80 hotfix #2 답습: timeout 20s (Suspense lazy + useQuery 다중)
 *   - 사이클 80 hotfix #3 답습: Playwright LIFO 정합 (api-mocks 영속)
 *   - 사이클 89 한글 친숙 용어 영속
 *
 * production 코드 변경 0 — spec 파일 신규 단일 산출물.
 */

import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

// ────────────────────────────────────────────────────────────────────────
// HIGH 케이스 4
// ────────────────────────────────────────────────────────────────────────

test.describe("H-RH1 (HIGH) — 4 카드 testid 렌더 visible", () => {
  test("4 카드 (dispatch-drop / callback-exception / stale-force-retry / ws-auto-restart) 렌더", async ({ page }) => {
    // 사이클 103 api-mocks logs/search LIFO 등록 영속
    await installApiMocks(page);
    await page.goto("/realtime-health");

    // 사이클 80 hotfix #2 답습 — timeout 20s
    await expect(
      page.getByTestId("realtime-health-card-dispatch-drop")
    ).toBeVisible({ timeout: 20000 });

    await expect(
      page.getByTestId("realtime-health-card-callback-exception")
    ).toBeVisible({ timeout: 20000 });

    await expect(
      page.getByTestId("realtime-health-card-stale-force-retry")
    ).toBeVisible({ timeout: 20000 });

    await expect(
      page.getByTestId("realtime-health-card-ws-auto-restart")
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe("H-RH2 (HIGH) — 빈 데이터 graceful 표시", () => {
  test("ws_auto_restart 0건 = '0건 — 정상' 표시 + 다른 카드 '데이터 없음'", async ({ page }) => {
    // 사이클 103 api-mocks = logs/search → 빈 로그 응답
    await installApiMocks(page);
    await page.goto("/realtime-health");

    // ws_auto_restart 카드 렌더 대기
    await expect(
      page.getByTestId("realtime-health-card-ws-auto-restart")
    ).toBeVisible({ timeout: 20000 });

    // ws_auto_restart = 0건 → "0건 — 정상" graceful 메시지 (RealtimeHealth.tsx L116 영속)
    const wsCard = page.getByTestId("realtime-health-card-ws-auto-restart");
    await expect(wsCard.getByText("0건 — 정상")).toBeVisible({ timeout: 20000 });

    // dispatch-drop 카드 = 0건 → "데이터 없음" graceful 메시지
    const dropCard = page.getByTestId("realtime-health-card-dispatch-drop");
    await expect(dropCard.getByText("데이터 없음")).toBeVisible({ timeout: 20000 });
  });
});

test.describe("H-RH3 (HIGH) — api-mocks ECONNREFUSED 0건 (LIFO 정합 영속)", () => {
  test("realtime-health 진입 시 logs/search network failure 0건", async ({ page }) => {
    // 사이클 80 hotfix #3 — Playwright LIFO 정합 영속
    // 사이클 103 — logs/search 라우트 LIFO 등록 영속
    const failedUrls: string[] = [];

    page.on("requestfailed", (request) => {
      const url = request.url();
      if (url.includes("/api/logs")) {
        failedUrls.push(url);
      }
    });

    await installApiMocks(page);
    await page.goto("/realtime-health");

    // 4 카드 렌더 완료까지 대기 (모든 API 요청 완료 보장)
    await expect(
      page.getByTestId("realtime-health-card-ws-auto-restart")
    ).toBeVisible({ timeout: 20000 });

    // logs API 호출 실패 0건 검증
    expect(failedUrls).toHaveLength(0);
  });
});

test.describe("H-RH4 (HIGH) — 페이지 제목 visible", () => {
  test("'실시간 건강 모니터링' 제목 visible (사이클 89 한글 친숙 용어 영속)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/realtime-health");

    // 페이지 h1 제목
    await expect(
      page.getByText("실시간 건강 모니터링").first()
    ).toBeVisible({ timeout: 20000 });
  });
});

// ────────────────────────────────────────────────────────────────────────
// MEDIUM 케이스 2
// ────────────────────────────────────────────────────────────────────────

test.describe("M-RH5 (MEDIUM) — 시간 윈도우 토글 버튼 visible", () => {
  test("24시간 / 7일 토글 버튼 모두 visible (사이클 103 MEDIUM-2 영속)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/realtime-health");

    // 4 카드 렌더 대기
    await expect(
      page.getByTestId("realtime-health-card-ws-auto-restart")
    ).toBeVisible({ timeout: 20000 });

    // 24h 토글 버튼
    await expect(
      page.getByTestId("realtime-health-window-24h")
    ).toBeVisible({ timeout: 20000 });

    // 7d 토글 버튼
    await expect(
      page.getByTestId("realtime-health-window-7d")
    ).toBeVisible({ timeout: 20000 });

    // 텍스트 확인 (한글 라벨 영속)
    await expect(page.getByTestId("realtime-health-window-24h")).toContainText("24시간");
    await expect(page.getByTestId("realtime-health-window-7d")).toContainText("7일");
  });
});

test.describe("M-RH6 (MEDIUM) — 카드 한글 라벨 영속", () => {
  test("4 카드 한글 제목 모두 visible (사이클 89 한글 친숙 용어 영속)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/realtime-health");

    // 카드 렌더 대기
    await expect(
      page.getByTestId("realtime-health-card-dispatch-drop")
    ).toBeVisible({ timeout: 20000 });

    // 한글 카드 제목 (RealtimeHealth.tsx CARD_CONFIGS 영속)
    await expect(page.getByText("메시지 누락").first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("콜백 예외").first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("강제 재구독").first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("자동 재기동").first()).toBeVisible({ timeout: 20000 });
  });
});

// ────────────────────────────────────────────────────────────────────────
// LOW 케이스 2
// ────────────────────────────────────────────────────────────────────────

test.describe("L-NAV1 (LOW) — PC 메뉴 '실시간 상태' 클릭 → 라우트 진입", () => {
  test("PC 메뉴에서 실시간 상태 클릭 시 /realtime-health URL + 카드 렌더", async ({ page }) => {
    // 사이클 85 8번째 메뉴 → 사이클 103 8번째 메뉴 영속 검증
    await installApiMocks(page);
    await page.goto("/");

    // PC viewport (기본) — cycle288: "실시간 상태"는 "운영상태" 그룹 하위. 트리거를 먼저 연다.
    await page.getByRole("button", { name: "운영상태", exact: true }).click();
    await page.getByRole("link", { name: "실시간 상태" }).first().click();

    // URL /realtime-health 전환 검증
    await expect(page).toHaveURL(/\/realtime-health/);

    // 카드 렌더 완료 검증 (사이클 80 hotfix #2 답습 timeout 20s)
    await expect(
      page.getByTestId("realtime-health-card-ws-auto-restart")
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe("L-MOB (LOW) — 모바일 viewport 375px 햄버거 9개 메뉴", () => {
  test("실시간 상태 + 전략 현황 포함 9개 메뉴 drawer 표시 (사이클 81 G-M5 → 9개 갱신)", async ({ page }) => {
    // 사이클 81 G-M3 — 375px iPhone viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await installApiMocks(page);
    await page.goto("/");

    // 햄버거 버튼 존재
    const hamburgerBtn = page.getByLabel("메뉴 열기");
    await expect(hamburgerBtn).toBeVisible({ timeout: 20000 });

    // 클릭 후 drawer open
    await hamburgerBtn.click();
    const drawer = page.getByTestId("mobile-menu-drawer");
    await expect(drawer).toBeVisible({ timeout: 20000 });

    // 사이클 103 추가 메뉴 2개 (8번째 / 9번째) 포함 검증
    await expect(drawer.getByText("실시간 상태")).toBeVisible({ timeout: 20000 });
    await expect(drawer.getByText("전략 현황")).toBeVisible({ timeout: 20000 });

    // 기존 메뉴도 drawer 내부에 표시 검증
    await expect(drawer.getByText("대시보드")).toBeVisible({ timeout: 20000 });
    await expect(drawer.getByText("설정")).toBeVisible({ timeout: 20000 });
    await expect(drawer.getByText("종목마스터")).toBeVisible({ timeout: 20000 });
  });
});
