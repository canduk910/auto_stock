/**
 * Red — TradePnLGrid 실현손익 요약 바 + 전략 필터 kojiro 추가.
 *
 * 명세: team-lead 메시지 「매매손익 (1) 실현손익 요약 바 + (2) kojiro 필터」.
 * Red 메모: `_workspace/red/pnl_summary_kojiro_filter.md`.
 *
 * 요구 행위:
 *  (a) `data.summary` 값으로 요약 바(testid `pnl-summary`) 렌더 —
 *      실현 합계·손익율·승/패/보합·승률 + 현재 전략 필터 라벨.
 *  (b) 실현손익 값(testid `pnl-summary-realized`)이 양수면 이익색(text-red)/
 *      음수면 손실색(text-blue) — 프로젝트 컨벤션(이익=빨강, 손실=파랑).
 *  (c) 전략 select 에 kojiro(고지로 대순환) option 존재.
 *  (d) 전략을 kojiro 로 변경 시 strategy=kojiro 로 재조회.
 *
 * RED: 현재 TradePnLGrid 는 요약 바 미렌더 + kojiro option 부재 →
 * findByTestId('pnl-summary') 타임아웃 / kojiro option 미존재로 전 케이스 실패.
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import {
  makeLlmEvaluation,
  makeLlmEvaluationSummary,
  makeTradePair,
  wrap,
} from "../../test/factories";
import { TestProviders } from "../../test/providers";
import TradePnLGrid from "../TradePnLGrid";

interface SummaryShape {
  realized_total_krw: number;
  realized_rate_pct: number;
  win_count: number;
  loss_count: number;
  even_count: number;
  win_rate_pct: number;
  closed_count: number;
}

const EMPTY_SUMMARY: SummaryShape = {
  realized_total_krw: 0,
  realized_rate_pct: 0,
  win_count: 0,
  loss_count: 0,
  even_count: 0,
  win_rate_pct: 0,
  closed_count: 0,
};

function pnlPayload(summary: SummaryShape, pairs: unknown[] = []) {
  return wrap({
    pairs,
    summary,
    page: 1,
    size: 30,
    total: pairs.length,
    total_pages: pairs.length > 0 ? 1 : 0,
  });
}

describe("TradePnLGrid — 실현손익 요약 바 + kojiro 필터 (Red)", () => {
  // ---------------------------------------------------------------------
  // (a) 요약 바가 summary 값을 렌더한다
  // ---------------------------------------------------------------------
  it("요약 바에 실현 합계·손익율·승/패/보합·승률·전략 라벨을 렌더한다", async () => {
    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(
          pnlPayload({
            realized_total_krw: 600,
            realized_rate_pct: 2.0,
            win_count: 3,
            loss_count: 1,
            even_count: 2,
            win_rate_pct: 75.0,
            closed_count: 6,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    const summary = await screen.findByTestId("pnl-summary");
    const text = summary.textContent ?? "";
    // 실현 합계
    expect(text).toMatch(/실현/);
    expect(text).toMatch(/600/);
    // 손익율
    expect(text).toMatch(/2(\.0)?\s*%/);
    // 승/패/보합
    expect(text).toMatch(/승\s*3/);
    expect(text).toMatch(/패\s*1/);
    expect(text).toMatch(/보합\s*2/);
    // 승률
    expect(text).toMatch(/승률\s*75/);
    // 현재 전략 필터 라벨 (기본 = 전체)
    expect(text).toMatch(/전체/);
  });

  // ---------------------------------------------------------------------
  // (b) 실현손익 부호별 색상 (이익=빨강 / 손실=파랑)
  // ---------------------------------------------------------------------
  it("실현손익이 양수면 이익색(text-red), 음수면 손실색(text-blue)으로 표시한다", async () => {
    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(
          pnlPayload({
            ...EMPTY_SUMMARY,
            realized_total_krw: 1500,
            realized_rate_pct: 5.0,
            win_count: 2,
            win_rate_pct: 100.0,
            closed_count: 2,
          }),
        ),
      ),
    );

    const { unmount } = render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    const pos = await screen.findByTestId("pnl-summary-realized");
    expect(pos.className).toMatch(/text-red/); // 이익 = 빨강
    unmount();

    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(
          pnlPayload({
            ...EMPTY_SUMMARY,
            realized_total_krw: -1500,
            realized_rate_pct: -5.0,
            loss_count: 2,
            win_rate_pct: 0.0,
            closed_count: 2,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    const neg = await screen.findByTestId("pnl-summary-realized");
    expect(neg.className).toMatch(/text-blue/); // 손실 = 파랑
  });

  // ---------------------------------------------------------------------
  // (c) 전략 select 에 kojiro(고지로 대순환) option 존재
  // ---------------------------------------------------------------------
  it("전략 필터에 kojiro(고지로 대순환) 옵션이 있다", async () => {
    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(pnlPayload(EMPTY_SUMMARY)),
      ),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    // 로딩 종료 후 select 렌더 대기
    const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
    const option = within(select).getByRole("option", {
      name: "고지로 대순환",
    });
    expect(option).toHaveValue("kojiro");
  });

  // ---------------------------------------------------------------------
  // (d) 전략을 kojiro 로 바꾸면 strategy=kojiro 로 재조회한다
  // ---------------------------------------------------------------------
  it("전략을 kojiro 로 변경하면 strategy=kojiro 로 재조회한다", async () => {
    const seenStrategies: (string | null)[] = [];
    server.use(
      http.get("/api/history/pnl", ({ request }) => {
        seenStrategies.push(new URL(request.url).searchParams.get("strategy"));
        return HttpResponse.json(pnlPayload(EMPTY_SUMMARY));
      }),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    // 요약 바가 뜨면 최초 조회 완료 상태
    await screen.findByTestId("pnl-summary");

    const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
    await userEvent.selectOptions(select, "kojiro");

    await waitFor(() =>
      expect(seenStrategies).toContain("kojiro"),
    );
  });
});

// =======================================================================
// cycle276 Red — 매매손익 그리드 "AI 자문" 열 (F19~F24)
//
// 명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §8 / §10.3 / §11.2.
//
// 손익 화면은 **테이블이 아니다** — `get_trade_pairs` 가 `trade_history` 를 매번 읽어
// 계산하는 뷰라 행을 가리키는 안정적 키가 없었다. 그래서 페어는 `buy_order_nos`(복수!),
// `sell_order_nos`, `pair_key`(= `전략:종목:첫 매수 order_no`) 를 함께 내보낸다.
// 운영 DB 전 기간 614행 중 **9건**이 매수 주문 2건 이상을 품은 페어라 단수 필드는 불가.
//
// 계약:
//  - 맨 끝 열 "AI 자문". 활성 = `buy_order_nos.some(no => summaries[no])`.
//  - 비활성 = `buy_order_nos.length === 0`(수기 매매 등) 또는 전부 기록 없음.
//  - `buy_order_nos.length > 1` 이면 라벨 옆 `(n)` 배지.
//  - 배치 조회는 페이지의 모든 `buy_order_nos` 를 flat 하게 모아 **1회**.
//
// RED: 현재 그리드는 열도 버튼도 배치 조회도 없다 → F19~F23 실패(F24 는 회귀 보호).
// =======================================================================

const PAIR_A_BUY = "0000123456";
const PAIR_B_BUY_1 = "0000200001";
const PAIR_B_BUY_2 = "0000200002";

const PAIR_WITH_EVAL = makeTradePair({
  ticker: "005930",
  ticker_name: "삼성전자",
  strategy: "volatility_breakout",
  buy_order_nos: [PAIR_A_BUY],
  sell_order_nos: ["0000987654"],
  pair_key: `volatility_breakout:005930:${PAIR_A_BUY}`,
});

/** 매수 주문 2건이 뭉친 페어 — `(2)` 배지 + 모달 탭 대상. */
const PAIR_MULTI_BUY = makeTradePair({
  ticker: "042700",
  ticker_name: "한미반도체",
  strategy: "volatility_breakout",
  buy_price: 90000,
  buy_qty: 4,
  sell_price: 91000,
  sell_qty: 4,
  profit_loss: 4000,
  profit_rate: 1.11,
  buy_order_nos: [PAIR_B_BUY_1, PAIR_B_BUY_2],
  sell_order_nos: ["0000200099"],
  pair_key: `volatility_breakout:042700:${PAIR_B_BUY_1}`,
});

