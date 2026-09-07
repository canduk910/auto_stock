/**
 * cycle266 — StockMaster "일봉 (30일)" 탭 결함 3건 방어 가드 (§3-B / §C-2).
 *
 * 명세 정본 = `_workspace/specs/cycle266_daily_tab_fix.md`.
 *
 * ## 왜 흰 화면이었나 (확정 진단, 재조사 금지)
 *
 * `stock_master_daily.change_rate` 는 `NUMERIC(8,4)` → asyncpg `Decimal` →
 * pydantic v2 JSON 모드에서 **문자열** `"0.0000"` 으로 나간다. `DailyTab` 은
 * `row.change_rate.toFixed(2)` 를 호출하므로 `TypeError` 가 나고, StockMaster 에는
 * ErrorBoundary 가 없어 React 루트까지 전파돼 **트리 전체가 언마운트**된다.
 * 도입 = dc66026(2026-06-13, 사이클 124) — 이 탭은 **처음부터 동작한 적이 없다**.
 *
 * 목 셋이 전부 `change_rate` 를 진짜 number 로 만들어 두어 3개월간 초록이었다
 * (`frontend/src/test/handlers.ts` · `e2e/fixtures/api-mocks.ts` · `StockMaster.test.tsx`).
 *
 * ## 이 파일이 강제하는 계약 (frontend-dev 와의 인터페이스 합의)
 *
 * - **B-1** 숫자 필드(`open_price`/`high_price`/`low_price`/`close_price`/`volume`/
 *   `change_rate`)는 렌더 **전에** 안전 변환한다. 문자열 숫자 → number,
 *   그 외/`NaN`/`null`/`undefined` → `'—'` 대체 표기. 등락률 **색상 분기도 변환 후 값 기준**.
 *   `toFixed`/`toLocaleString` 을 미검증 값에 직접 호출하지 않는다.
 * - **B-3** `useQuery` 에러가 404 면 **안내**(회색, `data-testid="stock-master-daily-notice"`),
 *   그 외(500·네트워크)는 **오류**(빨강, `data-testid="stock-master-daily-error"`).
 *   판별은 `axios.isAxiosError(error) && error.response?.status === 404`
 *   (`DetailModal` 의 `is404` 선례 답습).
 * - ⚠️ `retry: 1` 은 **유지 의무** (사이클 65 H3 + AST 가드
 *   `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts`).
 * - **B-4** ErrorBoundary 는 이번 사이클에 넣지 않는다(범위 확대 — 후속).
 *
 * ## 뮤테이션 내성
 *
 * 방어 변환(B-1)을 지우면 문자열 케이스가 크래시해 이 파일이 붉어져야 한다.
 * 그래서 단언은 `toBeInTheDocument` 수준에 머물지 않고 **셀 단위의 값과 색상 클래스**를
 * 잰다(`'—'` 로 전부 퉁치는 구현도 함께 잡힌다).
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { http, HttpResponse } from "msw";
import type { HttpResponseResolver } from "msw";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import StockMaster from "../StockMaster";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

// react-query 의 컴포넌트 레벨 `retry: 1` 이 기본값을 이기므로 에러 케이스는
// 1회 재시도(기본 지연 ~1s) 후에야 확정된다 — 넉넉한 타임아웃을 쓴다.
const ERROR_TIMEOUT = 6000;
// vitest 기본 testTimeout(5s)보다 길게 — 실패 메시지가 '타임아웃'이 아니라
// '해당 testid 없음'으로 읽혀야 진단이 된다.
const ERROR_TEST_TIMEOUT = 20000;

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE_STATS = {
  count_all: 3583,
  bfdy_clpr_present: 3500,
  nxt_tradable_count: 1810,
  top_10_recent: [
    { ticker: "005930", name: "삼성전자", refreshed_at: "2026-09-05T09:00:00+09:00" },
  ],
  with_hts_avls: 3400,
  with_acml_tr_pbmn: 3300,
  total_daily_rows: 540000,
  last_daily_load_at: "2026-09-05T16:05:00+09:00",
};

const SAMPLE_LIST = [
  {
    ticker: "005930",
    name: "삼성전자",
    excg_dvsn_cd: "01",
    nxt_tradable: true,
    krx_halted: false,
    admin_item: false,
    refreshed_at: "2026-09-05T09:00:00+09:00",
    raw: { bfdy_clpr: 75000 },
  },
];

const SAMPLE_DETAIL = {
  ...SAMPLE_LIST[0],
  raw: { bfdy_clpr: 75000, hts_avls: 500000 },
};

/**
 * 운영 응답의 **실제** 모양 — `change_rate` 는 문자열, `bas_dd` 는 `YYYY-MM-DD`
 * (`bas_dd` 는 DATE 컬럼이다 — 타입 주석의 `YYYYMMDD` 는 거짓, B-2 에서 시정).
 */
