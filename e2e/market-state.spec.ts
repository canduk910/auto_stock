/**
 * cycle282 Red — 장운영상태 화면 E2E (`G-E2E-282`, 명세 §7.2 E2E-1~3).
 *
 * 명세 정본: `_workspace/red/cycle282_market_state_spec.md`
 *
 * 이 화면은 사용자의 한 문장에서 나왔다 — "현재 장운영상태와 함께 **어떤 호가유형을 쓸 수
 * 있는지** 알 수 있게 하자." 그래서 실브라우저에서 재야 하는 것은 세 가지다:
 *   ① 메뉴를 눌러 들어갈 수 있는가, 그리고 **커서가 시장마다 정확히 하나**인가
 *   ② 주문유형 카탈로그가 "미지원(빈칸)" 과 "미확인(?)" 을 **다른 것으로** 보여주는가
 *   ③ 미확인 행(K1·N3·N5)이 **숨겨지지 않고** 확인 필요로 드러나는가
 *
 * ②·③ 이 이 사이클의 정직성 계약이다. 표에는 아직 모르는 칸이 있고, 그 모름을 화면에서
 * 지우면 우리는 "모른다" 를 "없다"/"된다" 로 바꿔 말하게 된다.
 *
 * 기대값은 전부 `fixtures/market-state.fixture.ts`(=목 본문)에서 읽는다 — 목과 단언이
 * 같은 출처를 보므로, 표가 바뀌면 둘이 함께 움직인다.
 *
 * 파일 위치는 리포 관례(기존 spec 전부 `e2e/` 바로 아래, `testDir: "."`)를 따른다.
 * production 코드 변경 0 — spec + 목 append 만.
 */
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";
import { MARKET_STATE_FIXTURE } from "./fixtures/market-state.fixture";

const T = { timeout: 20000 };

const FIXTURE = MARKET_STATE_FIXTURE;

/** 목 응답이 그 날짜의 커서를 실제로 담고 있는가 — 아니면 아래 단언들이 공허해진다. */
function cursors() {
  const markets = FIXTURE.markets;
  if (!markets) throw new Error("목 기본 변종은 커서를 담은 '지금' 응답이어야 한다");
  return markets;
}

test.describe("G-E2E-282a — 메뉴 진입과 커서", () => {
  test("나브에서 장운영상태로 들어가면 시장별 카드와 커서 행이 보인다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/");

    // cycle288 — "장운영상태"는 "운영상태" 그룹 하위. 트리거를 먼저 열어야 링크가 보인다.
    await page.getByRole("button", { name: "운영상태", exact: true }).click();
    await page.getByRole("link", { name: "장운영상태" }).first().click();
    await expect(page).toHaveURL(/\/market-state$/, T);
    await expect(page.getByTestId("market-state-page")).toBeVisible(T);

    // 카드 = market_order 그대로
    for (const market of FIXTURE.market_order) {
      const card = page.getByTestId(`market-state-card-${market}`);
      await expect(card).toBeVisible(T);
      await expect(card).toHaveAttribute("data-phase", cursors()[market].phase);
    }

    // 커서는 시장마다 **정확히 하나**. 둘이면 표가 겹친 것이고, 0 이면 표와 커서가 갈라진 것이다(M9).
    for (const market of FIXTURE.market_order) {
      const current = page.locator(
        `[data-testid^="market-state-row-"][data-market="${market}"][data-rel="current"]`,
      );
      await expect(current).toHaveCount(1, T);
      await expect(current).toHaveAttribute(
        "data-testid",
        `market-state-row-${cursors()[market].row_id}`,
      );
    }

    // 지금 쓸 수 있는 주문유형 칩 — 사용자 질문의 직접적인 답이다. 비어 있으면 화면이 무의미하다.
    for (const market of FIXTURE.market_order) {
      const cursor = cursors()[market];
      expect(cursor.order_divisions.length).toBeGreaterThan(0);
      for (const code of cursor.order_divisions) {
        await expect(
          page.getByTestId(`market-state-card-division-${market}-${code}`),
        ).toBeVisible(T);
      }
      await expect(
        page.getByTestId(`market-state-card-market-order-${market}`),
      ).toHaveAttribute("data-ok", String(cursor.market_order_ok), T);
    }
  });
});