/** 수기 매매 등 order_no 가 빈 체결로 만들어진 페어 — 버튼 비활성. */
const PAIR_NO_ORDER_NO = makeTradePair({
  ticker: "073240",
  ticker_name: "금호타이어",
  strategy: "momentum",
  status: "open",
  sell_date: null,
  sell_time: null,
  sell_price: null,
  sell_qty: null,
  profit_loss: null,
  profit_rate: null,
  buy_order_nos: [],
  sell_order_nos: [],
  pair_key: null,
});

function pnlPage(pairs: unknown[]) {
  return wrap({
    pairs,
    page: 1,
    size: 30,
    total: pairs.length,
    total_pages: 1,
    summary: {
      realized_total_krw: 6100,
      realized_rate_pct: 1.2,
      win_count: 2,
      loss_count: 0,
      even_count: 0,
      win_rate_pct: 100,
      closed_count: 2,
    },
  });
}

/** 배치 응답 맵의 복합 키 — 라우트 `summary_key()` / 프론트 `llmEvalKey()` 와 같은 규약. */
const sumKey = (tradeDate: string, orderNo: string) => `${tradeDate}|${orderNo}`;

/** 페어 픽스처의 매수일(`makeTradePair` 기본값) — 요약 키의 날짜 축. */
const PAIR_BUY_DATE = "2026-09-11";

