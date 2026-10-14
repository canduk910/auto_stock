/**
 * cycle456 — 시장 유닛 결정 과정 카드(Dashboard, 읽기 전용) 실브라우저 확인.
 *
 * G-E2E-MU1: 카드가 뜨고 차트 SVG(가격 캔들·60일선 선)가 실제로 그려진다 · 코스닥 탭 전환 · 현재 판정 칸 강조.
 */
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";
import { MARKET_UNIT_CHART_FIXTURE } from "./fixtures/market-unit-chart.fixture";

test("G-E2E-MU1 — 시장 유닛 차트가 그려지고 탭이 바뀐다", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/");
  const card = page.getByTestId("mu-chart-card");
  await expect(card).toBeVisible({ timeout: 10_000 });
  const kospi = MARKET_UNIT_CHART_FIXTURE.markets.kospi;
  await expect(page.getByTestId("mu-chart-today-m")).toHaveText(`×${kospi.effective.m}`);
  // recharts 가 실제 선 경로를 그렸는지(jsdom 에서는 못 보는 부분)
  await expect(page.getByTestId("mu-chart-price").locator("path.recharts-curve").first()).toBeVisible({ timeout: 10_000 });
  // 가격은 캔들 — 봉 수만큼 그려진다
  await expect(page.getByTestId("mu-chart-price").getByTestId("mu-chart-candle")).toHaveCount(kospi.bars.length, { timeout: 10_000 });
  await expect(page.getByTestId(`mu-chart-state-${kospi.decision.state}`)).toHaveAttribute("data-active", "true");
  if (process.env.MU_SHOT) await card.screenshot({ path: `${process.env.MU_SHOT}/mu_kospi.png` });
  await page.getByTestId("mu-chart-tab-kosdaq").click();
  const q = MARKET_UNIT_CHART_FIXTURE.markets.kosdaq;
  await expect(page.getByTestId("mu-chart-today-m")).toHaveText(`×${q.effective.m}`);
  if (process.env.MU_SHOT) await card.screenshot({ path: `${process.env.MU_SHOT}/mu_kosdaq.png` });
});
