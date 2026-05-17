/**
 * E2E — 자동매매 페이지 스모크.
 *
 * Dashboard 는 ScanMonitor/OrderMonitor/BalanceTable/PerformanceCard 등 다수의
 * 자식 컴포넌트가 status 응답의 깊은 필드에 의존한다. 따라서 E2E 에서는 페이지
 * 로드 + 핵심 텍스트 확인 수준의 안정적인 스모크만 다룬다. 컴포넌트 동작 자세한
 * 검증은 RTL 단위 테스트(Phase E) 가 담당.
 */

import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

test.describe("자동매매 대시보드", () => {
  test("페이지 로드 시 환경 배너가 보인다", async ({ page }) => {
    await installApiMocks(page, { isRunning: false });
    await page.goto("/");
    // env 배너는 Dashboard 자식 컴포넌트의 throw 와 무관하게 App 최상위에서 렌더링
    await expect(page.getByText(/모의투자 환경|실전 매매 환경/)).toBeVisible({
      timeout: 10000,
    });
  });

  test("네비게이션 메뉴 5개가 보인다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/");
    for (const label of ["대시보드", "거래 내역", "전략수정 AI자문", "로그", "설정"]) {
      await expect(page.getByRole("link", { name: label })).toBeVisible();
    }
  });
});