const PRODUCTION_SHAPE_ROWS = [
  {
    ticker: "005930",
    bas_dd: "2026-09-05",
    open_price: 74000,
    high_price: 75500,
    low_price: 73500,
    close_price: 75000,
    volume: 1234567,
    trade_value: 75000000000,
    change_rate: "1.2300",
    prtt_rate: "0.0000",
    raw: {},
  },
  {
    ticker: "005930",
    bas_dd: "2026-09-04",
    open_price: 73000,
    high_price: 74000,
    low_price: 72000,
    close_price: 73100,
    volume: 987654,
    trade_value: 71000000000,
    change_rate: "-2.5000",
    prtt_rate: "0.0000",
    raw: {},
  },
  {
    ticker: "005930",
    bas_dd: "2026-09-03",
    open_price: 73200,
    high_price: 73400,
    low_price: 72800,
    close_price: 73000,
    volume: 456789,
    trade_value: 33000000000,
    change_rate: "0.0000",
    prtt_rate: "0.0000",
    raw: {},
  },
];

/** 백엔드 A-1 시정 **후** 의 모양 — 숫자. 이쪽도 계속 통과해야 한다(§C-2). */
const FIXED_BACKEND_ROWS = PRODUCTION_SHAPE_ROWS.map((r) => ({
  ...r,
  change_rate: Number(r.change_rate),
  prtt_rate: Number(r.prtt_rate),
}));

function setupHandlers(dailyResolver: HttpResponseResolver) {
  server.use(
    http.get("/api/stock-master/stats", () => HttpResponse.json(wrap(SAMPLE_STATS))),
    http.get("/api/stock-master/list", () => HttpResponse.json(wrap(SAMPLE_LIST))),
    http.get("/api/stock-master/scan-pool/summary", () =>
      HttpResponse.json(wrap({ eager_refresh_today: 0 })),
    ),
    http.get("/api/stock-master/:ticker/daily", dailyResolver),
    http.get("/api/stock-master/:ticker/history", () => HttpResponse.json(wrap([]))),
    http.get("/api/stock-master/005930", () => HttpResponse.json(wrap(SAMPLE_DETAIL))),
  );
}

/** 페이지 렌더 → ticker 클릭 → 일봉 탭 클릭. */
async function openDailyTab(dailyResolver: HttpResponseResolver) {
  setupHandlers(dailyResolver);
  render(withProviders(<StockMaster />));

  await waitFor(() => expect(screen.getByText("005930")).toBeDefined());
  fireEvent.click(screen.getByText("005930"));
  await waitFor(() =>
    expect(screen.getByTestId("stock-master-detail-tabs")).toBeDefined(),
  );
  fireEvent.click(screen.getByTestId("stock-master-tab-daily"));
}

const rowsResolver = (rows: unknown[]) => () => HttpResponse.json(wrap(rows));

/** bas_dd 셀 텍스트로 `<tr>` 을 잡아 셀 배열을 돌려준다. */
function cellsOf(basDd: string): HTMLElement[] {
  const tr = screen.getByText(basDd).closest("tr");
  expect(tr, `bas_dd=${basDd} 행을 찾지 못했다`).not.toBeNull();
  return within(tr as HTMLElement).getAllByRole("cell");
}

