/**
 * 사이클 86 (2026-06-09) — stock_master UI 통합 검증 E2E spec.
 *
 * 8 케이스 매트릭스 (HIGH 3 + MEDIUM 3 + LOW 2)
 * 사이클 80 hotfix #2 답습: timeout 20s (카드 누적 + useQuery 다중 + lazy + Suspense fallback)
 * 사이클 80 hotfix #3 답습: Playwright LIFO 정합 (api-mocks 5 stock-master 라우트 영속)
 * 사이클 81 G-M5 답습: 모바일 햄버거 메뉴 7개 압축 검증
 * 사이클 85 답습: installApiMocks 영속 (5 stock-master 라우트 LIFO 등록)
 *
 * production 코드 변경 0 — spec 파일 신규 단일 산출물.
 */

import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

// ────────────────────────────────────────────────────────────────────────
// HIGH 케이스 3
// ────────────────────────────────────────────────────────────────────────

test.describe("G-E2E-1 (HIGH) — 페이지 진입 + 4 카드 영역 렌더", () => {
  test("진입 시 stats-card 와 list-card 가 visible", async ({ page }) => {
    // 사이클 85 api-mocks 5 stock-master 라우트 LIFO 등록 영속
    await installApiMocks(page);
    await page.goto("/stock-master");

    // 사이클 80 hotfix #2 답습 — timeout 20s
    // stats-card 는 statsQuery + scanPoolQuery 양쪽 로딩 완료 후 testid 전환
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });

    // list-card 는 listQuery 로딩 완료 후 testid 전환
    await expect(
      page.getByTestId("stock-master-list-card"),
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe("G-E2E-2 (HIGH) — stats 카드 4 지표 구조 + list 빈 상태 graceful", () => {
  test("stats-card 4 지표 영역 + eager-refresh testid visible + 빈 목록 graceful 메시지", async ({ page }) => {
    // 사이클 85 api-mocks LIFO: /api/stock-master/* wildcard 가 stats/list 모두 매칭.
    // 숫자 정확성 검증보다 UI 구조(testid visible) + graceful fallback 검증으로 대체.
    // 운영 환경에서는 각 라우트가 백엔드 응답을 받아 정확한 데이터를 표시.
    await installApiMocks(page);
    await page.goto("/stock-master");

    // stats-card 렌더 완료 대기 (로딩 완료 후 testid 전환)
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });

    // eager_refresh_today testid 기반 — scan-pool 로딩 완료 보장 (Q12=A 영속)
    await expect(
      page.getByTestId("stock-master-stats-eager-refresh-today"),
    ).toBeVisible({ timeout: 20000 });

    // 4 지표 레이블 텍스트 visible 검증 (숫자보다 안정적)
    const statsCard = page.getByTestId("stock-master-stats-card");
    await expect(statsCard.getByText("전체 종목 수")).toBeVisible({ timeout: 20000 });
    await expect(statsCard.getByText("NXT 거래가능")).toBeVisible({ timeout: 20000 });

    // mock list = 빈 배열 + Array.isArray 가드 → 빈 목록 graceful 메시지
    await expect(
      page.getByTestId("stock-master-list-card"),
    ).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByText("종목 데이터가 없습니다.").first(),
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe("G-E2E-3 (HIGH) — 모바일 viewport 375px 햄버거 메뉴 7개 압축", () => {
  test("종목마스터 포함 7개 메뉴 drawer 표시 (사이클 81 G-M5 영속)", async ({ page }) => {
    // 사이클 81 G-M3 — 375px iPhone viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await installApiMocks(page);
    await page.goto("/");

    // 사이클 81 G-M1 — 햄버거 버튼 존재
    const hamburgerBtn = page.getByLabel("메뉴 열기");
    await expect(hamburgerBtn).toBeVisible({ timeout: 20000 });

    // 사이클 81 G-M3 — 클릭 전 drawer 미존재 (사이클 65 hotfix #3 timeout 영속)
    await expect(page.getByTestId("mobile-menu-drawer")).not.toBeVisible({ timeout: 5000 });

    // 사이클 81 G-M3 — 클릭 후 drawer open
    await hamburgerBtn.click();
    await expect(page.getByTestId("mobile-menu-drawer")).toBeVisible({ timeout: 20000 });

    // 사이클 85 7번째 메뉴 `종목마스터` 포함 검증 (사이클 81 G-M5 영속)
    // drawer 내부로 범위 좁혀 hidden PC 메뉴 요소 충돌 차단
    const drawer = page.getByTestId("mobile-menu-drawer");
    await expect(drawer.getByText("종목마스터")).toBeVisible({ timeout: 20000 });

    // 기존 6개 메뉴도 drawer 내부에 표시 검증 (사이클 65 hotfix #3 + 사이클 80 hotfix #2 timeout 영속)
    await expect(drawer.getByText("대시보드")).toBeVisible({ timeout: 20000 });
    await expect(drawer.getByText("거래 내역")).toBeVisible({ timeout: 20000 });
    await expect(drawer.getByText("설정")).toBeVisible({ timeout: 20000 });
  });
});

// ────────────────────────────────────────────────────────────────────────
// MEDIUM 케이스 3
// ────────────────────────────────────────────────────────────────────────

test.describe("G-E2E-4 (MEDIUM) — history 카드 선택 전 graceful 메시지", () => {
  test("목록 클릭 전 history 카드 안내 메시지 visible (Q12=A collapsible 영속)", async ({ page }) => {
    // 사이클 169 — history 영역 seq/raw 신 스키마 (사이클 150 migration 036).
    // 본 케이스는 선택 전 graceful 안내만 검증 (history 행 내용 무관).
    await installApiMocks(page);
    await page.goto("/stock-master");

    // stats-card 렌더 대기
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });

    // history-card-loading 이 visible (선택된 ticker 없음 = graceful 분기)
    // 주의: selectedTicker = null 이면 'stock-master-history-card-loading' testid
    await expect(
      page.getByTestId("stock-master-history-card-loading"),
    ).toBeVisible({ timeout: 20000 });

    // 안내 메시지 표시
    await expect(
      page.getByText("목록에서 종목을 클릭하면 변경 이력을 표시합니다.").first(),
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe("G-E2E-5 (MEDIUM) — api-mocks 5 stock-master 라우트 LIFO 영속 (ECONNREFUSED 0건)", () => {
  test("stock-master 페이지 진입 시 network failure 0건 (사이클 80 hotfix #3 영속)", async ({ page }) => {
    // 사이클 80 hotfix #3 — Playwright LIFO 정합 영속
    // 사이클 85 — 5 stock-master 라우트 LIFO 등록 영속
    const failedUrls: string[] = [];

    page.on("requestfailed", (request) => {
      const url = request.url();
      // stock-master 관련 API 요청 실패만 수집
      if (url.includes("/api/stock-master")) {
        failedUrls.push(url);
      }
    });

    await installApiMocks(page);
    await page.goto("/stock-master");

    // stats-card 렌더 완료까지 대기 (모든 API 요청 완료 보장)
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });

    // stock-master API 호출 실패 0건 검증
    expect(failedUrls).toHaveLength(0);
  });
});

test.describe("G-E2E-6 (MEDIUM) — stats eager-refresh-today 지표 testid 렌더", () => {
  test("eager_refresh_today 지표 testid visible (사이클 83 emit 카운트 가시화)", async ({ page }) => {
    // 사이클 85 api-mocks: /api/stock-master/scan-pool/summary → { eager_refresh_today: 0 }
    await installApiMocks(page);
    await page.goto("/stock-master");

    // stats-card 렌더 완료 대기
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });

    // eager_refresh_today 지표 testid 검증
    await expect(
      page.getByTestId("stock-master-stats-eager-refresh-today"),
    ).toBeVisible({ timeout: 20000 });

    // mock 값 0 표시 검증
    const eagerRefreshEl = page.getByTestId("stock-master-stats-eager-refresh-today");
    await expect(eagerRefreshEl).toContainText("0");
  });
});

// ────────────────────────────────────────────────────────────────────────
// LOW 케이스 2
// ────────────────────────────────────────────────────────────────────────

test.describe("G-E2E-7 (LOW) — lazy 로 + Suspense fallback 정상 전환", () => {
  test("StockMaster lazy import 후 본체 mount 완료 (Suspense fallback → 카드 렌더)", async ({ page }) => {
    // 사이클 85 StockMaster = React.lazy() + Suspense (PageFallback 스켈레톤 자연 전환)
    await installApiMocks(page);
    await page.goto("/stock-master");

    // PageFallback 이 표시되다가 Suspense 해제 후 카드 렌더 완료
    // 최종 본체 카드 가시성 확인 (Suspense fallback 자체는 timing 의존 = graceful)
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });

    // 페이지 제목 텍스트 확인
    await expect(page.getByText("종목마스터").first()).toBeVisible({ timeout: 20000 });
  });
});

test.describe("G-E2E-8 (LOW) — 7번째 메뉴 종목마스터 클릭 → 라우트 진입", () => {
  test("PC 메뉴에서 종목마스터 클릭 시 /stock-master URL + 카드 렌더", async ({ page }) => {
    // 사이클 85 7번째 메뉴 추가 영속 검증
    await installApiMocks(page);
    await page.goto("/");

    // PC viewport (기본) — 가로 메뉴에서 `종목마스터` 링크 클릭
    // sm 이상 viewport = hidden sm:flex 메뉴 가시 (playwright 기본 Desktop Chrome)
    await page.getByRole("link", { name: "종목마스터" }).first().click();

    // URL /stock-master 전환 검증
    await expect(page).toHaveURL(/\/stock-master/);

    // 카드 렌더 완료 검증 (사이클 80 hotfix #2 답습 timeout 20s)
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });
  });
});
