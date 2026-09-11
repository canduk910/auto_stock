/**
 * L3 — TradeHistoryGrid KST 시각 표시 일관성 (2026-05-12).
 *
 * 배경: 005930 보완 INSERT 결함 추적 결과, 백엔드는 `_to_kst` 헬퍼로 KST 변환을
 * 강제했지만 프론트엔드 `parseKST()` 는 실제론 `new Date(timestamp)` 후
 * `getFullYear()/getHours()` 를 브라우저 로컬 timezone 으로 추출 → 함수명과
 * 동작이 불일치. UTC ISO 가 트레이드 응답에 섞이면 환경별로 다른 시각 표시.
 *
 * 요구 행위:
 *  I. UTC ISO `2026-05-11T23:05:47Z` 입력 시 KST 환산으로 `26-05-12 / 08:05:47` 표시
 *     (브라우저 timezone 무관)
 *
 * 테스트 환경: vitest 의 jsdom 기본 timezone 은 호스트 OS 의존. 본 테스트는
 * `process.env.TZ='UTC'` 를 명시해 결정론적으로 동작 — KST 강제가 없으면
 * 브라우저는 UTC 시각 그대로 (`23:05:47`) 표시 → 단언 실패 → Red.
 */

import { describe, expect, it, beforeAll, afterAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import {
  makeLlmEvaluation,
  makeLlmEvaluationSummary,
  makeTrade,
  wrap,
} from "../../test/factories";
import { TestProviders } from "../../test/providers";
import TradeHistoryGrid from "../TradeHistoryGrid";

// 결정론적 검증을 위해 테스트 프로세스 TZ 를 UTC 로 고정.
// `new Date(...)` + `d.getHours()` 등 로컬타임 추출은 이 TZ 따라가므로
// KST 강제 변환 없이는 UTC 시각이 그대로 표시된다.
const ORIG_TZ = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "UTC";
});
afterAll(() => {
  process.env.TZ = ORIG_TZ;
});

