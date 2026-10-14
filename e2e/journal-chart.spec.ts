/**
 * cycle457 — 거래일지 카드 「차트」 실브라우저 확인(G-E2E-JC1).
 *
 * jsdom 에는 canvas 가 없어 단위 테스트는 차트 라이브러리 호출만 본다. 이 spec 은 실제 `klinecharts` 가
 * 사용자 지표·매수/매도 표시를 등록한 채 오류 없이 캔버스를 그리는지 본다.
 *
 * 응답 목 — `installApiMocks` 의 `/api/journal-chart`(고정 응답 = `frontend/src/test/fixtures/journalChart.fixture.ts`,
 * 실제 전략 객체의 `chart_indicators` 로 생성). 거래일지 고정 카드(2026-10-05~10-08 매매)를 덮는다.
 */
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";
import { JOURNAL_ANCHOR_BFB as BFB, JOURNAL_ANCHOR_OPEN as OPEN } from "../frontend/src/test/fixtures/journal.fixture";

test.describe("G-E2E-JC1 (cycle457) — 거래일지 차트", () => {
  for (const [label, anchor, firstLine] of [
    ["kojiro 보유 중", OPEN, "ema_s"],
    ["BFB 청산", BFB, "atr"],
  ] as const) {
    test(`${label} 카드의 차트가 오류 없이 그려진다`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await installApiMocks(page);
      await page.goto("/history");
      await page.getByTestId("history-tab-journal").click();
      const card = page.getByTestId(`journal-card-${anchor}`);
      await expect(card).toBeVisible({ timeout: 20_000 });
      await card.getByTestId("journal-chart-open").click();
      const modal = page.getByTestId("journal-chart-modal");
      await expect(modal).toBeVisible({ timeout: 20_000 });
      await expect(modal.getByTestId("journal-chart-lines")).toBeVisible({ timeout: 20_000 });
      await expect(modal.getByTestId("journal-chart-marks")).toHaveAttribute("data-buys", "1");
      await expect(modal.getByTestId(`journal-chart-line-${firstLine}`)).toBeVisible({ timeout: 10_000 });
      // klinecharts 가 실제 캔버스를 만들었다
      await expect(modal.getByTestId("journal-chart-canvas-host").locator("canvas").first()).toBeVisible({ timeout: 20_000 });
      await page.waitForTimeout(500);
      if (process.env.JC_SHOT) await modal.screenshot({ path: `${process.env.JC_SHOT}/jc_${anchor.slice(-1)}.png` });
      expect(errors).toEqual([]);
      await modal.getByTestId("journal-chart-close").click();
      await expect(modal).toHaveCount(0);
    });
  }
});
