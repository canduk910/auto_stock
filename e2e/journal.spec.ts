/**
 * cycle413 보완 1차 (2026-10-09) — 「거래 내역」 세 번째 탭 「거래일지」 E2E (G-E2E-12, 판정 #13).
 *
 * 판정 원문 = scratchpad `c413/fix/verdict1.md` #2·#3·#13 · 명세 = `_workspace/red/cycle413/journal_view_spec.md` 8절.
 *
 * 왜 실브라우저인가 — #2(메모가 지워짐)는 **운영 QueryClient 캐시**(staleTime 3초·gcTime 5분)에서만 드러난다.
 * 단위 테스트 기본 QueryClient(gcTime 0)는 탭을 오갈 때마다 새로 받아 결함을 가렸다. 이 spec 은 앱의 실제
 * QueryClient 로 「저장 → 다른 탭 → 돌아오기」 를 밟는다.
 *
 * 목 = `fixtures/api-mocks.ts` 의 `/api/history/journal`(상태형 메모 · 요청 page 별 응답). 응답 본문은 MSW 목과 같은
 * `frontend/src/test/fixtures/journal.fixture.ts` 다.
 * 사이클 65 hotfix #3 답습 — 모든 `toBeVisible()` 에 명시 timeout.
 *
 * RED: J-E2(탭 왕복 뒤 메모가 옛 값/빈 칸 · 저장 버튼이 켜져 있음) · J-E3(페이지 넘김 UI 없음).
 */

import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";
import {
  JOURNAL_ANCHOR_BFB as BFB,
  JOURNAL_ANCHOR_OPEN as OPEN,
  JOURNAL_ANCHOR_VB as VB,
  JOURNAL_FIXTURE,
} from "../frontend/src/test/fixtures/journal.fixture";

type AnyJson = Record<string, unknown>;

async function openJournal(page: import("@playwright/test").Page) {
  await page.goto("/history");
  await page.getByTestId("history-tab-journal").click();
  await expect(page.getByTestId(`journal-card-${BFB}`)).toBeVisible({ timeout: 20000 });
}

test.describe("G-E2E-12 (cycle413 보완 1차) — 거래일지 탭", () => {
  test("J-E1 탭을 누르면 카드 3장 · 기록 시작일 · 서버 문장이 선다", async ({ page }) => {
    await installApiMocks(page);
    await openJournal(page);
    await expect(page.getByTestId(`journal-card-${OPEN}`)).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId(`journal-card-${VB}`)).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("journal-record-start")).toContainText("2026-09-17");
    const bfb = page.getByTestId(`journal-card-${BFB}`);
    await expect(bfb.getByTestId("journal-entry-reason")).toContainText("깃발 상단 12,300 돌파");
    await expect(bfb.getByTestId("journal-head-pnl")).toContainText("+41,464");
    await expect(page.locator("body")).not.toContainText("NaN");
    await expect(page.locator("body")).not.toContainText("거래일지를 불러올 수 없습니다");
  });

  test("J-E2 메모 저장 → 다른 탭 → 돌아와도 저장한 값 · 저장 버튼 꺼짐 · 빈 body PUT 0", async ({ page }) => {
    const puts: Array<{ id: string; body: string }> = [];
    await installApiMocks(page, { journalPuts: puts });
    await openJournal(page);

    const open = page.getByTestId(`journal-card-${OPEN}`);
    const input = open.getByTestId("journal-note-input");
    const save = open.getByTestId("journal-note-save");
    await expect(save).toBeDisabled();                  // 메모 없음 + 바뀐 것 없음
    await input.fill("실브라우저 메모");
    await save.click();
    await expect(open).toContainText("저장됨", { timeout: 10000 });
    expect(puts).toEqual([{ id: OPEN, body: "실브라우저 메모" }]);

    await page.getByRole("button", { name: "주문체결내역" }).click();
    await expect(page.getByTestId(`journal-card-${OPEN}`)).toHaveCount(0, { timeout: 10000 });
    await page.getByTestId("history-tab-journal").click();
    const input2 = page.getByTestId(`journal-card-${OPEN}`).getByTestId("journal-note-input");
    await expect(input2).toHaveValue("실브라우저 메모", { timeout: 10000 });
    const save2 = page.getByTestId(`journal-card-${OPEN}`).getByTestId("journal-note-save");
    await expect(save2).toBeDisabled();
    await save2.click({ force: true });
    await page.waitForTimeout(300);
    expect(puts.filter((p) => p.body.trim() === "")).toEqual([]);
  });

  test("J-E3 「총 21」 이면 다음 쪽으로 넘겨 나머지 카드를 본다", async ({ page }) => {
    const base = JSON.parse(JSON.stringify(JOURNAL_FIXTURE)) as AnyJson & { cards: AnyJson[] };
    const meta = { total: 21, total_pages: 2, counts: { total: 21, open: 1, closed: 20 } };
    const p1 = { ...base, ...meta, page: 1, cards: base.cards.slice(0, 2) };
    const p2 = { ...base, ...meta, page: 2, cards: base.cards.slice(2) };
    const pages: string[] = [];
    page.on("request", (req) => {
      const u = new URL(req.url());
      if (u.pathname === "/api/history/journal") pages.push(u.searchParams.get("page") ?? "");
    });
    await installApiMocks(page, { journalPages: { "1": p1, "2": p2 } });
    await openJournal(page);
    await expect(page.getByTestId(`journal-card-${VB}`)).toHaveCount(0);
    await expect(page.getByTestId("journal-page-info")).toContainText(/1\s*\/\s*2/, { timeout: 10000 });
    await page.getByTestId("journal-page-next").click();
    await expect(page.getByTestId(`journal-card-${VB}`)).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("journal-page-info")).toContainText(/2\s*\/\s*2/);
    expect(pages).toContain("2");
  });
});
