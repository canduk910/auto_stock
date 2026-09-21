/**
 * cycle338 (2026-09-21) — 표가 브라우저 창 크기에 맞춰 스크롤되는가 (G-E2E-11).
 *
 * 사용자 지시 = "모든 UI에서 브라우저 창크기에 맞춰서 스크롤이 생성되게 하자.
 * 예를 들면 현재 거래내역-매매손익 화면에서 가로스크롤이 세로스크롤에서 끝까지
 * 내려가야만 보이는데, 창 사이즈에 맞춰서 보기좋게 가로/세로 스크롤이 가능했으면 해."
 *
 * 🔴 **왜 E2E 여야 하는가** — 이 결함은 **레이아웃 결함**이라 jsdom 이 원리적으로 못 잡는다.
 * jsdom 은 `clientHeight`·`scrollHeight` 가 전부 0 이고 스크롤바를 만들지 않는다. 단위
 * 테스트가 재는 것은 "우리가 `maxHeight` 를 걸었는가" 까지이고, "그 결과 가로 스크롤바가
 * 화면 안에 들어왔는가" 는 실브라우저만 안다. cycle266 의 종목마스터 일봉 탭이 **한 번도
 * 동작한 적 없는데 3개월 초록**이던 그 함정과 같은 계열이다.
 *
 * 판정 = 표 래퍼의 **바닥이 뷰포트 안에** 있는가. 결함 상태에서는 래퍼 높이가 표 전체
 * 높이라 바닥이 화면 훨씬 아래에 있고, 가로 스크롤바가 거기 붙어 보이지 않는다.
 *
 * production 코드 변경 0 — spec 만.
 */

import { expect, test, type Page } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

const VIEWPORT = { width: 1280, height: 800 };
const TIMEOUT = 15_000;

/** 그 요소의 바닥이 뷰포트 안에 있는가 + 실제로 세로 스크롤 가능한가. */
async function paneGeometry(page: Page, testId: string) {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"]`);
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      top: rect.top,
      bottom: rect.bottom,
      viewportHeight: window.innerHeight,
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      overflowX: getComputedStyle(el).overflowX,
      overflowY: getComputedStyle(el).overflowY,
      maxHeight: getComputedStyle(el).maxHeight,
    };
  }, testId);
}

test.describe("cycle338 — 창 크기에 맞는 표 스크롤", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(VIEWPORT);
    await installApiMocks(page);
  });

  test("G-E2E-11a: 매매손익 표 래퍼의 바닥이 뷰포트 안에 있다", async ({ page }) => {
    // 사용자가 직접 지목한 화면이다.
    await page.goto("/history");
    await page.getByRole("tab", { name: /매매손익/ }).click().catch(() => {});
    await page.waitForTimeout(600);

    const pane = page.locator('[data-testid="scroll-pane"]').first();
    await expect(pane).toBeVisible({ timeout: TIMEOUT });

    const g = await paneGeometry(page, "scroll-pane");
    expect(g).not.toBeNull();
    // 🔴 이것이 결함의 판정식이다 — 바닥이 화면 밖이면 가로 스크롤바를 볼 수 없다.
    expect(g!.bottom).toBeLessThanOrEqual(g!.viewportHeight + 1);
    // 상한이 실제로 걸려 있다(none 이면 결함 상태 그대로다).
    expect(g!.maxHeight).not.toBe("none");
  });

  test("G-E2E-11b: 두 축 모두 스크롤 가능하다 — 가로 전용이 아니다", async ({ page }) => {
    await page.goto("/history");
    await page.waitForTimeout(600);
    const g = await paneGeometry(page, "scroll-pane");
    expect(g).not.toBeNull();
    expect(["auto", "scroll"]).toContain(g!.overflowX);
    expect(["auto", "scroll"]).toContain(g!.overflowY);
  });

  test("G-E2E-11c: 창을 줄이면 표 영역도 따라 줄어든다", async ({ page }) => {
    await page.goto("/history");
    await page.waitForTimeout(600);

    const tall = await paneGeometry(page, "scroll-pane");
    await page.setViewportSize({ width: 1280, height: 520 });
    await page.waitForTimeout(500);
    const short = await paneGeometry(page, "scroll-pane");

    expect(tall).not.toBeNull();
    expect(short).not.toBeNull();
    // 창이 280px 줄었으면 표 영역도 줄어야 한다(고정 픽셀이면 안 줄어든다).
    expect(short!.clientHeight).toBeLessThan(tall!.clientHeight);
    // 바닥은 여전히 화면 안이다.
    expect(short!.bottom).toBeLessThanOrEqual(short!.viewportHeight + 1);
  });

  test("G-E2E-11d: 잔고 표도 같은 규약을 따른다", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(800);
    const panes = page.locator('[data-testid="scroll-pane"]');
    const n = await panes.count();
    expect(n).toBeGreaterThan(0);

    const all = await page.evaluate(() => {
      const out: { bottom: number; vh: number; maxHeight: string }[] = [];
      document.querySelectorAll('[data-testid="scroll-pane"]').forEach((el) => {
        const r = el.getBoundingClientRect();
        // 접혀 있어 높이가 0 인 것은 판정 대상이 아니다.
        if (r.height <= 0) return;
        out.push({
          bottom: r.bottom,
          vh: window.innerHeight,
          maxHeight: getComputedStyle(el).maxHeight,
        });
      });
      return out;
    });

    for (const g of all) {
      expect(g.maxHeight).not.toBe("none");
      expect(g.bottom).toBeLessThanOrEqual(g.vh + 1);
    }
  });
});