test.describe("G-E2E-282b — 주문유형 카탈로그의 3상태", () => {
  test("미지원(빈칸)과 미확인(?)을 다르게 보여준다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/market-state");
    await expect(page.getByTestId("market-state-page")).toBeVisible(T);

    const catalog = page.getByTestId("market-state-catalog");
    await expect(catalog).toBeVisible(T);
    await expect(
      catalog.locator('[data-testid^="market-state-catalog-row-"]'),
    ).toHaveCount(FIXTURE.order_divisions.length, T);

    // 표가 드러낸 두 사실을 픽스처 자체에 대고 먼저 못박는다 — 데이터가 바뀌면 여기서 먼저 붉어진다.
    const byCode = (code: string) => {
      const row = FIXTURE.order_divisions.find((d) => d.code === code);
      if (!row) throw new Error(`카탈로그에 없는 코드: ${code}`);
      return row;
    };
    for (const code of ["05", "06", "07"]) {
      expect(byCode(code).exchange_support["SOR"], `${code}: SOR 미지원(발견 2)`).toBe("no");
    }
    expect(byCode("01").exchange_support["NXT"], "01: NXT 시장가 없음(발견 1)").toBe("no");
    expect(byCode("27").exchange_support["SOR"], "27: SOR 지원 미확인(Q4)").toBe("unknown");

    // 화면이 그 세 상태를 각각 다른 값으로 실어 나른다.
    for (const division of FIXTURE.order_divisions) {
      for (const exchange of FIXTURE.exchange_order) {
        await expect(
          page.getByTestId(`market-state-catalog-cell-${division.code}-${exchange}`),
        ).toHaveAttribute("data-support", division.exchange_support[exchange], T);
      }
    }

    // 발견 2건이 표 아래에 그대로 보인다 — 이 화면이 조사에서 얻은 결론이다.
    for (let i = 0; i < FIXTURE.findings.length; i += 1) {
      await expect(page.getByTestId(`market-state-finding-${i}`)).toContainText(
        FIXTURE.findings[i],
        T,
      );
    }
    await expect(page.getByTestId("market-state-board-note")).toContainText(
      FIXTURE.board_note,
      T,
    );
  });
});

test.describe("G-E2E-282c — 모르는 것은 숨기지 않는다", () => {
  test("미확인 행에 확인 필요 배지가 보인다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/market-state");
    await expect(page.getByTestId("market-state-page")).toBeVisible(T);

    const unconfirmed = FIXTURE.table.filter((r) => r.confidence !== "confirmed");
    // K1(시가 단일가 시작 시각) · N3(정규장 시작 09:00:30) · N5(애프터 단일가 주문유형) 셋.
    expect(unconfirmed.length, "미확인 행이 사라지면 이 테스트는 아무것도 안 막는다").toBe(3);

    for (const row of FIXTURE.table) {
      const el = page.getByTestId(`market-state-row-${row.row_id}`);
      await expect(el).toHaveAttribute("data-confidence", row.confidence, T);
      const marks = el.getByText(/확인 필요/);
      if (row.confidence === "confirmed") {
        await expect(marks).toHaveCount(0, T);
      } else {
        await expect(marks.first()).toBeVisible(T);
        // 사유까지 함께 — 배지만 띄우고 왜인지를 숨기면 사용자는 무엇을 확인해야 할지 모른다.
        await expect(page.getByTestId(`market-state-row-note-${row.row_id}`)).toContainText(
          row.note.slice(0, 20),
          T,
        );
      }
    }

    // 시행 전 코드(09-14 부터인 27~29)도 지우지 않고 배지로 남긴다.
    const pendingRows = FIXTURE.table.filter((r) => r.order_divisions_pending.length > 0);
    expect(pendingRows.length).toBeGreaterThan(0);
    for (const row of pendingRows) {
      for (const code of row.order_divisions_pending) {
        await expect(
          page.getByTestId(`market-state-row-pending-${row.row_id}-${code}`),
        ).toBeVisible(T);
      }
    }
  });
});

test.describe("G-E2E-285 — 야간작업 현황 + 실시간 장운영 (cycle285)", () => {
  test("지금 시장은 섹션과 오늘 야간작업 타임라인이 기존 표 아래 함께 보인다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/market-state");
    await expect(page.getByTestId("market-state-page")).toBeVisible(T);

    // 섹션 A — 실시간 장운영(백엔드 신규 0, 기존 /api/realtime/market-operation 재사용)
    await expect(page.getByTestId("market-state-now-section")).toBeVisible(T);
    // test 렌즈 LOW #11 — 본문 제목은 testid 가 아니라 role 로도 고정한다(frontend/CLAUDE.md
    // cycle288 지침). testid 만 단언하면 <h2> 텍스트가 바뀌어도 아무것도 안 붉어진다.
    await expect(
      page.getByTestId("market-state-now-section").getByRole("heading", { name: "지금 시장은" }),
    ).toBeVisible(T);
    await expect(page.getByTestId("market-state-now-vi")).toBeVisible(T);
    await expect(page.getByTestId("market-state-now-halt")).toBeVisible(T);
    await expect(page.getByTestId("market-state-now-cb")).toBeVisible(T);
    // §4-2 — 관측 커버리지 한계 문구가 실제로 화면에 있어야 한다
    await expect(page.getByTestId("market-state-now-coverage-note")).toContainText(
      "관측 대상",
      T,
    );

    // 섹션 B — 야간작업 현황(신규 GET /api/market-ops)
    await expect(page.getByTestId("market-state-ops-section")).toBeVisible(T);
    await expect(
      page.getByTestId("market-state-ops-section").getByRole("heading", { name: "오늘 야간작업" }),
    ).toBeVisible(T);
    await expect(page.getByTestId("market-state-ops-table")).toBeVisible(T);
    await expect(page.getByTestId("market-state-ops-status-recommendation")).toContainText(
      "완료",
      T,
    );
    await expect(page.getByTestId("market-state-ops-status-quote_token_refresh")).toContainText(
      "확인 불가",
      T,
    );

    // 기존 (2) 표는 무접촉 — 여전히 그 아래 정상 렌더
    await expect(page.getByTestId("market-state-table")).toBeVisible(T);
  });
});
