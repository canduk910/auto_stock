import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

test.describe("AI 자문 페이지", () => {
  test("진입 시 페이지 헤더가 보인다", async ({ page }) => {
    await installApiMocks(page, { recommendations: [] });
    await page.goto("/recommendations");
    // lazy 로드
    await expect(
      page.getByText(/AI|자문|전략수정/).first(),
    ).toBeVisible({ timeout: 10000 });
  });

  test("일일 로그 분석 페이지도 진입 가능", async ({ page }) => {
    await installApiMocks(page, { logReports: [] });
    await page.goto("/log-reports");
    await expect(
      page.getByText(/로그|리포트|분석/).first(),
    ).toBeVisible({ timeout: 10000 });
  });
});
