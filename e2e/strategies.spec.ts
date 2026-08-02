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

// ────────────────────────────────────────────────────────────────────────
// 사이클 F 추가 — TE(트레이딩 예지치)/RR(손익비) 성과 섹션 표본 게이트 3분기 E2E
// (tester-cycleF 인계: vitest 10케이스가 렌더 로직을 커버하나 실브라우저 E2E 미검증 갭)
// ────────────────────────────────────────────────────────────────────────

test.describe("F-ST1 — N<20 표본 부족 뮤트 (판정 유보, 게이지/구조 숨김)", () => {
  test("insufficient tier → 판정 유보 배지 + RR 게이지/구조 태그 부재 + raw 승패N 캡션", async ({ page }) => {
    await installApiMocks(page, {
      teMetrics: [
        {
          strategy_id: "momentum",
          n: 9,
          win: 2,
          loss: 5,
          even: 2,
          win_rate: 2 / 9,
          avg_win_pct: 8.1,
          avg_loss_pct: -5.4,
          te_pct: -4.42,
          te_krw_avg: -19800,
          realized_sum_krw: -178200,
          rr: null,
          required_rr: null,
          rr_margin: null,
          rr_available: false,
          sample_tier: "insufficient",
          verdict: "undecided",
          structure_tag: null,
          single_trade_dominant: false,
        },
      ],
    });
    await page.goto("/strategies");

    await expect(
      page.getByTestId("te-section-momentum")
    ).toBeVisible({ timeout: 20000 });

    await expect(page.getByTestId("te-verdict-momentum")).toContainText("판정 유보");
    await expect(page.getByTestId("rr-gauge-fill-momentum")).toHaveCount(0);
    await expect(page.getByTestId("te-structure-momentum")).toHaveCount(0);
    await expect(page.getByTestId("te-sample-caption-momentum")).toContainText("표본 부족");
    await expect(page.getByTestId("te-sample-caption-momentum")).toContainText("9건");
  });
});

test.describe("F-ST2 — 20<=N<50 정상 표본 (RR 게이지 표시 + amber 추세 참고 캡션)", () => {
  test("low tier + rr_available → 우위 배지 + RR 게이지 채움/마커 + 구조 태그 + amber 캡션", async ({ page }) => {
    await installApiMocks(page, {
      teMetrics: [
        {
          strategy_id: "momentum",
          n: 21,
          win: 8,
          loss: 13,
          even: 0,
          win_rate: 8 / 21,
          avg_win_pct: 6.2,
          avg_loss_pct: -2.1,
          te_pct: 1.5,
          te_krw_avg: 15238,
          realized_sum_krw: 320000,
          rr: 3.0,
          required_rr: 1.86,
          rr_margin: 1.14,
          rr_available: true,
          sample_tier: "low",
          verdict: "superior",
          structure_tag: "robust",
          single_trade_dominant: false,
        },
      ],
    });
    await page.goto("/strategies");

    await expect(
      page.getByTestId("te-section-momentum")
    ).toBeVisible({ timeout: 20000 });

    await expect(page.getByTestId("te-verdict-momentum")).toContainText("우위");
    await expect(page.getByTestId("rr-gauge-fill-momentum")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("rr-gauge-marker-momentum")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("te-structure-momentum")).toContainText("견고형");
    await expect(page.getByTestId("te-sample-caption-momentum")).toContainText("표본 적음");
  });
});

test.describe("F-ST3 — N>=50 정상 표본 + 단일거래 의존 플래그", () => {
  test("normal tier + single_trade_dominant → 'RR 과대 가능' 캡션 visible", async ({ page }) => {
    await installApiMocks(page, {
      teMetrics: [
        {
          strategy_id: "momentum",
          n: 55,
          win: 20,
          loss: 15,
          even: 0,
          win_rate: 20 / 55,
          avg_win_pct: 5.0,
          avg_loss_pct: -3.0,
          te_pct: 0.6,
          te_krw_avg: 9000,
          realized_sum_krw: 495000,
          rr: 1.67,
          required_rr: 0.75,
          rr_margin: 0.92,
          rr_available: true,
          sample_tier: "normal",
          verdict: "superior",
          structure_tag: "robust",
          single_trade_dominant: true,
        },
      ],
    });
    await page.goto("/strategies");

    await expect(
      page.getByTestId("te-section-momentum")
    ).toBeVisible({ timeout: 20000 });

    await expect(page.getByTestId("te-sample-caption-momentum")).toContainText("RR 과대 가능");

    // 페이지 하단 참조표 + 교육 캡션 (1회) 도 실브라우저에서 확인
    await expect(page.getByTestId("te-reference-table")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("te-education-caption")).toContainText("TE는 거래당 기대손익");
  });
});