/**
 * 손익 그리드 목.
 *
 * `summaryOverrides` 로 "요약에는 있지만 날짜가 어긋난" 조합을 주입한다 — 배치 요약은
 * 날짜 없이 묻고 상세는 `pair.buy_date` 와 함께 묻기 때문에, 날짜 대조가 없으면
 * "버튼 활성 → 모달 404" 조합이 생긴다(KIS ODNO 는 하루 단위로만 유일).
 * `detailCalls` 는 상세 요청의 주문번호·`trade_date` 를 기록한다(F25b).
 */
function installPnlMocks(
  pairs: unknown[] = [PAIR_WITH_EVAL, PAIR_MULTI_BUY, PAIR_NO_ORDER_NO],
  summaryOverrides: Record<string, unknown> = {},
  // 그 주문번호의 **기본(매수일) 요약을 지운다**. 복합 키 맵에서는 "다른 날짜에만 기록이
  // 있다" 를 만들려면 같은 번호의 매수일 키가 없어야 한다 — 실제 라우트도 존재하는 행만
  // 돌려주므로 이쪽이 현실과 같은 목이다.
  omitOrderNos: string[] = [],
) {
  const batchCalls: string[] = [];
  const detailCalls: Array<{ orderNo: string; tradeDate: string | null }> = [];
  server.use(
    http.get("/api/history/pnl", () => HttpResponse.json(pnlPage(pairs))),
    http.get("/api/llm-evaluations", ({ request }) => {
      batchCalls.push(new URL(request.url).searchParams.get("order_nos") ?? "");
      const base: Record<string, unknown> = {
        [sumKey(PAIR_BUY_DATE, PAIR_A_BUY)]: makeLlmEvaluationSummary({
          order_no: PAIR_A_BUY,
          score: 62,
        }),
        [sumKey(PAIR_BUY_DATE, PAIR_B_BUY_1)]: makeLlmEvaluationSummary({
          order_no: PAIR_B_BUY_1,
          ticker: "042700",
          score: 77,
        }),
        [sumKey(PAIR_BUY_DATE, PAIR_B_BUY_2)]: makeLlmEvaluationSummary({
          order_no: PAIR_B_BUY_2,
          ticker: "042700",
          score: 81,
        }),
      };
      for (const no of omitOrderNos) delete base[sumKey(PAIR_BUY_DATE, no)];
      return HttpResponse.json(wrap({ ...base, ...summaryOverrides }));
    }),
    http.get("/api/llm-evaluations/:orderNo", ({ params, request }) => {
      detailCalls.push({
        orderNo: String(params.orderNo),
        tradeDate: new URL(request.url).searchParams.get("trade_date"),
      });
      return HttpResponse.json(
        wrap(makeLlmEvaluation({ order_no: String(params.orderNo), score: 77 })),
      );
    }),
  );
  return { batchCalls, detailCalls };
}

