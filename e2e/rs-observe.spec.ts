/**
 * RS·재무 관찰 화면(전략 메뉴 세 번째 세부, 읽기 전용) 실브라우저 확인.
 *
 * G-E2E-RS1: 나브 「전략」 그룹에서 「RS·재무 관찰」 로 들어가 관찰 전용 띠 · 4전략 구역 · 표 행이 보인다 ·
 * 전략 버튼이 그 구역만 남긴다 · 모름 칸은 — 다.
 */
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";
import { RS_OBSERVE_FIXTURE } from "../frontend/src/test/fixtures/rsObserve.fixture";

test("G-E2E-RS1 — 전략 메뉴에서 RS·재무 관찰로 들어간다", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await installApiMocks(page);
  await page.goto("/");
  await page.getByRole("button", { name: "전략", exact: true }).click();
  await page.getByRole("link", { name: "RS·재무 관찰" }).click();
  await expect(page).toHaveURL(/\/rs-observe$/);
  await expect(page.getByTestId("rs-observe-banner")).toContainText("관찰 전용", { timeout: 15_000 });
  for (const sid of RS_OBSERVE_FIXTURE.strategies) {
    await expect(page.getByTestId(`rs-observe-section-${sid}`)).toBeVisible({ timeout: 10_000 });
  }
  const kakao = page.getByTestId("rs-observe-row-donchian_swing-035720");
  await expect(kakao).toBeVisible({ timeout: 10_000 });
  await expect(kakao.locator('[data-key="roe"]')).toHaveText("—");
  await page.getByTestId("rs-observe-strategy-vcp_breakout").click();
  await expect(page.getByTestId("rs-observe-section-donchian_swing")).toHaveCount(0);
  await expect(page.getByTestId("rs-observe-row-vcp_breakout-000660")).toBeVisible({ timeout: 10_000 });
  if (process.env.RS_SHOT) await page.screenshot({ path: `${process.env.RS_SHOT}/rs_observe.png`, fullPage: true });
  expect(errors).toEqual([]);
});
