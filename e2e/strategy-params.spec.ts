/**
 * cycle278 — 전략 파라미터 카탈로그 편집 E2E (`G-E2E-278`).
 *
 * 명세: `_workspace/red/cycle278_param_catalog_ui_spec.md` §7.3
 *
 * 이 사이클 이전에는 화면에서 파라미터를 고칠 수단이 사실상 없었다(구 `Settings.tsx` 패널은
 * 24키 화이트리스트 ∩ number 로 이중 게이팅돼 99키 중 73키가 구조적으로 편집 불가). 그래서
 * 값 변경은 전부 curl/스크립트로 이뤄졌고, 오타·범위 밖 값은 **성공 응답을 받고 조용히 버려졌다**.
 * 이 spec 은 그 반대편을 실브라우저로 잰다 — 사람이 화면에서 고치고, 서버가 거절하면 그 이유가
 * 그 입력 칸 옆에 붙고, 패널은 닫히지 않는다.
 *
 * 파일 위치는 리포 관례를 따른다(기존 spec 6개가 전부 `e2e/` 바로 아래, `testDir: "."`).
 * 명세 §7.3 의 `e2e/tests/` 경로는 현행 배치와 다르다 — 결과 보고의 이견 항목 참조.
 *
 * production 코드 변경 0 — spec + 목 append 만.
 */
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

const T = { timeout: 20000 };

/** 아코디언 그룹을 연다(이미 열려 있으면 그대로). */
async function openGroup(page: import("@playwright/test").Page, groupId: string) {
  const body = page.getByTestId(`strategy-params-group-body-${groupId}`);
  if ((await body.count()) === 0) {
    await page.getByTestId(`strategy-params-group-${groupId}`).click();
  }
  await expect(body).toBeVisible(T);
  return body;
}

test.describe("G-E2E-278a — 편집 → diff → 정체성 2단계 확인 → 저장 → 목록 갱신", () => {
  test("percent 키와 identity 키를 함께 고쳐 저장하면 카드 요약이 갱신된다", async ({
    page,
  }) => {
    await installApiMocks(page);

    // 저장 성공 후 목록이 새 값을 준다 — LIFO 라 installApiMocks 뒤에 등록해야 이긴다.
    let saved = false;
    await page.route("**/api/strategies", (route) =>
      route.fulfill({
        json: {
          success: true,
          data: {
            momentum: {
              key: "momentum",
              name: "상한가 모멘텀",
              enabled: true,
              weight: 0.5,
              total_investment: 50_000_000,
              params: {
                position_ratio: saved ? 0.2 : 0.25,
                max_positions: saved ? 3 : 4,
                stop_loss_rate: -7.5,
                daily_loss_limit: -5.0,
                trailing_stop_rate: -2.0,
              },
            },
          },
          message: "",
        },
      }),
    );
    await page.route("**/api/strategies/*/params", (route) => {
      if (route.request().method() !== "PUT") return route.fallback();
      saved = true;
      return route.fulfill({
        json: {
          success: true,
          data: { applied: { position_ratio: 0.2, max_positions: 3 }, warnings: [] },
          message: "파라미터 저장 완료",
        },
      });
    });

    await page.goto("/strategies");
    await expect(page.getByTestId("strategy-card-momentum")).toBeVisible(T);
    await expect(page.getByTestId("strategy-momentum-position-ratio")).toContainText("25%");

    // 편집기 진입
    await page.getByTestId("strategy-params-open-momentum").click();
    await expect(page.getByTestId("strategy-params-editor")).toBeVisible(T);
    await expect(page.getByTestId("strategy-params-title")).toContainText("상한가 모멘텀");

    // percent 키 — 저장은 비율, 화면은 %
    await openGroup(page, "sizing_risk");
    const ratio = page.getByTestId("strategy-params-input-position-ratio");
    await expect(ratio).toHaveValue(/^25(\.0+)?$/, T);
    await ratio.fill("20");

    // 변경분 미리보기
    const diffRow = page.getByTestId("strategy-params-diff-row-position-ratio");
    await expect(diffRow).toBeVisible(T);
    await expect(diffRow).toContainText("25");
    await expect(diffRow).toContainText("20");

    // identity 키 — 2단계 확인 전에는 저장 불가
    await page.getByTestId("strategy-params-input-max-positions").fill("3");
    const ack = page.getByTestId("strategy-params-identity-ack");
    await expect(ack).toBeVisible(T);
    await expect(page.getByTestId("strategy-params-save")).toBeDisabled(T);
    await ack.check();
    await expect(page.getByTestId("strategy-params-save")).toBeEnabled(T);

    // 저장 → 공용 ConfirmModal 확인
    await page.getByTestId("strategy-params-save").click();
    await page.getByRole("button", { name: "확인" }).click();

    // 패널이 닫히고 카드 요약이 새 값으로 갱신된다
    await expect(page.getByTestId("strategy-params-editor")).toHaveCount(0, T);
    await expect(page.getByTestId("strategy-momentum-position-ratio")).toContainText("20%", T);
  });
});

test.describe("G-E2E-278b — 범위 밖 값은 422 로 거절되고 그 행에 이유가 붙는다", () => {
  test("종목당 비중 150% 저장 → 422 → 필드 오류 표시 + 패널 유지", async ({ page }) => {
    // installApiMocks 의 PUT 라우트가 position_ratio > 1.0 을 422 로 돌려준다.
    await installApiMocks(page);
    await page.goto("/strategies");

    await expect(page.getByTestId("strategy-card-momentum")).toBeVisible(T);
    await page.getByTestId("strategy-params-open-momentum").click();
    await expect(page.getByTestId("strategy-params-editor")).toBeVisible(T);

    await openGroup(page, "sizing_risk");
    await page.getByTestId("strategy-params-input-position-ratio").fill("150");

    await page.getByTestId("strategy-params-save").click();
    await page.getByRole("button", { name: "확인" }).click();

    const fieldError = page.getByTestId("strategy-params-error-position-ratio");
    await expect(fieldError).toBeVisible(T);
    await expect(fieldError).toContainText("0.01 ~ 1.0");

    // 오류를 띄운 채 패널을 닫으면 고칠 화면이 사라진다.
    await expect(page.getByTestId("strategy-params-editor")).toBeVisible(T);
  });
});
