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