const IDX = {
  basDd: 0,
  open: 1,
  high: 2,
  low: 3,
  close: 4,
  volume: 5,
  changeRate: 6,
} as const;

// ────────────────────────────────────────────────────────────────────────────
// B-1 — 방어 변환: 문자열 등락률에도 버틴다
// ────────────────────────────────────────────────────────────────────────────

describe("cycle266 B-1 (HIGH) — DailyTab 은 문자열 숫자 응답에도 크래시하지 않는다", () => {
  it("B-1-1: change_rate 가 문자열이어도 테이블이 렌더된다 (흰 화면 재발 차단)", async () => {
    await openDailyTab(rowsResolver(PRODUCTION_SHAPE_ROWS));

    await waitFor(() =>
      expect(screen.getByTestId("stock-master-daily-table")).toBeDefined(),
    );
    // 트리가 언마운트되지 않았다는 것 = 모달과 탭이 살아 있다
    expect(screen.getByTestId("stock-master-detail-modal")).toBeDefined();
  });

  it("B-1-2: 문자열 '1.2300' → '+1.23%' 상승색 / '-2.5000' → '-2.50%' 하락색 / '0.0000' → '0.00%' 중립색", async () => {
    await openDailyTab(rowsResolver(PRODUCTION_SHAPE_ROWS));
    await waitFor(() =>
      expect(screen.getByTestId("stock-master-daily-table")).toBeDefined(),
    );

    const up = cellsOf("2026-09-05")[IDX.changeRate];
    expect(up.textContent?.trim()).toBe("+1.23%");
    expect(
      up.className,
      "상승 등락률 색상 분기가 **변환 후 값** 기준이 아니다 (문자열 비교는 항상 false)",
    ).toContain("text-red-600");

    const down = cellsOf("2026-09-04")[IDX.changeRate];
    expect(down.textContent?.trim()).toBe("-2.50%");
    expect(down.className).toContain("text-blue-600");

    const flat = cellsOf("2026-09-03")[IDX.changeRate];
    expect(flat.textContent?.trim()).toBe("0.00%");
    expect(flat.className).toContain("text-gray-500");
  });

  it("B-1-3: OHLCV 가 문자열이어도 ko-KR 천단위 서식으로 렌더된다", async () => {
    const stringOhlcv = [
      {
        ...PRODUCTION_SHAPE_ROWS[0],
        open_price: "74000",
        high_price: "75500",
        low_price: "73500",
        close_price: "75000",
        volume: "1234567",
      },
    ];
    await openDailyTab(rowsResolver(stringOhlcv));
    await waitFor(() =>
      expect(screen.getByTestId("stock-master-daily-table")).toBeDefined(),
    );

    const cells = cellsOf("2026-09-05");
    expect(cells[IDX.open].textContent?.trim()).toBe("74,000");
    expect(cells[IDX.high].textContent?.trim()).toBe("75,500");
    expect(cells[IDX.low].textContent?.trim()).toBe("73,500");
    expect(cells[IDX.close].textContent?.trim()).toBe("75,000");
    expect(cells[IDX.volume].textContent?.trim()).toBe("1,234,567");
  });

  it("B-1-4: null / undefined / 비숫자 문자열 / NaN 은 '—' 로 대체되고 크래시하지 않는다", async () => {
    const brokenRow = [
      {
        ticker: "005930",
        bas_dd: "2026-09-02",
        open_price: null,
        high_price: undefined,
        low_price: "N/A",
        close_price: "",
        volume: Number.NaN,
        trade_value: 0,
        change_rate: null,
        raw: {},
      },
    ];
    await openDailyTab(rowsResolver(brokenRow));
    await waitFor(() =>
      expect(screen.getByTestId("stock-master-daily-table")).toBeDefined(),
    );

    const cells = cellsOf("2026-09-02");
    for (const idx of [IDX.open, IDX.high, IDX.low, IDX.close, IDX.volume, IDX.changeRate]) {
      expect(
        cells[idx].textContent?.trim(),
        `변환 불가 값이 '—' 로 대체되지 않았다 (cell index ${idx}): ${cells[idx].textContent}`,
      ).toBe("—");
    }
    // '—' 는 값이 아니므로 손익 색상을 입히지 않는다
    expect(cells[IDX.changeRate].className).not.toContain("text-red-600");
    expect(cells[IDX.changeRate].className).not.toContain("text-blue-600");
  });

  it("B-1-5(회귀): 백엔드 시정 후의 숫자 응답도 그대로 통과한다 (양쪽 다 초록 의무)", async () => {
    await openDailyTab(rowsResolver(FIXED_BACKEND_ROWS));
    await waitFor(() =>
      expect(screen.getByTestId("stock-master-daily-table")).toBeDefined(),
    );

    expect(cellsOf("2026-09-05")[IDX.changeRate].textContent?.trim()).toBe("+1.23%");
    expect(cellsOf("2026-09-04")[IDX.changeRate].textContent?.trim()).toBe("-2.50%");
    expect(cellsOf("2026-09-05")[IDX.close].textContent?.trim()).toBe("75,000");
    expect(cellsOf("2026-09-05")[IDX.volume].textContent?.trim()).toBe("1,234,567");
  });
});