function renderPnlGrid() {
  render(
    <TestProviders>
      <TradePnLGrid />
    </TestProviders>,
  );
}

function rowOf(text: string): HTMLElement {
  const cell = screen.getByText(text);
  const row = cell.closest("tr");
  if (!row) throw new Error(`행을 찾지 못했다: ${text}`);
  return row as HTMLElement;
}

describe("cycle276 — TradePnLGrid AI 자문 열 (Red)", () => {
  it("F19 'AI 자문' 열을 렌더하고 buy_order_nos 기준으로 활성화한다", async () => {
    installPnlMocks();
    renderPnlGrid();

    await screen.findByText("삼성전자", {}, { timeout: 5000 });

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent?.trim());
    expect(headers[headers.length - 1]).toBe("AI 자문");

    const btn = await screen.findByTestId(
      `llm-eval-btn-pair-${PAIR_WITH_EVAL.pair_key}`,
      {},
      { timeout: 5000 },
    );
    expect(btn).toBeEnabled();
  });

  it("F20 buy_order_nos 가 빈 페어의 버튼은 비활성이다", async () => {
    installPnlMocks();
    renderPnlGrid();

    await screen.findByText("금호타이어", {}, { timeout: 5000 });

    const row = rowOf("금호타이어");
    const buttons = within(row).getAllByRole("button");
    expect(buttons).toHaveLength(1);
    const btn = buttons[0];
    expect(btn).toBeDisabled();
    // pair_key 가 null 인 행은 행 인덱스로 testid 를 만든다.
    expect(btn.getAttribute("data-testid")).toMatch(/^llm-eval-btn-pair-none-\d+$/);
    // 왜 못 누르는지 문면으로 알려 준다(문구는 구현 재량 — 침묵만 금지).
    expect(btn.getAttribute("title") ?? "").toMatch(/평가 기록 없음|주문번호/);
  });

  it("F21 매수 주문 2건 페어는 (2) 배지를 보여 준다", async () => {
    installPnlMocks();
    renderPnlGrid();

    const btn = await screen.findByTestId(
      `llm-eval-btn-pair-${PAIR_MULTI_BUY.pair_key}`,
      {},
      { timeout: 5000 },
    );
    expect(btn).toBeEnabled();
    expect(btn.textContent).toContain("(2)");
  });

  it("F22 페이지의 모든 buy_order_nos 를 한 요청으로 모아 조회한다", async () => {
    const { batchCalls } = installPnlMocks();
    renderPnlGrid();

    await screen.findByTestId(
      `llm-eval-btn-pair-${PAIR_WITH_EVAL.pair_key}`,
      {},
      { timeout: 5000 },
    );
    await new Promise((r) => setTimeout(r, 300));

    expect(batchCalls).toHaveLength(1);
    // 집합 동일성으로 잰다 — `toContain` 만으로는 매도 주문번호 혼입·중복 미제거가
    // 살아남는다(명세 §10.3: 페이지의 `buy_order_nos` 를 flat + dedupe 해 1회).
    expect(batchCalls[0].split(",").sort()).toEqual(
      [PAIR_A_BUY, PAIR_B_BUY_1, PAIR_B_BUY_2].sort(),
    );
    // 매도 주문번호는 평가 대상이 아니다.
    expect(batchCalls[0]).not.toContain("0000987654");
    expect(batchCalls[0]).not.toContain("0000200099");
  }, 20000);

  it("F20b 다른 날짜의 평가 기록만 있는 페어의 버튼은 비활성이다", async () => {
    // 검증 라운드 지적(MEDIUM, 손익 그리드 쪽) — 배치는 날짜 없이 묻고 상세는
    // `pair.buy_date` 와 함께 묻는다. 같은 주문번호가 다른 날 재사용된 경우 요약은 키를
    // 돌려주지만 상세는 404 라, 날짜 대조 없이는 "버튼 활성 → 모달 회색 안내" 가 된다.
    installPnlMocks(
      [PAIR_WITH_EVAL, PAIR_MULTI_BUY, PAIR_NO_ORDER_NO],
      {
        [sumKey("2026-09-08", PAIR_A_BUY)]: makeLlmEvaluationSummary({
          order_no: PAIR_A_BUY,
          trade_date: "2026-09-08", // 페어의 buy_date(2026-09-11)와 다르다
          score: 62,
        }),
      },
      [PAIR_A_BUY], // 09-11 기록은 없다 — 그래야 "다른 날짜에만 있다" 가 성립한다
    );
    renderPnlGrid();

    // 날짜가 맞는 다중 매수 페어는 여전히 활성 — 대조가 전면 차단으로 퇴화하지 않았다.
    const ok = await screen.findByTestId(
      `llm-eval-btn-pair-${PAIR_MULTI_BUY.pair_key}`,
      {},
      { timeout: 5000 },
    );
    expect(ok).toBeEnabled();

    const btn = screen.getByTestId(`llm-eval-btn-pair-${PAIR_WITH_EVAL.pair_key}`);
    expect(btn).toBeDisabled();
    expect(btn.getAttribute("title") ?? "").toContain("다른 날짜");
  }, 20000);

  it("F25b 버튼 클릭 시 상세 요청의 trade_date 가 페어의 buy_date 와 같다", async () => {
    // 검증 라운드 지적(LOW, 뮤테이션 ESCAPED) — `onOpen(buyOrderNos, buyDate)` 의 두 번째
    // 인자를 `undefined` 로 바꿔도 전건 통과했다. 그 인자가 사라지면 라우트가 "가장 최근
    // 1건" 을 골라 **다른 거래의 평가**를 모달에 띄운다(KIS ODNO 는 하루 단위로만 유일).
    // 코드 주석이 근거로 든 위험을 지키는 테스트가 없었으므로 여기서 잠근다.
    const { detailCalls } = installPnlMocks();
    renderPnlGrid();

    const btn = await screen.findByTestId(
      `llm-eval-btn-pair-${PAIR_WITH_EVAL.pair_key}`,
      {},
      { timeout: 5000 },
    );
    await userEvent.click(btn);

    await screen.findByTestId("llm-eval-modal", {}, { timeout: 5000 });
    await waitFor(() => expect(detailCalls.length).toBeGreaterThanOrEqual(1), {
      timeout: 5000,
    });
    expect(detailCalls[0].orderNo).toBe(PAIR_A_BUY);
    expect(detailCalls[0].tradeDate).toBe(PAIR_WITH_EVAL.buy_date);
    expect(detailCalls[0].tradeDate).not.toBeNull();
  }, 20000);

  it("F23 기존 13개 열과 요약 바 testid 는 그대로다 (회귀)", async () => {
    installPnlMocks();
    renderPnlGrid();

    await screen.findByText("삼성전자", {}, { timeout: 5000 });

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent?.trim());
    expect(headers.slice(0, 13)).toEqual([
      "매수일",
      "매수체결시각",
      "매도일",
      "매도체결시각",
      "종목코드",
      "종목명",
      "매수체결가",
      "매수체결수량",
      "매도체결가",
      "매도체결수량",
      "매매손익",
      "손익율",
      "전략",
    ]);
    expect(headers).toHaveLength(14);
    expect(screen.getByTestId("pnl-summary")).toBeInTheDocument();
    expect(screen.getByTestId("pnl-summary-realized")).toBeInTheDocument();
  });

  it("F24 open 페어 행의 배경(bg-emerald-50/40)은 그대로다 (회귀)", async () => {
    installPnlMocks();
    renderPnlGrid();

    await screen.findByText("금호타이어", {}, { timeout: 5000 });
    expect(rowOf("금호타이어").className).toContain("bg-emerald-50/40");
    expect(rowOf("삼성전자").className).not.toContain("bg-emerald-50/40");
  });
});
