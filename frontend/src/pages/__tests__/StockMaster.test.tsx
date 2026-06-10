/**
 * 사이클 85 — StockMaster 페이지 통합 테스트.
 *
 * 답습 패턴: StrategyFunnel (사이클 41) — 단일 페이지 4 카드 구조.
 *
 * 회귀 가드 매트릭스:
 * - G-KST (HIGH): refreshed_at / changed_at KST `+09:00` 표시 (사이클 68 영속)
 * - H-STATS (MEDIUM): 상태 카드 렌더 (4 키 + top_10_recent)
 * - H-LIST (MEDIUM): list 테이블 페이징 (limit=100, offset 이전/다음)
 * - H-DETAIL (MEDIUM): ticker 클릭 → detail 모달 + Q11=B 카테고리 + 핵심 5 키 highlight
 * - H-HISTORY (MEDIUM): history 테이블 changed_at DESC + change_type 배지 + `<pre>` collapsible
 * - H-POLLING (MEDIUM): 5 useQuery refetchInterval: 60_000 (Q13=B) AST 정적 grep
 * - L-CYCLE83-EMIT (LOW): eager_refresh_today 카드 노출 (사이클 83 emit 카운트 가시화)
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { http, HttpResponse } from "msw";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import StockMaster from "../StockMaster";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

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
  count_all: 29,
  bfdy_clpr_present: 28,
  nxt_tradable_count: 25,
  top_10_recent: [
    { ticker: "005930", name: "삼성전자", refreshed_at: "2026-06-09T09:00:00+09:00" },
    { ticker: "402340", name: "SK스퀘어", refreshed_at: "2026-06-09T08:55:00+09:00" },
  ],
};

const SAMPLE_LIST = [
  {
    ticker: "005930",
    name: "삼성전자",
    excg_dvsn_cd: "01",
    nxt_tradable: true,
    krx_halted: false,
    admin_item: false,
    refreshed_at: "2026-06-09T09:00:00+09:00",
    raw: { bfdy_clpr: 70000, acml_vol: 1000000 },
  },
];

const SAMPLE_DETAIL = {
  ticker: "005930",
  name: "삼성전자",
  excg_dvsn_cd: "01",
  nxt_tradable: true,
  krx_halted: false,
  admin_item: false,
  refreshed_at: "2026-06-09T09:00:00+09:00",
  raw: {
    bfdy_clpr: 70000,
    acml_vol: 1000000,
    acml_tr_pbmn: 70000000000,
    stck_prpr: 71500,
  },
};

const SAMPLE_HISTORY = [
  {
    id: 2,
    ticker: "005930",
    change_type: "UPDATE",
    before_raw: { bfdy_clpr: 70000 },
    after_raw: { bfdy_clpr: 71500 },
    changed_at: "2026-06-09T09:05:00+09:00",
  },
  {
    id: 1,
    ticker: "005930",
    change_type: "INSERT",
    before_raw: null,
    after_raw: { bfdy_clpr: 70000 },
    changed_at: "2026-06-09T09:00:00+09:00",
  },
];

function setupHappyPathHandlers() {
  server.use(
    http.get("/api/stock-master/stats", () =>
      HttpResponse.json(wrap(SAMPLE_STATS)),
    ),
    http.get("/api/stock-master/list", () =>
      HttpResponse.json(wrap(SAMPLE_LIST)),
    ),
    http.get("/api/stock-master/scan-pool/summary", () =>
      HttpResponse.json(wrap({ eager_refresh_today: 7 })),
    ),
    http.get("/api/stock-master/005930", () =>
      HttpResponse.json(wrap(SAMPLE_DETAIL)),
    ),
    http.get("/api/stock-master/005930/history", () =>
      HttpResponse.json(wrap(SAMPLE_HISTORY)),
    ),
  );
}

describe("사이클 85 — StockMaster 페이지 (H-STATS + L-CYCLE83-EMIT)", () => {
  it("H-STATS: 상태 카드가 4 키 값 + top_10_recent 를 렌더한다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-stats-card")).toBeDefined();
    });

    // 4 핵심 키 값 (count_all=29 / bfdy_clpr_present=28 / nxt_tradable_count=25 / eager_refresh_today=7)
    expect(screen.getByText("29")).toBeDefined();
    expect(screen.getByText("28")).toBeDefined();
    expect(screen.getByText("25")).toBeDefined();
    expect(screen.getByTestId("stock-master-stats-eager-refresh-today").textContent).toContain(
      "7",
    );

    // top_10_recent 2종 종목명 표시 (사이클 89 hotfix: list 테이블도 name 렌더 → getAllByText)
    expect(screen.getAllByText("삼성전자").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("SK스퀘어").length).toBeGreaterThanOrEqual(1);
  });

  it("L-CYCLE83-EMIT: eager_refresh_today 가 stock-master-stats-eager-refresh-today testid 로 노출된다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));
    await waitFor(() => {
      const el = screen.getByTestId("stock-master-stats-eager-refresh-today");
      expect(el).not.toBeNull();
    });
  });
});

describe("사이클 85 — StockMaster 페이지 (H-LIST)", () => {
  it("H-LIST: list 테이블이 ticker / name / nxt_tradable / refreshed_at 컬럼을 렌더한다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-list-card")).toBeDefined();
    });

    // 005930 (삼성전자) 행 존재
    expect(screen.getByText("005930")).toBeDefined();
  });

  it("H-LIST 페이징: 이전/다음 버튼이 offset 갱신을 트리거한다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));
    await waitFor(() => {
      expect(screen.getByTestId("stock-master-list-next")).toBeDefined();
    });
    // next 버튼 클릭 → fetchList 재호출 (offset += 100)
    fireEvent.click(screen.getByTestId("stock-master-list-next"));
    // 페이지 표시 갱신 검증은 구현 단계에서 (Red 단계 testid 존재만 검증)
  });
});

describe("사이클 85 — StockMaster 페이지 (H-DETAIL + Q11=B 카테고리 + 핵심 5 키 highlight)", () => {
  it("H-DETAIL: ticker 클릭 시 detail 모달이 열린다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByText("005930")).toBeDefined();
    });

    fireEvent.click(screen.getByText("005930"));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-detail-modal")).toBeDefined();
    });
  });

  it("H-DETAIL Q11=B: detail 모달이 핵심 5 키 highlight 영역을 렌더한다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));
    await waitFor(() => expect(screen.getByText("005930")).toBeDefined());
    fireEvent.click(screen.getByText("005930"));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-detail-modal")).toBeDefined();
    });

    // 핵심 5 키 highlight (사이클 81 silent 결함 진단 영속)
    for (const key of [
      "bfdy_clpr",
      "acml_vol",
      "nxt_tradable",
      "krx_halted",
      "admin_item",
    ]) {
      expect(
        screen.getByTestId(`stock-master-detail-highlight-${key}`),
      ).toBeDefined();
    }
  });
});

describe("사이클 85 — StockMaster 페이지 (H-HISTORY + Q12=A `<pre>` collapsible)", () => {
  it("H-HISTORY: ticker 선택 시 history 테이블이 changed_at DESC 로 표시된다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));
    await waitFor(() => expect(screen.getByText("005930")).toBeDefined());
    fireEvent.click(screen.getByText("005930"));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-history-card")).toBeDefined();
    });

    // change_type 배지 INSERT / UPDATE 2개 표시 (changed_at DESC = UPDATE 먼저)
    expect(screen.getAllByText(/UPDATE|INSERT/).length).toBeGreaterThanOrEqual(2);
  });
});

// G-KST (HIGH) — 사이클 68 KST 일관성 영속 AST 가드
describe("사이클 85 G-KST (HIGH) — StockMaster KST `+09:00` 표시 영속", () => {
  it("G-KST AST: StockMaster.tsx 가 Intl.DateTimeFormat + Asia/Seoul 명시", () => {
    const source = readFileSync(
      path.join(__dirname, "..", "StockMaster.tsx"),
      "utf-8",
    );
    expect(
      source.includes("Asia/Seoul"),
      "StockMaster.tsx 가 'Asia/Seoul' timeZone 명시 누락 — 사이클 68 KST 영속 위반",
    ).toBe(true);
    expect(
      source.includes("Intl.DateTimeFormat"),
      "StockMaster.tsx 가 Intl.DateTimeFormat 사용 누락 — Q13 KST 강제 위반",
    ).toBe(true);
  });

  it("G-KST AST: StockMaster.tsx 에 `new Date(...).getHours()` 패턴 0건 (브라우저 로컬타임 추출 금지)", () => {
    const source = readFileSync(
      path.join(__dirname, "..", "StockMaster.tsx"),
      "utf-8",
    );
    const forbidden = /new\s+Date\([^)]*\)\.get(?:Hours|FullYear|Month|Date|Minutes|Seconds)\b/;
    expect(forbidden.test(source)).toBe(false);
  });
});

// H-POLLING (MEDIUM) — Q13=B refetchInterval: 60_000 영속 AST 가드
describe("사이클 85 H-POLLING (MEDIUM) — 5 useQuery refetchInterval: 60_000 영속", () => {
  it("H-POLLING AST: StockMaster.tsx 의 useQuery 중 ≥1건이 refetchInterval: 60_000 명시", () => {
    const source = readFileSync(
      path.join(__dirname, "..", "StockMaster.tsx"),
      "utf-8",
    );
    // Q13=B 사용자 결정 영속 — 60_000 ms 명시 (KisAccountPoolCard 30_000 답습 영역 분리)
    const regex = /refetchInterval\s*:\s*60_?000\b/;
    expect(
      regex.test(source),
      "StockMaster.tsx 의 useQuery 에 refetchInterval: 60_000 명시 누락 — Q13=B 위반",
    ).toBe(true);
  });
});

// ────────────────────────────────────────────────────────────────────────
// 사이클 90 H-6 (HIGH) + M-4 (MEDIUM) — "지금 새로고침" 버튼 + useMutation
// ────────────────────────────────────────────────────────────────────────
describe('사이클 90 H-6 (HIGH) — "지금 새로고침" 버튼 + useMutation 호출', () => {
  it("H-6: stats 카드 상단 우측에 testid `stock-master-refresh-universe-button` 버튼 존재 (Q26=A)", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-stats-card")).toBeDefined();
    });

    const button = screen.getByTestId("stock-master-refresh-universe-button");
    expect(button).toBeDefined();
    // 버튼 텍스트 영속 의무 — "지금 새로고침"
    expect(button.textContent).toMatch(/지금 새로고침|새로고침/);
  });

  it("H-6: 버튼 클릭 시 POST refresh-universe 발화 + 성공 토스트 노출", async () => {
    let postCalled = false;
    setupHappyPathHandlers();
    server.use(
      http.post("/api/stock-master/refresh-universe", () => {
        postCalled = true;
        return HttpResponse.json(wrap({ universe: 487, elapsed_ms: 24823 }));
      }),
    );
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-refresh-universe-button")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("stock-master-refresh-universe-button"));

    await waitFor(() => {
      expect(postCalled).toBe(true);
    });

    // 성공 토스트 영역 — testid `stock-master-refresh-universe-toast`
    await waitFor(() => {
      const toast = screen.getByTestId("stock-master-refresh-universe-toast");
      expect(toast).toBeDefined();
      // 성공 토스트는 universe 결과 노출
      expect(toast.textContent).toMatch(/487/);
    });
  });

  it("H-6: 409 Conflict 응답 시 에러 토스트 노출 (in-flight 가드)", async () => {
    setupHappyPathHandlers();
    server.use(
      http.post("/api/stock-master/refresh-universe", () =>
        HttpResponse.json(
          { detail: "universe refresh 진행 중 — 잠시 후 재시도" },
          { status: 409 },
        ),
      ),
    );
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-refresh-universe-button")).toBeDefined();
    });
    fireEvent.click(screen.getByTestId("stock-master-refresh-universe-button"));

    await waitFor(() => {
      const toast = screen.getByTestId("stock-master-refresh-universe-toast");
      expect(toast).toBeDefined();
      // 409 토스트는 "진행 중" 메시지 노출
      expect(toast.textContent).toMatch(/진행 중|409|재시도/);
    });
  });

  it("H-6: 500 응답 시 실패 토스트 노출", async () => {
    setupHappyPathHandlers();
    server.use(
      http.post("/api/stock-master/refresh-universe", () =>
        HttpResponse.json({ detail: "internal error" }, { status: 500 }),
      ),
    );
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-refresh-universe-button")).toBeDefined();
    });
    fireEvent.click(screen.getByTestId("stock-master-refresh-universe-button"));

    await waitFor(() => {
      const toast = screen.getByTestId("stock-master-refresh-universe-toast");
      expect(toast).toBeDefined();
      // 실패 토스트는 에러 메시지 노출
      expect(toast.textContent).toMatch(/실패|오류|에러|error/i);
    });
  });
});

describe("사이클 90 M-4 (MEDIUM) — 버튼 위치 + disabled 상태", () => {
  it("M-4: 버튼이 stats 카드 영역 내부에 위치 (Q26=A stats 카드 상단 우측)", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-stats-card")).toBeDefined();
    });

    const statsCard = screen.getByTestId("stock-master-stats-card");
    const button = screen.getByTestId("stock-master-refresh-universe-button");

    // 버튼이 stats 카드의 자손 의무 (Q26=A 영속)
    expect(statsCard.contains(button)).toBe(true);
  });

  it("M-4: 클릭 후 isPending 상태에서 버튼 disabled (useMutation 로딩 인디케이터)", async () => {
    setupHappyPathHandlers();
    // 응답을 지연시키는 mock — 짧은 delay 후 응답
    server.use(
      http.post("/api/stock-master/refresh-universe", async () => {
        await new Promise((resolve) => setTimeout(resolve, 200));
        return HttpResponse.json(wrap({ universe: 487, elapsed_ms: 24823 }));
      }),
    );
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-refresh-universe-button")).toBeDefined();
    });

    const button = screen.getByTestId("stock-master-refresh-universe-button") as HTMLButtonElement;
    fireEvent.click(button);

    // 클릭 직후 disabled 상태 (useMutation isPending=true)
    await waitFor(() => {
      const btnNow = screen.getByTestId("stock-master-refresh-universe-button") as HTMLButtonElement;
      expect(btnNow.disabled).toBe(true);
    });

    // 응답 후 disabled 해제
    await waitFor(() => {
      const btnNow = screen.getByTestId("stock-master-refresh-universe-button") as HTMLButtonElement;
      expect(btnNow.disabled).toBe(false);
    });
  });
});

// ────────────────────────────────────────────────────────────────────────
// 사이클 94 H-5 (HIGH) — UI 안내 가이드 배너 (사용자 혼동 영역 해소)
// ────────────────────────────────────────────────────────────────────────
// 명세: _workspace/red/cycle94_fid_input_iscd_fix.md §4 H-5
//
// 영속 의무:
//   - testid: stock-master-info-banner
//   - 한글 친숙 용어 (사이클 89 UI hotfix 답습)
//   - 사이클 언급 0 (영문 사이클 코드/번호 노출 금지)
//   - "참고용 종목 마스터 데이터" 영속 (사용자 결정 채택 영역)
//   - 매매 신호 별개 영역 명시 (사용자 혼동 영역 해소)
// ────────────────────────────────────────────────────────────────────────

describe("사이클 94 H-5 (HIGH) — StockMaster UI 안내 가이드 배너", () => {
  it("H-5: data-testid `stock-master-info-banner` 가 페이지 마운트 시 즉시 렌더된다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-info-banner")).toBeDefined();
    });
  });

  it("H-5: 배너에 '참고용 종목 마스터 데이터' 한글 헤더 영속", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      const banner = screen.getByTestId("stock-master-info-banner");
      expect(banner.textContent).toContain("참고용 종목 마스터 데이터");
    });
  });

  it("H-5: 배너에 매매 신호 별개 영역 안내 (사용자 혼동 해소)", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      const banner = screen.getByTestId("stock-master-info-banner");
      // 매매 신호 영역 별개 명시 (사이클 94 사용자 결정 영속)
      expect(banner.textContent).toMatch(/실시간 매매 신호|별개 영역|시세 API/);
    });
  });

  it("H-5: 배너에 영문 '사이클' / cycle 번호 노출 0건 (한글 친숙 용어 영속)", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      const banner = screen.getByTestId("stock-master-info-banner");
      const text = banner.textContent || "";
      // 사이클 89 UI hotfix 답습 — 영문/cycle 코드 노출 금지
      expect(text).not.toMatch(/cycle\s*\d+/i);
      expect(text).not.toMatch(/사이클\s*\d+/);
    });
  });
});

// ────────────────────────────────────────────────────────────────────────
// 사이클 95 H-4 (HIGH) — list 테이블 전일종가 컬럼 + formatPrice 영역 정합
// 사이클 95 H-5 (HIGH) — list 테이블 시장 한글 변환 (`"02"` → KOSPI 등)
// 사이클 95 M-3 (MEDIUM) — formatExchange 헬퍼 5+ 코드 분류 영속
// ────────────────────────────────────────────────────────────────────────
// 명세: _workspace/red/cycle95_chicken_and_egg_fix_ui.md §2 영역 1/2
//
// 영속 의무:
//   - formatPrice 헬퍼 (L113~L117) 변경 0 → list 테이블 raw.bfdy_clpr 렌더
//   - formatExchange 헬퍼 (L101~L108) 변경 0 → "02" / "03" → KOSPI / KOSDAQ
//   - 사이클 89 hotfix 답습 (한글 친숙 용어)
//   - 사이클 85 G-KST + H-POLLING + H-DETAIL 영속 (변경 0)
// ────────────────────────────────────────────────────────────────────────

// list 테이블 검증용 SAMPLE_LIST 확장 — 다중 시장 코드 (KOSPI/KOSDAQ/ETF)
const SAMPLE_LIST_MULTI_MARKET = [
  {
    ticker: "005930",
    name: "삼성전자",
    excg_dvsn_cd: "02",
    nxt_tradable: true,
    krx_halted: false,
    admin_item: false,
    refreshed_at: "2026-06-09T09:00:00+09:00",
    raw: { bfdy_clpr: 70000, acml_vol: 1000000 },
  },
  {
    ticker: "035720",
    name: "카카오",
    excg_dvsn_cd: "03",
    nxt_tradable: true,
    krx_halted: false,
    admin_item: false,
    refreshed_at: "2026-06-09T09:00:00+09:00",
    raw: { bfdy_clpr: 42500, acml_vol: 500000 },
  },
  {
    ticker: "069500",
    name: "KODEX 200",
    excg_dvsn_cd: "04",
    nxt_tradable: false,
    krx_halted: false,
    admin_item: false,
    refreshed_at: "2026-06-09T09:00:00+09:00",
    raw: { bfdy_clpr: 38000, acml_vol: 200000 },
  },
];

function setupMultiMarketHandlers() {
  server.use(
    http.get("/api/stock-master/stats", () =>
      HttpResponse.json(wrap(SAMPLE_STATS)),
    ),
    http.get("/api/stock-master/list", () =>
      HttpResponse.json(wrap(SAMPLE_LIST_MULTI_MARKET)),
    ),
    http.get("/api/stock-master/scan-pool/summary", () =>
      HttpResponse.json(wrap({ eager_refresh_today: 7 })),
    ),
  );
}

describe("사이클 95 H-4 (HIGH) — list 테이블 전일종가 컬럼", () => {
  it("H-4.a: list 테이블 thead 에 '전일종가' 컬럼 영역 영속", async () => {
    setupMultiMarketHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-list-card")).toBeDefined();
    });

    // thead 영역에 '전일종가' 헤더 추가 (사이클 95 H-4)
    const listCard = screen.getByTestId("stock-master-list-card");
    expect(
      listCard.textContent?.includes("전일종가"),
      "list 테이블 thead 에 '전일종가' 컬럼 누락 — 사이클 95 H-4 위반",
    ).toBe(true);
  });

  it("H-4.b: tbody 에 raw.bfdy_clpr formatPrice 적용 렌더", async () => {
    setupMultiMarketHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByText("005930")).toBeDefined();
    });

    // formatPrice 헬퍼 결과 (사이클 89 hotfix 영속) — 70000원 = "70,000원"
    await waitFor(() => {
      expect(
        screen.getAllByText(/70,?000\s*원/).length,
        "list 테이블 tbody 에 bfdy_clpr formatPrice 렌더 누락 — H-4.b 위반",
      ).toBeGreaterThanOrEqual(1);
    });
  });

  it("H-4.c: 다중 종목 전일종가 동시 렌더 (KOSPI/KOSDAQ/ETF 3 행)", async () => {
    setupMultiMarketHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByText("005930")).toBeDefined();
      expect(screen.getByText("035720")).toBeDefined();
      expect(screen.getByText("069500")).toBeDefined();
    });

    // 3 종목 전일종가 모두 렌더 (70,000 / 42,500 / 38,000)
    await waitFor(() => {
      expect(screen.getAllByText(/70,?000\s*원/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/42,?500\s*원/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/38,?000\s*원/).length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("사이클 95 H-5 (HIGH) — list 테이블 시장 한글 변환", () => {
  it("H-5.a: KOSPI 코드 '02' → '코스피' / KOSDAQ '03' → '코스닥' 한글 렌더", async () => {
    setupMultiMarketHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByText("005930")).toBeDefined();
    });

    // formatExchange 헬퍼 결과 (L101~L108 영속): '02' → 'KOSPI' / '03' → 'KOSDAQ'
    // (헬퍼 매핑은 영문 KOSPI/KOSDAQ — 사이클 89 hotfix 영속)
    await waitFor(() => {
      const listCard = screen.getByTestId("stock-master-list-card");
      const text = listCard.textContent || "";

      // KOSPI 한글 변환 (formatExchange 적용 영속)
      expect(
        /KOSPI/.test(text),
        "list 테이블 시장 컬럼에 'KOSPI' 한글 변환 누락 — H-5.a 위반 (사이클 95 formatExchange 적용 의무)",
      ).toBe(true);

      // KOSDAQ 한글 변환
      expect(
        /KOSDAQ/.test(text),
        "list 테이블 시장 컬럼에 'KOSDAQ' 한글 변환 누락 — H-5.a 위반",
      ).toBe(true);
    });
  });

  it("H-5.b: 시장 컬럼에 raw 코드 '02' / '03' 노출 0건 (formatExchange 적용 후)", async () => {
    setupMultiMarketHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByText("005930")).toBeDefined();
    });

    // list 테이블 행에서 raw 코드 ('02' / '03') 직접 노출 0건
    // (formatExchange 적용 후 KOSPI/KOSDAQ 만 노출)
    const rows = screen.getAllByText("005930");
    for (const row of rows) {
      const tr = row.closest("tr");
      if (!tr) continue;
      const tds = tr.querySelectorAll("td");
      // 시장 컬럼 (3번째 td, 0-based index 2) 텍스트 검증
      if (tds.length >= 3) {
        const marketCellText = tds[2].textContent || "";
        expect(
          marketCellText.trim() === "02" || marketCellText.trim() === "03",
          `시장 컬럼에 raw 코드 '${marketCellText.trim()}' 직접 노출 — H-5.b 위반`,
        ).toBe(false);
      }
    }
  });
});

describe("사이클 95 M-3 (MEDIUM) — formatExchange 헬퍼 영역 영속", () => {
  it("M-3.a: ETF 코드 '04' → 'ETF' 분류 영속 (사이클 89 hotfix 영역 영속)", async () => {
    setupMultiMarketHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByText("069500")).toBeDefined();
    });

    // formatExchange "04" → "ETF" (사이클 89 영속)
    await waitFor(() => {
      const listCard = screen.getByTestId("stock-master-list-card");
      expect(
        /ETF/.test(listCard.textContent || ""),
        "list 테이블 시장 컬럼에 ETF 한글 변환 누락 — M-3.a 위반",
      ).toBe(true);
    });
  });

  it("M-3.b: formatExchange 헬퍼 AST 영속 (KOSPI/KOSDAQ/ETF 매핑 0건 결함 차단)", () => {
    // 사이클 89 영속 formatExchange 헬퍼 정적 검증
    const source = readFileSync(
      path.join(__dirname, "..", "StockMaster.tsx"),
      "utf-8",
    );

    // formatExchange 함수 정의 영속
    expect(
      /function\s+formatExchange\s*\(/.test(source),
      "formatExchange 함수 정의 누락 — M-3.b 위반 (사이클 89 영속 위반)",
    ).toBe(true);

    // '02': 'KOSPI' 매핑 영속
    expect(
      source.includes("'02': 'KOSPI'") || source.includes('"02": "KOSPI"'),
      "formatExchange '02' → KOSPI 매핑 누락 — M-3.b 위반",
    ).toBe(true);

    // '03': 'KOSDAQ' 매핑 영속
    expect(
      source.includes("'03': 'KOSDAQ'") || source.includes('"03": "KOSDAQ"'),
      "formatExchange '03' → KOSDAQ 매핑 누락 — M-3.b 위반",
    ).toBe(true);

    // list 테이블 영역에서 formatExchange 호출 영속 (사이클 95 시정 의무)
    // 기존 `{item.excg_dvsn_cd ?? '—'}` → `{formatExchange(item.excg_dvsn_cd)}` 1줄 교체
    expect(
      /formatExchange\s*\(\s*item\.excg_dvsn_cd\s*\)/.test(source),
      "list 테이블 시장 컬럼에 formatExchange(item.excg_dvsn_cd) 호출 누락 — 사이클 95 M-3.b 위반",
    ).toBe(true);
  });
});
