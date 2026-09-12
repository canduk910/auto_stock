/**
 * 사이클 86 (2026-06-09) — stock_master UI 통합 검증 E2E spec.
 *
 * 8 케이스 매트릭스 (HIGH 3 + MEDIUM 3 + LOW 2)
 * cycle266 D-3 (2026-09-07): G-E2E-9 추가 → 9 케이스 (일봉 탭 실브라우저 커버리지).
 * 사이클 80 hotfix #2 답습: timeout 20s (카드 누적 + useQuery 다중 + lazy + Suspense fallback)
 * 사이클 80 hotfix #3 답습: Playwright LIFO 정합 (api-mocks 5 stock-master 라우트 영속)
 * 사이클 81 G-M5 답습: 모바일 햄버거 메뉴 압축 검증 (cycle288 이후 leaf 10개)
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

test.describe("G-E2E-3 (HIGH) — 모바일 viewport 375px 햄버거 메뉴 압축 (cycle288 이후 leaf 10개)", () => {
  test("종목마스터 포함 drawer 표시 (사이클 81 G-M5 영속 · cycle288 그룹화 반영)", async ({ page }) => {
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

    // 기존 메뉴도 drawer 내부에 표시 검증 (사이클 65 hotfix #3 + 사이클 80 hotfix #2 timeout 영속)
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

    // 페이지 제목 텍스트 확인 — cycle288 검증 라운드 시정: "종목마스터"는 나브 그룹 하위
    // 라벨과도 겹치는 텍스트라 getByText(...).first() 가 (닫힌 그룹 안이라 숨겨진) 나브 요소를
    // 집을 수 있다. 페이지 본문의 <h1> 으로 좁힌다.
    await expect(page.getByRole("heading", { name: "종목마스터" })).toBeVisible({ timeout: 20000 });
  });
});

test.describe("G-E2E-8 (LOW) — 7번째 메뉴 종목마스터 클릭 → 라우트 진입", () => {
  test("PC 메뉴에서 종목마스터 클릭 시 /stock-master URL + 카드 렌더", async ({ page }) => {
    // 사이클 85 7번째 메뉴 추가 영속 검증
    await installApiMocks(page);
    await page.goto("/");

    // PC viewport (기본) — cycle288: "종목마스터"는 "종목" 그룹 하위. 트리거를 먼저 연다.
    // sm 이상 viewport = hidden sm:flex 메뉴 가시 (playwright 기본 Desktop Chrome)
    await page.getByRole("button", { name: "종목", exact: true }).click();
    await page.getByRole("link", { name: "종목마스터" }).first().click();

    // URL /stock-master 전환 검증
    await expect(page).toHaveURL(/\/stock-master/);

    // 카드 렌더 완료 검증 (사이클 80 hotfix #2 답습 timeout 20s)
    await expect(
      page.getByTestId("stock-master-stats-card"),
    ).toBeVisible({ timeout: 20000 });
  });
});

// ────────────────────────────────────────────────────────────────────────
// cycle266 D-3 (tester 적대 검토) — 일봉 탭 실브라우저 커버리지
//
// 종전 8 케이스는 일봉 탭을 **한 번도 열지 않았다**(`grep -n "daily" e2e/*.spec.ts`
// = 0건). 그래서 2026-06-13(사이클 124) 이후 일봉 탭이 프로덕션에서 흰 화면인
// 3개월 내내 E2E 33 케이스가 초록이었다 — 통과한 E2E 는 이 결함에 대해 아무
// 증거도 제공하지 않았다.
//
// 이 케이스가 재는 것: 문자열 등락률(`"1.2000"`, 운영 실제 응답 모양)이 실브라우저
// 에서 `+1.20%` 로 렌더되고 트리가 살아 있는가. 종전 구현은 여기서
// `row.change_rate.toFixed(2)` → TypeError → (ErrorBoundary 부재) 루트 언마운트로
// 흰 화면이 됐다.
//
// ⚠️ Playwright route 는 **LIFO**(사이클 80 hotfix #3). 아래 목록 라우트는
// `installApiMocks` **뒤에** 등록해 목록만 덮는다 — 일봉 목은 fixture 정본
// (`e2e/fixtures/api-mocks.ts`, 문자열/숫자 혼합 5행)을 그대로 쓴다.
// ────────────────────────────────────────────────────────────────────────

test.describe("G-E2E-9 (cycle266 D-3) — 일봉 탭 렌더 + 문자열 등락률", () => {
  test("종목 클릭 → 일봉 탭 → 표 가시 + 문자열 등락률이 +1.20% 로 렌더", async ({ page }) => {
    await installApiMocks(page);

    // LIFO 우선 — 목록에 클릭 가능한 종목 1건을 만든다 (fixture 기본은 빈 목록).
    await page.route("**/api/stock-master/list*", (route) =>
      route.fulfill({
        json: {
          success: true,
          message: "",
          data: {
            items: [
              {
                ticker: "005930",
                name: "삼성전자",
                excg_dvsn_cd: "01",
                nxt_tradable: true,
                krx_halted: false,
                admin_item: false,
                refreshed_at: "2026-09-05T09:00:00+09:00",
                raw: { bfdy_clpr: 75000, stck_prpr: "75000" },
              },
            ],
            total: 1,
            limit: 100,
            offset: 0,
          },
        },
      }),
    );

    await page.goto("/stock-master");

    // 목록 행 클릭 → 상세 모달 (사이클 80 hotfix #2 답습 timeout 20s)
    const row = page.getByTestId("stock-master-row-stck-prpr-005930");
    await expect(row).toBeVisible({ timeout: 20000 });
    await row.click();

    await expect(
      page.getByTestId("stock-master-detail-tabs"),
    ).toBeVisible({ timeout: 20000 });

    // 일봉 탭 전환
    await page.getByTestId("stock-master-tab-daily").click();

    const table = page.getByTestId("stock-master-daily-table");
    await expect(table).toBeVisible({ timeout: 20000 });

    // 문자열 등락률 행 — `change_rate: "1.2000"` (fixture 첫 행)
    const stringRow = table.locator("tbody tr").filter({ hasText: "2026-09-05" });
    await expect(stringRow).toHaveCount(1);
    await expect(stringRow.locator("td").nth(6)).toHaveText("+1.20%");

    // 숫자 등락률 행도 함께 통과해야 한다 — `change_rate: 0.9` (A-1 시정 후의 모양)
    const numberRow = table.locator("tbody tr").filter({ hasText: "2026-09-04" });
    await expect(numberRow.locator("td").nth(6)).toHaveText("+0.90%");

    // 흰 화면 재발 신호 — 변환 실패('—')·NaN 이 표 안에 없어야 한다
    await expect(table).not.toContainText("NaN");
    await expect(table).not.toContainText("—");
  });
});