describe("TradeHistoryGrid — KST 시각 표시 (L3)", () => {
  it("UTC ISO 타임스탬프를 KST 로 환산해 주문일/주문시각 컬럼에 표시한다", async () => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json(
          wrap({
            trades: [
              {
                id: 1,
                // 2026-05-11 23:05:47 UTC = 2026-05-12 08:05:47 KST
                timestamp: "2026-05-11T23:05:47Z",
                ticker: "005930",
                ticker_name: "삼성전자",
                trade_type: "BUY",
                price: 70000,
                quantity: 10,
                profit_loss: 0,
                status: "COMPLETED",
                strategy: "momentum",
                order_no: "0000001111",
              },
            ],
            total: 1,
            total_pages: 1,
            page: 1,
            size: 20,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <TradeHistoryGrid />
      </TestProviders>,
    );

    // 종목명이 렌더되면 그리드가 준비된 상태.
    await waitFor(() => expect(screen.getByText("삼성전자")).toBeInTheDocument());

    // KST 변환: 주문일 = 26-05-12, 주문시각 = 08:05:47
    expect(screen.getByText("26-05-12")).toBeInTheDocument();
    expect(screen.getByText("08:05:47")).toBeInTheDocument();
  });
});

// =======================================================================
// cycle276 Red — 체결 그리드 "AI 자문" 열 (F13~F18)
//
// 명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §10.3 / §11.2.
// 사용자 지시(2026-09-11) = "UI의 거래기록(체결, 매매손익)에서 각 행에 AI매매자문
// 버튼을 달고 버튼 선택 시 팝업형태로 확인가능하도록 함."
//
// 계약:
//  - 맨 끝 열 "AI 자문". 활성 = `trade_type === 'BUY' && order_no && summaries[order_no]`.
//  - SELL 행은 **비활성 버튼을 렌더**한다(열 폭 유지) — 활성 버튼은 매수 행에만.
//  - 배치 요약 조회는 **페이지당 1회**(행마다 개별 조회 금지 — 페이지당 20~30 요청 방지).
//  - 모달에 넘기는 날짜는 `timestamp` 의 **KST 사영**(브라우저 로컬타임 금지 — 이 파일 TZ=UTC).
//
// RED: 현재 그리드는 열도 버튼도 배치 조회도 없다 → 전 케이스 실패.
// =======================================================================

const BUY_WITH_EVAL = "0000123456";
const BUY_WITHOUT_EVAL = "0000222222";
const SELL_ORDER = "0000333333";

/** 2026-09-11 23:05:47 UTC = 2026-09-12 08:05:47 KST — KST 사영 검증용 타임스탬프. */
const UTC_TS_CROSSING_KST_DATE = "2026-09-11T23:05:47Z";
/**
 * 위 타임스탬프의 **KST 영업일**. 배치 요약의 `trade_date` 는 이 값이어야 버튼이 켜진다 —
 * 요약(날짜 없이 조회)과 상세(날짜와 함께 조회)의 날짜가 어긋나면 "버튼은 활성인데 모달은
 * 404" 가 되므로, 셀이 요약의 `trade_date` 를 행의 KST 날짜와 대조한다.
 * 이 픽스처가 브라우저 로컬(UTC) 날짜 `2026-09-11` 을 쓰면 어떤 구현으로도 안 켜진다.
 */
const KST_DATE_OF_ROWS = "2026-09-12";

function historyPage() {
  return wrap({
    trades: [
      makeTrade({
        id: 1,
        timestamp: UTC_TS_CROSSING_KST_DATE,
        trade_type: "BUY",
        order_no: BUY_WITH_EVAL,
        ticker: "005930",
        ticker_name: "삼성전자",
        strategy: "volatility_breakout",
      }),
      makeTrade({
        id: 2,
        timestamp: UTC_TS_CROSSING_KST_DATE,
        trade_type: "BUY",
        order_no: BUY_WITHOUT_EVAL,
        ticker: "000660",
        ticker_name: "SK하이닉스",
        strategy: "long_tail_volatility",
      }),
      makeTrade({
        id: 3,
        timestamp: UTC_TS_CROSSING_KST_DATE,
        trade_type: "SELL",
        order_no: SELL_ORDER,
        ticker: "005930",
        ticker_name: "삼성전자",
        strategy: "volatility_breakout",
      }),
    ],
    page: 1,
    size: 20,
    total: 3,
    total_pages: 1,
  });
}

/** 배치 응답 맵의 복합 키 — 라우트 `summary_key()` / 프론트 `llmEvalKey()` 와 같은 규약. */
const sumKey = (tradeDate: string, orderNo: string) => `${tradeDate}|${orderNo}`;

/**
 * 배치 요약 목 — 기록이 있는 조합만 `날짜|주문번호` 키로 돌려준다(없으면 **키 자체가 없다**).
 *
 * 키가 주문번호 단독이 아니라 복합인 이유 = KIS ODNO 는 하루 단위로만 유일해서 같은 번호가
 * 여러 날짜에 존재하고, 단독 키로 접으면 오래된 날짜의 평가가 응답에서 **사라진다**.
 *
 * `extraSummaries` 로 "요약 맵에는 있지만 활성이면 안 되는" 조합(다른 날짜 기록 · 매도 주문
 * 번호)을 주입한다. 실제 라우트는 요청한 주문번호만 돌려주지만, 목이 더 넣어도 셀 판정이
 * 흔들리지 않아야 방어가 2중이 된다.
 */
function installMocks(extraSummaries: Record<string, unknown> = {}) {
  const batchCalls: string[] = [];
  server.use(
    http.get("/api/history", () => HttpResponse.json(historyPage())),
    http.get("/api/llm-evaluations", ({ request }) => {
      const url = new URL(request.url);
      batchCalls.push(url.searchParams.get("order_nos") ?? "");
      return HttpResponse.json(
        wrap({
          [sumKey(KST_DATE_OF_ROWS, BUY_WITH_EVAL)]: makeLlmEvaluationSummary({
            order_no: BUY_WITH_EVAL,
            trade_date: KST_DATE_OF_ROWS,
            score: 62,
            min_score: 70,
            would_block: true,
          }),
          ...extraSummaries,
        }),
      );
    }),
  );
  return { batchCalls };
}

function renderGrid() {
  render(
    <TestProviders>
      <TradeHistoryGrid />
    </TestProviders>,
  );
}

describe("cycle276 — TradeHistoryGrid AI 자문 열 (Red)", () => {
  it("F13 'AI 자문' 열 헤더를 맨 끝에 렌더한다", async () => {
    installMocks();
    renderGrid();

    // ⚠️ Green(cycle276) 정정 — 원안은 `getByText("삼성전자")` 였는데 이 픽스처는 삼성전자
    // 행이 **둘**이다(id=1 BUY, id=3 SELL). `getByText` 는 다중 매치에서 던지므로 어떤
    // 구현으로도 통과할 수 없었다. 의도(행이 그려질 때까지 기다린다)는 그대로 두고
    // 다중 매치를 허용하는 형태로만 고친다.
    await waitFor(() => expect(screen.getAllByText("삼성전자").length).toBeGreaterThan(0));

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent?.trim());
    expect(headers).toContain("AI 자문");
    expect(headers[headers.length - 1]).toBe("AI 자문");
  });

  it("F14 평가 기록이 있는 매수 행의 버튼은 활성이다", async () => {
    installMocks();
    renderGrid();

    const btn = await screen.findByTestId(
      `llm-eval-btn-${BUY_WITH_EVAL}`,
      {},
      { timeout: 5000 },
    );
    expect(btn).toBeEnabled();
    expect(btn.textContent).toContain("AI 자문");
  });

  it("F15 평가 기록이 없는 매수 행의 버튼은 비활성이고 '평가 기록 없음' 을 알린다", async () => {
    installMocks();
    renderGrid();

    const btn = await screen.findByTestId(
      `llm-eval-btn-${BUY_WITHOUT_EVAL}`,
      {},
      { timeout: 5000 },
    );
    expect(btn).toBeDisabled();
    expect(btn.getAttribute("title")).toContain("평가 기록 없음");
  });

  it("F14b 다른 날짜의 평가 기록만 있는 매수 행의 버튼은 비활성이다", async () => {
    // 검증 라운드 지적(MEDIUM) — 배치 요약은 **날짜 없이** 묻고 모달 상세는 **날짜와 함께**
    // 묻는다. KIS 주문번호(ODNO)는 하루 단위로만 유일해서(마이그레이션 043 주석), 09-08 에만
    // 평가가 있는 번호를 09-12 체결 행이 조회하면 요약은 키를 돌려주고 상세는 404 를 준다 —
    // "버튼은 활성인데 모달은 회색 '평가 기록 없음'" 이라는 거짓말이 그 조합이다.
    // 실 PG + 실 라우트로 재현된 정상 경로이므로 셀에서 날짜를 대조해 막는다.
    installMocks({
      [sumKey("2026-09-08", BUY_WITHOUT_EVAL)]: makeLlmEvaluationSummary({
        order_no: BUY_WITHOUT_EVAL,
        trade_date: "2026-09-08", // 행의 KST 날짜(2026-09-12)와 다르다
        ticker: "000660",
      }),
    });
    renderGrid();

    // 같은 페이지의 날짜 일치 행은 정상 활성 — 대조가 전면 차단으로 퇴화하지 않았다는 증거.
    const ok = await screen.findByTestId(
      `llm-eval-btn-${BUY_WITH_EVAL}`,
      {},
      { timeout: 5000 },
    );
    expect(ok).toBeEnabled();

    const btn = screen.getByTestId(`llm-eval-btn-${BUY_WITHOUT_EVAL}`);
    expect(btn).toBeDisabled();
    // 사유가 "기록 없음" 이 아니라 "다른 날짜" 임을 알린다(반대 방향 거짓말 차단).
    expect(btn.getAttribute("title") ?? "").toContain("다른 날짜");
  }, 20000);

  it("F16b 매도 주문번호가 요약 맵에 있어도 매도 행 버튼은 비활성이다", async () => {
    // 검증 라운드 지적(LOW) — 셀의 `isBuy &&` 가드는 현재 도달 불가(배치가 BUY 만 묻는다)라
    // 지워도 전건 통과했다. 그런데 `trade_history` 의 부분 UNIQUE 는 `(ticker, order_no,
    // trade_type)` 이라 **같은 주문번호가 BUY·SELL 두 행으로 존재하는 것을 스키마가 허용**한다.
    // 그 조합을 목으로 만들어 방어를 2중으로 잠근다.
    installMocks({
      [sumKey(KST_DATE_OF_ROWS, SELL_ORDER)]: makeLlmEvaluationSummary({
        order_no: SELL_ORDER,
        trade_date: KST_DATE_OF_ROWS, // 날짜까지 일치시켜도 매도는 대상이 아니다
      }),
    });
    renderGrid();

    // ⚠️ 매도 행 버튼은 요약 응답 **전에도** 비활성으로 그려진다. 그 순간에 단언하면
    // 어떤 구현이든 통과하므로(실측: `isBuy` 가드를 지운 뮤테이션이 살아남았다),
    // 먼저 "요약이 도착했다" 는 증거(날짜 일치 매수 행이 활성)를 기다린 뒤에 잰다.
    const ok = await screen.findByTestId(
      `llm-eval-btn-${BUY_WITH_EVAL}`,
      {},
      { timeout: 5000 },
    );
    await waitFor(() => expect(ok).toBeEnabled(), { timeout: 5000 });

    const btn = screen.getByTestId(`llm-eval-btn-${SELL_ORDER}`);
    expect(btn).toBeDisabled();
    expect(btn.getAttribute("title")).toContain("매수 주문만 평가 대상");
  }, 20000);

  it("F16 매도 행에는 활성 버튼이 없다 — '매수 주문만 평가 대상' 비활성 버튼", async () => {
    installMocks();
    renderGrid();

    const btn = await screen.findByTestId(`llm-eval-btn-${SELL_ORDER}`, {}, { timeout: 5000 });
    expect(btn).toBeDisabled();
    expect(btn.getAttribute("title")).toContain("매수 주문만 평가 대상");

    // 매도 행 어디에도 누를 수 있는 AI 자문 버튼이 없어야 한다.
    const row = btn.closest("tr");
    expect(row).not.toBeNull();
    const enabled = within(row as HTMLElement)
      .getAllByRole("button")
      .filter((b) => !(b as HTMLButtonElement).disabled);
    expect(enabled).toHaveLength(0);
  });

  it("F17 배치 요약 조회는 페이지당 1회다 (행별 개별 조회 금지)", async () => {
    const { batchCalls } = installMocks();
    renderGrid();

    await screen.findByTestId(`llm-eval-btn-${BUY_WITH_EVAL}`, {}, { timeout: 5000 });
    // 늦게 도착하는 추가 요청까지 잡는다.
    await new Promise((r) => setTimeout(r, 300));

    expect(batchCalls).toHaveLength(1);
    // 페이지의 **매수** 주문번호가 한 요청에 모여 나간다 — 집합 동일성으로 잰다.
    // `toContain` 만으로는 "무엇이 더 들어갔는지" 를 못 봐서 매도 주문번호 혼입·중복
    // 미제거 뮤테이션이 살아남는다(명세 §10.3 의 "BUY 만, 페이지당 1회" 계약).
    expect(batchCalls[0].split(",").sort()).toEqual(
      [BUY_WITH_EVAL, BUY_WITHOUT_EVAL].sort(),
    );
    expect(batchCalls[0]).not.toContain(SELL_ORDER);
  }, 20000);

  it("F18 버튼을 누르면 그 주문번호의 모달이 열린다 (날짜는 KST 사영)", async () => {
    const { batchCalls } = installMocks();
    const detailCalls: Array<{ orderNo: string; tradeDate: string | null }> = [];
    server.use(
      http.get("/api/llm-evaluations/:orderNo", ({ params, request }) => {
        detailCalls.push({
          orderNo: String(params.orderNo),
          tradeDate: new URL(request.url).searchParams.get("trade_date"),
        });
        return HttpResponse.json(
          wrap(
            makeLlmEvaluation({
              order_no: String(params.orderNo),
              score: 62,
              min_score: 70,
              would_block: true,
            }),
          ),
        );
      }),
    );

    renderGrid();

    const btn = await screen.findByTestId(
      `llm-eval-btn-${BUY_WITH_EVAL}`,
      {},
      { timeout: 5000 },
    );
    await userEvent.click(btn);

    const modal = await screen.findByTestId("llm-eval-modal", {}, { timeout: 5000 });
    expect(modal.textContent).toMatch(/62/);
    expect(modal.textContent).not.toMatch(/NaN/);

    await waitFor(() => expect(detailCalls).toHaveLength(1), { timeout: 5000 });
    expect(detailCalls[0].orderNo).toBe(BUY_WITH_EVAL);
    // 2026-09-11T23:05:47Z = KST 2026-09-12 — 브라우저 로컬(UTC)의 09-11 이면 결함.
    expect(detailCalls[0].tradeDate).toBe("2026-09-12");
    // 모달을 열어도 배치 조회가 늘지 않는다.
    expect(batchCalls).toHaveLength(1);
  }, 20000);
});
