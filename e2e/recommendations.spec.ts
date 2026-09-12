import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

test.describe("AI 자문 페이지", () => {
  test("진입 시 페이지 헤더가 보인다", async ({ page }) => {
    await installApiMocks(page, { recommendations: [] });
    await page.goto("/recommendations");
    // lazy 로드 — cycle288 검증 라운드 시정: "전략수정 AI자문"은 나브(전략) 그룹 하위 라벨과
    // 정확히 같은 문자열이라 getByText(...).first() 가 (닫힌 그룹 안이라 숨겨진) 나브 요소나
    // 모바일 헤더의 숨은 현재-메뉴 span 을 집을 수 있다. 페이지 본문의 <h1> 으로 좁힌다.
    await expect(
      page.getByRole("heading", { name: /AI|자문|전략수정/ }),
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
