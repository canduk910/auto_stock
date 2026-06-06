import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

test.describe("Settings 페이지", () => {
  test("진입 시 페이지 헤더와 전략 카드가 보인다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/settings");
    // lazy 로 로드되므로 약간의 대기 + 사이클 64+65 카드 추가로 페이지 어셈블 5s 초과 가능성
    // (사이클 65 hotfix #3 — recommendations/trading-flow 패턴 답습, timeout: 10000)
    await expect(page.getByText(/설정|전략/).first()).toBeVisible({ timeout: 10000 });
    // 4 전략 중 momentum 은 mock 에 있으므로 표시
    await expect(page.getByText("상한가 모멘텀").first()).toBeVisible({ timeout: 10000 });
  });
});
