/**
 * 사이클 104 (2026-06-11) — 전략 현황 E2E spec.
 *
 * 10 케이스 매트릭스 (HIGH 4 + MEDIUM 3 + LOW 2 = 9 케이스)
 *
 * 사이클 86 답습 패턴:
 *   - installApiMocks 영속 (사이클 103 /api/strategies GET LIFO 등록 영속)
 *   - 사이클 80 hotfix #2 답습: timeout 20s (Suspense lazy + useQuery)
 *   - 사이클 80 hotfix #3 답습: Playwright LIFO 정합 (api-mocks 영속)
 *   - 사이클 89 한글 친숙 용어 영속 ("손절 임계" / "일일 손실 한도" 등)
 *
 * production 코드 변경 0 — spec 파일 신규 단일 산출물.
 */

import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

// ────────────────────────────────────────────────────────────────────────
// HIGH 케이스 4
// ────────────────────────────────────────────────────────────────────────

test.describe("H-ST1 (HIGH) — momentum 전략 카드 testid 렌더 visible", () => {
  test("momentum strategy-card testid + 상한가 모멘텀 이름 visible", async ({ page }) => {
    // 사이클 103 api-mocks /api/strategies GET LIFO 등록 영속
    await installApiMocks(page);
    await page.goto("/strategies");

    // 사이클 80 hotfix #2 답습 — timeout 20s
    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    // 전략명 한글 표시 (mock: "상한가 모멘텀")
    const card = page.getByTestId("strategy-card-momentum");
    await expect(card.getByText("상한가 모멘텀")).toBeVisible({ timeout: 20000 });
  });
});

test.describe("H-ST2 (HIGH) — 4 임계 한글 라벨 visible", () => {
  test("손절 임계 / 일일 손실 한도 / 트레일링 임계 / 종목당 비율 라벨 visible (사이클 89 영속)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/strategies");

    // 카드 렌더 대기
    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    const card = page.getByTestId("strategy-card-momentum");

    // 4 임계 한글 라벨 (Strategies.tsx PARAM_LABELS 영속)
    await expect(card.getByText("손절 임계")).toBeVisible({ timeout: 20000 });
    await expect(card.getByText("일일 손실 한도")).toBeVisible({ timeout: 20000 });
    await expect(card.getByText("트레일링 임계")).toBeVisible({ timeout: 20000 });
    await expect(card.getByText("종목당 비율")).toBeVisible({ timeout: 20000 });
  });
});

test.describe("H-ST3 (HIGH) — api-mocks ECONNREFUSED 0건 (LIFO 정합 영속)", () => {
  test("strategies 진입 시 /api/strategies network failure 0건", async ({ page }) => {
    // 사이클 80 hotfix #3 — Playwright LIFO 정합 영속
    const failedUrls: string[] = [];

    page.on("requestfailed", (request) => {
      const url = request.url();
      if (url.includes("/api/strategies")) {
        failedUrls.push(url);
      }
    });

    await installApiMocks(page);
    await page.goto("/strategies");

    // 카드 렌더 완료까지 대기 (모든 API 요청 완료 보장)
    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    // /api/strategies 호출 실패 0건 검증
    expect(failedUrls).toHaveLength(0);
  });
});

test.describe("H-ST4 (HIGH) — 페이지 제목 visible", () => {
  test("'전략 현황' 제목 visible (사이클 89 한글 친숙 용어 영속)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/strategies");

    await expect(
      page.getByText("전략 현황").first()
    ).toBeVisible({ timeout: 20000 });
  });
});

// ────────────────────────────────────────────────────────────────────────
// MEDIUM 케이스 3
// ────────────────────────────────────────────────────────────────────────

test.describe("M-ST5 (MEDIUM) — momentum 손절 임계 값 렌더", () => {
  test("stop_loss_rate mock -7.5% → '+' 없는 음수 표시 검증", async ({ page }) => {
    // api-mocks: momentum.params.stop_loss_rate = -7.5
    await installApiMocks(page);
    await page.goto("/strategies");

    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    // stop_loss_rate testid 검증 (Strategies.tsx testId 영속: strategy-{key}-{key_dashed})
    const stopLossEl = page.getByTestId("strategy-momentum-stop-loss-rate");
    await expect(stopLossEl).toBeVisible({ timeout: 20000 });

    // -7.5 → formatPercent → "-7.5%" (음수이므로 '+' 없음)
    await expect(stopLossEl).toContainText("-7.5%");
  });
});

test.describe("M-ST6 (MEDIUM) — 전략 활성/비활성 배지 visible", () => {
  test("momentum enabled=true → '활성' 배지 visible", async ({ page }) => {
    // api-mocks: momentum.enabled = true
    await installApiMocks(page);
    await page.goto("/strategies");

    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    const card = page.getByTestId("strategy-card-momentum");
    await expect(card.getByText("활성")).toBeVisible({ timeout: 20000 });
  });
});

test.describe("M-ST7 (MEDIUM) — 안내 배너 visible", () => {
  test("손절/손실 임계 안내 배너 visible (사이클 89 한글 영속)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/strategies");

    // 카드 렌더 대기
    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    // 안내 배너 텍스트 (Strategies.tsx 하단 amber 배너 영속)
    await expect(
      page.getByText("손절·일일 손실 한도는 음수(파란색) 표시").first()
    ).toBeVisible({ timeout: 20000 });
  });
});

// ────────────────────────────────────────────────────────────────────────
// LOW 케이스 2
// ────────────────────────────────────────────────────────────────────────

test.describe("L-NAV2 (LOW) — PC 메뉴 '전략 현황' 클릭 → 라우트 진입", () => {
  test("PC 메뉴에서 전략 현황 클릭 시 /strategies URL + 카드 렌더", async ({ page }) => {
    // 사이클 103 9번째 메뉴 영속 검증
    await installApiMocks(page);
    await page.goto("/");

    // PC viewport (기본) — 가로 메뉴에서 `전략 현황` 링크 클릭
    await page.getByRole("link", { name: "전략 현황" }).first().click();

    // URL /strategies 전환 검증
    await expect(page).toHaveURL(/\/strategies/);

    // 카드 렌더 완료 검증 (사이클 80 hotfix #2 답습 timeout 20s)
    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe("L-ST8 (LOW) — Lazy 로딩 + Suspense fallback 정상 전환", () => {
  test("Strategies lazy import 후 본체 mount 완료 (Suspense fallback → 카드 렌더)", async ({ page }) => {
    // 사이클 85 StockMaster lazy 패턴 답습 (App.tsx React.lazy)
    await installApiMocks(page);
    await page.goto("/strategies");

    // PageFallback 이 표시되다가 Suspense 해제 후 카드 렌더 완료
    await expect(
      page.getByTestId("strategy-card-momentum")
    ).toBeVisible({ timeout: 20000 });

    // 페이지 제목 텍스트 확인
    await expect(page.getByText("전략 현황").first()).toBeVisible({ timeout: 20000 });
  });
});
