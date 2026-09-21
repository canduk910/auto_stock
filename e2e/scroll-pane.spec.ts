/**
 * cycle338 (2026-09-21) — 표가 브라우저 창 크기에 맞춰 스크롤되는가 (G-E2E-11).
 *
 * 사용자 지시 = "모든 UI에서 브라우저 창크기에 맞춰서 스크롤이 생성되게 하자.
 * 예를 들면 현재 거래내역-매매손익 화면에서 가로스크롤이 세로스크롤에서 끝까지
 * 내려가야만 보이는데, 창 사이즈에 맞춰서 보기좋게 가로/세로 스크롤이 가능했으면 해."
 *
 * 🔴 **왜 E2E 여야 하는가** — 이 결함은 **레이아웃 결함**이라 jsdom 이 원리적으로 못 잡는다.
 * jsdom 은 `clientHeight`·`scrollHeight` 가 전부 0 이고 스크롤바를 만들지 않는다.
 * 단위 테스트가 재는 것은 "우리가 `maxHeight` 를 걸었는가" 까지다.
 *
 * ⚠️ **이 spec 의 초판이 틀렸고 그 덕에 진짜 결함을 찾았다.** 초판은 모든 pane 에
 * `bottom <= viewport` 를 요구했는데, 대시보드처럼 긴 페이지에서는 표가 화면
 * **아래**(top=1387)에 있는 것이 정상이라 그 단언이 성립할 수 없다. 대신 그 실측이
 * 진짜 결함을 드러냈다 — 화면 밖 표가 최소 높이 220px 에 **갇혀** 있었다.
 * 그래서 불변식을 다시 정의한다:
 *
 *   ① 상한이 반드시 걸린다 (`max-height !== none`)
 *   ② 상한은 **창 높이를 넘지 않는다** (넘으면 가로 스크롤바가 화면 밖으로 밀린다)
 *   ③ 상한은 **최소 높이에 갇히지 않는다** (화면 밖 표도 제 크기를 갖는다)
 *   ④ 화면 안에 있는 표는 바닥도 화면 안이다
 *
 * production 코드 변경 0 — spec 만.
 */

import { expect, test, type Page } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

const VIEWPORT = { width: 1280, height: 800 };
const TIMEOUT = 15_000;
/** `ScrollPane` 의 `MIN_HEIGHT_PX` 와 같은 값 — 여기 갇히면 결함이다. */
const MIN_HEIGHT_PX = 220;

type Geometry = {
  top: number; bottom: number; height: number;
  vh: number; maxHeightPx: number | null; maxHeightRaw: string;
  overflowX: string; overflowY: string;
};

async function panes(page: Page): Promise<Geometry[]> {
  return page.evaluate(() => {
    const out: Geometry[] = [];
    document.querySelectorAll('[data-testid="scroll-pane"]').forEach((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const raw = cs.maxHeight;
      const px = raw.endsWith("px") ? parseFloat(raw) : null;
      out.push({
        top: r.top, bottom: r.bottom, height: r.height,
        vh: window.innerHeight, maxHeightPx: px, maxHeightRaw: raw,
        overflowX: cs.overflowX, overflowY: cs.overflowY,
      });
    });
    return out;
  }) as Promise<Geometry[]>;
}

test.describe("cycle338 — 창 크기에 맞는 표 스크롤", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(VIEWPORT);
    await installApiMocks(page);
  });

  test("G-E2E-11a: 매매손익 표의 바닥이 화면 안에 있다", async ({ page }) => {
    // 사용자가 직접 지목한 화면이다. 탭은 `role=tab` 이 아니라 평범한 button 이다.
    await page.goto("/history");
    await page.getByRole("button", { name: "매매손익", exact: true }).click();
    await page.waitForTimeout(800);

    const [pane] = await panes(page);
    expect(pane, "매매손익 탭에 scroll-pane 이 없다").toBeTruthy();
    expect(pane.maxHeightRaw).not.toBe("none");
    // 🔴 이것이 결함의 판정식이다 — 바닥이 화면 밖이면 가로 스크롤바를 볼 수 없다.
    expect(pane.top).toBeLessThan(pane.vh);
    expect(pane.bottom).toBeLessThanOrEqual(pane.vh + 1);
  });

  test("G-E2E-11b: 두 축 모두 스크롤한다 — 가로 전용이 아니다", async ({ page }) => {
    await page.goto("/history");
    await expect(page.locator('[data-testid="scroll-pane"]').first())
      .toBeVisible({ timeout: TIMEOUT });
    const [pane] = await panes(page);
    expect(["auto", "scroll"]).toContain(pane.overflowX);
    expect(["auto", "scroll"]).toContain(pane.overflowY);
  });

  test("G-E2E-11c: 창을 줄이면 표의 상한도 따라 줄어든다", async ({ page }) => {
    await page.goto("/history");
    await expect(page.locator('[data-testid="scroll-pane"]').first())
      .toBeVisible({ timeout: TIMEOUT });
    const [tall] = await panes(page);

    await page.setViewportSize({ width: 1280, height: 520 });
    await page.waitForTimeout(700);
    const [short] = await panes(page);

    // ⚠️ 잴 것은 **상한**(`max-height`)이지 실제 높이가 아니다 — 내용이 짧으면
    // 실제 높이는 상한보다 작아 창을 줄여도 안 변한다(초판이 여기서 틀렸다).
    expect(tall.maxHeightPx).not.toBeNull();
    expect(short.maxHeightPx).not.toBeNull();
    expect(short.maxHeightPx!).toBeLessThan(tall.maxHeightPx!);
    expect(short.maxHeightPx!).toBeLessThanOrEqual(short.vh);
  });

  test("G-E2E-11d: 대시보드의 모든 표가 불변식 넷을 지킨다", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="scroll-pane"]').first())
      .toBeVisible({ timeout: TIMEOUT });
    await page.waitForTimeout(800);

    const all = (await panes(page)).filter((g) => g.height > 0);
    expect(all.length, "대시보드에 scroll-pane 이 없다").toBeGreaterThan(0);

    for (const g of all) {
      // ① 상한이 반드시 걸린다
      expect(g.maxHeightRaw).not.toBe("none");
      expect(g.maxHeightPx).not.toBeNull();
      // ② 창 높이를 넘지 않는다
      expect(g.maxHeightPx!).toBeLessThanOrEqual(g.vh);
      // ③ 🔴 최소 높이에 갇히지 않는다 — 화면 밖 표도 제 크기를 갖는다
      expect(g.maxHeightPx!).toBeGreaterThan(MIN_HEIGHT_PX);
      // ④ 화면 안에 있는 표는 바닥도 화면 안이다
      if (g.top >= 0 && g.top < g.vh) {
        expect(g.bottom).toBeLessThanOrEqual(g.vh + 1);
      }
    }
  });
});