// ────────────────────────────────────────────────────────────────────────────
// B-3 — 404 는 안내, 그 밖은 오류
// ────────────────────────────────────────────────────────────────────────────

describe("cycle266 B-3 (HIGH) — 404 는 안내 문구, 500·네트워크는 오류 문구", () => {
  it("B-3-1: 404 → 회색 안내(미적재)이고 '조회 실패' 가 아니다", async () => {
    await openDailyTab(() =>
      HttpResponse.json(
        { detail: "ticker=005930 일봉 미적재 — 일봉은 전 종목이 아니라 전략 유니버스 대상만 적재됩니다 (days=30)" },
        { status: 404 },
      ),
    );

    const notice = await screen.findByTestId(
      "stock-master-daily-notice",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(
      notice.textContent,
      "404 는 장애가 아니라 정상 미적재다 — 운영 실측 3,583 중 1,773(49.5%)이 이 경우다",
    ).toContain("미적재");
    expect(notice.className).toContain("text-gray-");
    expect(screen.queryByTestId("stock-master-daily-error")).toBeNull();
    expect(screen.queryByText(/조회 실패/)).toBeNull();
  }, ERROR_TEST_TIMEOUT);

  it("B-3-2: 500 → 빨간 오류 문구 (안내로 위장하지 않는다)", async () => {
    await openDailyTab(() =>
      HttpResponse.json({ detail: "internal" }, { status: 500 }),
    );

    const err = await screen.findByTestId(
      "stock-master-daily-error",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(err.className).toContain("text-red-");
    expect(screen.queryByTestId("stock-master-daily-notice")).toBeNull();
  }, ERROR_TEST_TIMEOUT);

  it("B-3-3: 네트워크 오류(response 없음) → 빨간 오류 문구", async () => {
    await openDailyTab(() => HttpResponse.error());

    const err = await screen.findByTestId(
      "stock-master-daily-error",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(err.className).toContain("text-red-");
    expect(screen.queryByTestId("stock-master-daily-notice")).toBeNull();
  }, ERROR_TEST_TIMEOUT);

  it("B-3-4: 200 + 빈 배열도 안내 문구로 흡수된다 (오류 아님)", async () => {
    await openDailyTab(rowsResolver([]));

    const notice = await screen.findByTestId(
      "stock-master-daily-notice",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(notice).toBeDefined();
    expect(screen.queryByTestId("stock-master-daily-error")).toBeNull();
  }, ERROR_TEST_TIMEOUT);
});

// ────────────────────────────────────────────────────────────────────────────
// D-1 (마무리 라운드, tester 적대 검토) — 안내가 원인을 **단정하지 않는다**
//
// B-3 의 안내 문구는 종전 "일봉 데이터 없음" 보다 친절하지만 원인을 단정한다.
// 그런데 `src/db/stock_master_daily.py::get_recent_daily` 는 **자신이** DB 예외를
// 삼키고 `[]` 를 돌려주므로(그 모듈은 6 전략 prepare + 터틀 ATR 공유 = 이 사이클
// 무접촉) 진짜 장애도 404 → 이 안내로 도착한다. 운영자가 그것을 "정상 미적재"로
// 읽고 넘기면 장애를 놓친다 ⇒ 안내에 단서 + 검색 가능한 로그 토큰을 함께 싣는다.
//
// ⚠️ 단서는 "조회 실패" 라는 **정확한 표현을 쓰지 않는다** — B-3-1 이
// `queryByText(/조회 실패/)` 부재로 오류 분기와 안내 분기를 가르기 때문이다.
// 두 분기의 구분은 그 단언이 계속 지키고, 이 블록은 단서의 **존재**를 지킨다.
// ────────────────────────────────────────────────────────────────────────────

describe("cycle266 D-1 — 404 안내가 조회 실패 가능성을 함께 알린다", () => {
  const NOT_LOADED_404 = () =>
    HttpResponse.json(
      {
        detail:
          "ticker=005930 일봉 미적재 — 전략 유니버스 대상만 적재됩니다 (days=30). " +
          "단, 서버 조회 실패도 같은 404 로 보일 수 있으니(cycle266 D-1) " +
          "로그에서 stock_master_daily 를 확인하세요",
      },
      { status: 404 },
    );

  it("D-1-1: 404 안내에 '가져오지 못한 경우' 단서가 있다 (원인 단정 금지)", async () => {
    await openDailyTab(NOT_LOADED_404);

    const notice = await screen.findByTestId(
      "stock-master-daily-notice",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    const text = notice.textContent ?? "";

    expect(text, "A-3/B-3 계약 유지 — '미적재' 토큰").toContain("미적재");
    expect(
      /가져오지 못|조회에 실패|실패한 경우/.test(text),
      `안내가 원인을 단정한다: ${JSON.stringify(text)} — ` +
        "`get_recent_daily` 가 DB 예외를 삼키므로 진짜 장애도 이 안내로 온다(D-1)",
    ).toBe(true);
  }, ERROR_TEST_TIMEOUT);

  it("D-1-2: 404 안내가 검색 가능한 로그 토큰 `stock_master_daily` 를 담는다", async () => {
    await openDailyTab(NOT_LOADED_404);

    const notice = await screen.findByTestId(
      "stock-master-daily-notice",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(
      notice.textContent,
      "'로그를 보세요'만으로는 무엇을 찾을지 알 수 없다 — db 마커 " +
        "'[stock_master_daily] get_recent_daily 실패 graceful' 과 라우트 마커 " +
        "'[stock_master_daily_route_error]' 를 모두 잡는 접두를 싣는다(D-1)",
    ).toContain("stock_master_daily");
  }, ERROR_TEST_TIMEOUT);

  it("D-1-3: 단서를 붙여도 오류 분기와 안내 분기의 구분은 그대로다", async () => {
    // B-3-1 의 `조회 실패` 부재 단언과 충돌하지 않음을 이 파일 안에서 못박는다.
    await openDailyTab(NOT_LOADED_404);

    const notice = await screen.findByTestId(
      "stock-master-daily-notice",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(notice.className).toContain("text-gray-");
    expect(notice.textContent).not.toContain("조회 실패");
    expect(screen.queryByTestId("stock-master-daily-error")).toBeNull();
  }, ERROR_TEST_TIMEOUT);

  it("D-1-4: 200 + 빈 배열도 같은 단서를 받는다 (분기가 하나이므로)", async () => {
    await openDailyTab(rowsResolver([]));

    const notice = await screen.findByTestId(
      "stock-master-daily-notice",
      {},
      { timeout: ERROR_TIMEOUT },
    );
    expect(notice.textContent).toContain("stock_master_daily");
  }, ERROR_TEST_TIMEOUT);
});

// ────────────────────────────────────────────────────────────────────────────
// B-1/B-3 정적 가드 — 뮤테이션 내성 보강
// ────────────────────────────────────────────────────────────────────────────

const SRC = path.resolve(__dirname, "../StockMaster.tsx");
const TYPES = path.resolve(__dirname, "../../types/stock-master.ts");

describe("cycle266 정적 가드 — 미검증 값 직접 호출 금지 + retry 유지", () => {
  it("G-266-1: DailyTab 이 `row.<field>.toFixed(` / `row.<field>.toLocaleString(` 를 직접 호출하지 않는다", () => {
    const source = readFileSync(SRC, "utf-8");
    const direct = source.match(/\brow\.\w+\.(toFixed|toLocaleString)\(/g) ?? [];
    expect(
      direct,
      `미검증 응답 값에 직접 호출: ${direct.join(", ")} — ` +
        "문자열 응답에서 TypeError 로 트리 전체가 언마운트된다(B-1 위반)",
    ).toEqual([]);

    // tester 보강(cycle266 뮤테이션 M6) — 위 정규식은 캐스팅/괄호로 우회된다:
    // `(row.change_rate as number).toFixed(2)` 는 런타임에 똑같이 죽지만 `\brow\.\w+\.`
    // 패턴에 안 걸린다(뮤테이션 실측: 행위 가드 4건이 잡아 KILLED 였으나 이 정적
    // 가드만 초록이었다). 캐스팅으로 타입 오류까지 지운 형태가 가장 위험하므로
    // 괄호로 감싼 형태와 `as number` 캐스팅을 함께 막는다.
    const casted =
      source.match(/\(\s*row\.\w+\b[^()]*\)\s*[!?]?\.(toFixed|toLocaleString)\(/g) ?? [];
    expect(
      casted,
      `캐스팅으로 우회한 직접 호출: ${casted.join(", ")} — ` +
        "타입 오류만 지웠을 뿐 런타임 TypeError 는 그대로다(B-1 위반)",
    ).toEqual([]);

    const cast = source.match(/\brow\.\w+\s+as\s+(number|any)\b/g) ?? [];
    expect(
      cast,
      `응답 값을 number 로 단언: ${cast.join(", ")} — ` +
        "타입 계약(`number | string`)을 캐스팅으로 무력화하지 않는다. " +
        "변환은 toSafeNumber 를 거친다",
    ).toEqual([]);
  });

  it("G-266-2: DailyTab 의 useQuery 가 `retry: 1` 을 유지한다 (사이클 65 H3 영속)", () => {
    const source = readFileSync(SRC, "utf-8");
    const dailyBlock = source.slice(
      source.indexOf("'stock-master-daily'"),
      source.indexOf("'stock-master-daily'") + 400,
    );
    expect(dailyBlock).toContain("retry: 1");
  });

  it("G-266-3: 404 판별이 `error.response?.status === 404` 로 이뤄진다 (DetailModal is404 선례)", () => {
    const source = readFileSync(SRC, "utf-8");
    const occurrences = source.match(/response\?\.status === 404/g) ?? [];
    expect(
      occurrences.length,
      "DailyTab 에도 404 판별이 필요하다 — DetailModal 한 곳만으로는 " +
        "일봉 미적재가 '조회 실패' 로 표시된다",
    ).toBeGreaterThanOrEqual(2);
  });

  it("G-266-4(B-2): StockMasterDailyRow 타입이 문자열 등락률을 허용하고 bas_dd 주석이 사실과 맞는다", () => {
    const types = readFileSync(TYPES, "utf-8");
    const block = types.slice(
      types.indexOf("export interface StockMasterDailyRow"),
      types.indexOf("export interface StockMasterListItem"),
    );
    expect(block, "StockMasterDailyRow 블록을 찾지 못했다").toBeTruthy();

    expect(
      /change_rate\s*:\s*number\s*\|\s*string|change_rate\s*:\s*string\s*\|\s*number/.test(
        block,
      ),
      "`change_rate: number` 는 거짓말이다 — 백엔드가 숫자로 내보내되 프론트는 " +
        "문자열도 허용한다는 실제 계약을 타입에 반영하라 (B-2)",
    ).toBe(true);

    expect(
      block.includes("YYYYMMDD"),
      "`bas_dd` 는 DATE 컬럼이라 직렬화가 `YYYY-MM-DD` 다 — " +
        "`YYYYMMDD` 주석은 거짓이다 (migration 033, B-2)",
    ).toBe(false);
    expect(block).toContain("YYYY-MM-DD");
  });

  it("G-266-5(D-2): StockMasterDailyRow 가 `SELECT *` 응답의 14 필드를 전부 선언한다", () => {
    // 라우트는 `SELECT * FROM stock_master_daily` 라 migration 033 의 14 컬럼이
    // 전부 나간다. 타입이 8개만 선언하면 "응답에 없는 필드" 로 오해돼 다음
    // 사이클이 또 목을 실제와 다르게 만든다(이 사이클이 고친 결함의 씨앗).
    // 선언만 강제하고 렌더 로직은 건드리지 않는다(D-2 = LOW, 런타임 영향 0).
    const types = readFileSync(TYPES, "utf-8");
    const block = types.slice(
      types.indexOf("export interface StockMasterDailyRow"),
      types.indexOf("export interface StockMasterListItem"),
    );

    const COLUMNS = [
      "ticker",
      "bas_dd",
      "open_price",
      "high_price",
      "low_price",
      "close_price",
      "volume",
      "trade_value",
      "change_rate",
      "flng_cls_code",
      "prtt_rate",
      "raw",
      "created_at",
      "updated_at",
    ];
    const missing = COLUMNS.filter(
      (c) => !new RegExp(`^\\s*${c}\\??\\s*:`, "m").test(block),
    );
    expect(
      missing,
      `응답에 오는데 타입에 없는 필드: ${missing.join(", ")} — ` +
        "라우트는 `SELECT *` 다(migration 033, 14 컬럼). 주석이 아니라 필드로 명시하라",
    ).toEqual([]);
  });

  it("G-266-6(D-2): `prtt_rate` 도 문자열을 허용한다 (change_rate 와 같은 NUMERIC 계열)", () => {
    const types = readFileSync(TYPES, "utf-8");
    const block = types.slice(
      types.indexOf("export interface StockMasterDailyRow"),
      types.indexOf("export interface StockMasterListItem"),
    );
    expect(
      /prtt_rate\??\s*:\s*(number\s*\|\s*string|string\s*\|\s*number)/.test(block),
      "`prtt_rate` 는 `change_rate` 와 같은 NUMERIC(8,4) → Decimal 출신이다 — " +
        "`number` 단독 선언은 change_rate 가 3개월간 했던 그 거짓말이다(D-2)",
    ).toBe(true);
  });

  it("G-266-7(D-1): 404 안내 리터럴이 로그 토큰 단서를 유지한다", () => {
    // 행위 가드(D-1-2)와 이중으로 잠근다 — 문구는 렌더 트리를 거치지 않고도
    // 조용히 지워질 수 있는 종류의 코드다.
    const source = readFileSync(SRC, "utf-8");
    const start = source.indexOf('data-testid="stock-master-daily-notice"');
    expect(start, "안내 분기를 찾지 못했다").toBeGreaterThan(-1);
    const noticeBlock = source.slice(start, source.indexOf("</p>", start));
    expect(
      noticeBlock,
      "안내가 원인을 단정하지 않도록 붙인 로그 토큰 단서가 사라졌다(D-1)",
    ).toContain("stock_master_daily");
  });
});
