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

// 사이클 169 의미 전환 (사이클 66 K-2) — migration 036 (사이클 150) 신 스키마.
// 기존 {id, before_raw, after_raw} → {seq, raw}. seq0=최신본 / seq1=직전본.
// 백엔드 list_history 는 changed_at DESC 정렬이지만 UPDATE 시 seq0/seq1
// changed_at 이 동일(now())이라 순서 비결정 → 프론트가 seq ASC 재정렬.
const SAMPLE_HISTORY = [
  {
    ticker: "005930",
    seq: 1,
    change_type: "UPDATE",
    raw: { bfdy_clpr: 70000 },
    changed_at: "2026-06-09T09:05:00+09:00",
  },
  {
    ticker: "005930",
    seq: 0,
    change_type: "UPDATE",
    raw: { bfdy_clpr: 71500 },
    changed_at: "2026-06-09T09:05:00+09:00",
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
  it("H-HISTORY: ticker 선택 시 history 테이블이 표시된다 (사이클 169 신 스키마)", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));
    await waitFor(() => expect(screen.getByText("005930")).toBeDefined());
    fireEvent.click(screen.getByText("005930"));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-history-card")).toBeDefined();
    });

    // 사이클 169 의미 전환 — change_type 배지 2개 (seq0/seq1 두 스냅샷)
    expect(screen.getAllByText("UPDATE").length).toBeGreaterThanOrEqual(2);
  });
});

// ────────────────────────────────────────────────────────────────────────
// 사이클 169 (2026-06-20) — 변경이력 탭 신 스키마 (seq/raw) 렌더 회귀 가드
// 근본 원인 = 사이클 150 migration 036 이 stock_master_history 스키마 재설계
// (id/before_raw/after_raw → seq/raw) 했으나 프론트 UI 미동기화 → 빈 화면.
// 사용자 결정 Option A = seq0(최신본)/seq1(직전본) 2 스냅샷 각각 표시.
// ────────────────────────────────────────────────────────────────────────
describe("사이클 169 — 변경이력 탭 신 스키마 (seq/raw, 최신본/직전본)", () => {
  async function openHistory() {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));
    await waitFor(() => expect(screen.getByText("005930")).toBeDefined());
    fireEvent.click(screen.getByText("005930"));
    await waitFor(() => {
      expect(screen.getByTestId("stock-master-history-card")).toBeDefined();
    });
  }

  it("G-169-1: seq0=최신본 / seq1=직전본 라벨이 각각 표시된다", async () => {
    await openHistory();
    expect(screen.getByText("최신본")).toBeDefined();
    expect(screen.getByText("직전본")).toBeDefined();
  });

  it("G-169-2: seq ASC 정렬 — 최신본 행이 직전본 행보다 먼저 렌더된다", async () => {
    await openHistory();
    const card = screen.getByTestId("stock-master-history-card");
    const text = card.textContent ?? "";
    const idxLatest = text.indexOf("최신본");
    const idxPrev = text.indexOf("직전본");
    expect(idxLatest).toBeGreaterThanOrEqual(0);
    expect(idxPrev).toBeGreaterThan(idxLatest);
  });

  it("G-169-3: raw 스냅샷 CollapsiblePre 펼치면 raw JSONB 값이 표시된다", async () => {
    await openHistory();
    // 두 행 모두 'raw' 라벨 버튼 (CollapsiblePre label="raw")
    const rawButtons = screen.getAllByRole("button", { name: "raw" });
    expect(rawButtons.length).toBe(2);
    fireEvent.click(rawButtons[0]);
    // seq0 (최신본) raw = { bfdy_clpr: 71500 }
    await waitFor(() => {
      expect(screen.getByText(/71500/)).toBeDefined();
    });
  });

  it("G-169-4: change_type 배지가 신 스키마 행마다 렌더된다", async () => {
    await openHistory();
    expect(screen.getAllByText("UPDATE").length).toBe(2);
  });

  it("G-169-AST: StockMaster.tsx 에 before_raw / after_raw 잔존 0건 (사이클 150 회귀 차단)", () => {
    const source = readFileSync(
      path.join(__dirname, "..", "StockMaster.tsx"),
      "utf-8",
    );
    expect(
      source.includes("before_raw"),
      "StockMaster.tsx 에 before_raw 잔존 — 사이클 150 신 스키마 미동기화 회귀",
    ).toBe(false);
    expect(
      source.includes("after_raw"),
      "StockMaster.tsx 에 after_raw 잔존 — 사이클 150 신 스키마 미동기화 회귀",
    ).toBe(false);
  });

  it("G-169-TYPE-AST: stock-master.ts 타입이 신 스키마 (seq/raw) — 폐기 필드 0건", () => {
    const source = readFileSync(
      path.join(__dirname, "..", "..", "types", "stock-master.ts"),
      "utf-8",
    );
    // StockMasterHistoryItem interface body 한정 검사 (docstring 설명 텍스트 제외)
    const m = source.match(
      /interface StockMasterHistoryItem\s*\{([\s\S]*?)\}/,
    );
    expect(m, "StockMasterHistoryItem interface 누락").not.toBeNull();
    const body = m?.[1] ?? "";
    // 폐기 필드 0건
    expect(body.includes("before_raw")).toBe(false);
    expect(body.includes("after_raw")).toBe(false);
    expect(body.includes("TTL_REFRESH")).toBe(false);
    // 신 스키마 필드 존재
    expect(body.includes("seq")).toBe(true);
    expect(/\braw\b/.test(body)).toBe(true);
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

  it("H-6: 버튼 클릭 시 POST refresh-universe 발화 + 시작 토스트 노출 (사이클 127 fire-and-forget)", async () => {
    let postCalled = false;
    setupHappyPathHandlers();
    server.use(
      http.post("/api/stock-master/refresh-universe", () => {
        postCalled = true;
        // 사이클 127 — 202 Accepted + RefreshStartedResponse
        return HttpResponse.json(wrap({ status: "started", task_key: "universe" }), {
          status: 202,
        });
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

    // 사이클 127 — 시작 토스트 (fire-and-forget). 결과 카운터는 RefreshProgressBanner 폴링.
    await waitFor(() => {
      const toast = screen.getByTestId("stock-master-refresh-universe-toast");
      expect(toast).toBeDefined();
      expect(toast.textContent).toMatch(/시작|상단 배너/);
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
      // 실패 토스트는 에러 메시지 노출 (사이클 106 Q3=A: "KIS API 일시 결함" 포함)
      expect(toast.textContent).toMatch(/실패|오류|에러|error|KIS API/i);
    });
  });
});

// ────────────────────────────────────────────────────────────────────────
// 사이클 106 G-TOAST1 (HIGH) — Q3=A 적재 실패 toast 정밀화
// ────────────────────────────────────────────────────────────────────────
// 영속 의무:
//   - 5xx 에러 toast 에 "KIS API 일시 결함" 명시 (사이클 76 graceful 영역 정합)
//   - 409 Conflict toast 는 변경 없음 ("진행 중" 영속)
// ────────────────────────────────────────────────────────────────────────

describe("사이클 106 G-TOAST1 (HIGH) — 적재 실패 toast 정밀화 (Q3=A)", () => {
  it("G-TOAST1: 5xx 에러 toast 에 'KIS API 일시 결함' 문구 포함", async () => {
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
      // Q3=A 정밀화 — "KIS API 일시 결함" 명시 (사이클 106 영속)
      expect(toast.textContent).toContain("KIS API 일시 결함");
    });
  });

  it("G-TOAST1: 409 Conflict toast 는 '진행 중' 메시지 영속 (Q3=A 영향 없음)", async () => {
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
      // 409 분기는 사이클 90 H-6 영속 — 사이클 106 변경 무관
      expect(toast.textContent).toMatch(/진행 중|재시도/);
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
// 사이클 106 G-BANNER (HIGH/MEDIUM) — 안내 배너 갱신 회귀 가드
// ────────────────────────────────────────────────────────────────────────
// 영속 의무:
//   - G-BANNER1 (HIGH): testid stock-master-info-banner 영속 존재
//   - G-BANNER2 (HIGH): 사이클 94 무효 메시지 ("각 전략의 후보 종목은 매 사이클") 부재
//   - G-BANNER3 (MEDIUM): 신규 메시지 ("매일 20:00 KRX/KOSDAQ 전 종목 일괄 적재") 존재
//   - 사이클 89 한글 친숙 용어 영속 (영문 cycle 번호 노출 금지)
// ────────────────────────────────────────────────────────────────────────

describe("사이클 106 G-BANNER1 (HIGH) — stock-master-info-banner testid 영속", () => {
  it("G-BANNER1: data-testid `stock-master-info-banner` 가 페이지 마운트 시 즉시 렌더된다", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-info-banner")).toBeDefined();
    });
  });
});

describe("사이클 106 G-BANNER2 (HIGH) — 사이클 94 무효 메시지 영구 부재", () => {
  it("G-BANNER2: 배너에 사이클 94 영역 메시지 ('각 전략의 후보 종목은 매 사이클') 미존재", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      const banner = screen.getByTestId("stock-master-info-banner");
      // 사이클 94 무효 메시지 영구 제거 확인 (Q2=A 신규 메시지로 대체)
      expect(banner.textContent).not.toContain("각 전략의 후보 종목은 매 사이클");
    });
  });

  it("G-BANNER2: 배너에 영문 cycle 번호 노출 0건 (한글 친숙 용어 영속)", async () => {
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

describe("사이클 106 G-BANNER3 (MEDIUM) — Q2=A 신규 메시지 존재", () => {
  it("G-BANNER3: 배너에 '매일 20:00 KRX/KOSDAQ 전 종목 일괄 적재' 메시지 존재", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      const banner = screen.getByTestId("stock-master-info-banner");
      // Q2=A 사용자 결정 영속 — 20:00 일괄 적재 안내 메시지
      expect(banner.textContent).toContain("매일 20:00");
    });
  });

  it("G-BANNER3: 배너 제목이 '종목 마스터 데이터' (갱신된 헤더 영속)", async () => {
    setupHappyPathHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => {
      const banner = screen.getByTestId("stock-master-info-banner");
      expect(banner.textContent).toContain("종목 마스터 데이터");
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

// ────────────────────────────────────────────────────────────────────────
// 사이클 124 — StockMaster UI 확장 회귀 가드
//
// 영속 의무:
//   G-STATS-8 (HIGH): Stats 카드 4 → 8 개 (신규 4 testid 렌더)
//   G-TAB-1   (HIGH): detail 모달에 탭 네비게이션 (stock-master-detail-tabs)
//   G-TAB-2   (HIGH): 일봉 탭 전환 시 OHLCV 테이블 렌더 (stock-master-daily-table)
//   G-HIGHLIGHT-NEW (MEDIUM): 신규 4 키 amber highlight 렌더
//   G-DAILY-AST     (MEDIUM): DailyTab useQuery retry:1 + refetchInterval:60_000 AST
//   G-STATS-AST     (MEDIUM): stats 신규 4 키 AST 정적 정합
// ────────────────────────────────────────────────────────────────────────

const SAMPLE_STATS_124 = {
  count_all: 2800,
  bfdy_clpr_present: 2750,
  nxt_tradable_count: 1200,
  top_10_recent: [
    { ticker: '005930', name: '삼성전자', refreshed_at: '2026-06-13T09:00:00+09:00' },
  ],
  with_hts_avls: 2800,
  with_acml_tr_pbmn: 2700,
  total_daily_rows: 84000,
  last_daily_load_at: '2026-06-13T20:00:00+09:00',
}

// cycle266 §C-3 — 종전 목은 `change_rate` 를 전부 진짜 number 로, `bas_dd` 를
// `YYYYMMDD` 로 만들어 **의도한 계약**만 담고 **실제 응답**을 담지 않았다. 그래서
// 일봉 탭이 프로덕션에서 3개월 넘게 흰 화면인 동안 이 파일은 계속 초록이었다.
// 실제 응답: `change_rate`/`prtt_rate` = NUMERIC(8,4) → asyncpg Decimal →
// pydantic v2 JSON **문자열**, `bas_dd` = DATE → `YYYY-MM-DD`.
// ⇒ 문자열 케이스(시정 전 모양)와 숫자 케이스(A-1 시정 후 모양)를 **함께** 담는다.
const SAMPLE_DAILY_ROWS = [
  {
    bas_dd: '2026-09-05',
    open_price: 74000,
    high_price: 75500,
    low_price: 73500,
    close_price: 75000,
    volume: 1000000,
    trade_value: 75000000000,
    change_rate: '1.2000',
    prtt_rate: '0.0000',
  },
  {
    bas_dd: '2026-09-04',
    open_price: 74100,
    high_price: 75600,
    low_price: 73600,
    close_price: 75100,
    volume: 1050000,
    trade_value: 75000000000,
    change_rate: 0.9,
    prtt_rate: '0.0000',
  },
  {
    bas_dd: '2026-09-03',
    open_price: 74200,
    high_price: 75700,
    low_price: 73700,
    close_price: 75200,
    volume: 1100000,
    trade_value: 75000000000,
    change_rate: '0.6000',
    prtt_rate: '0.0000',
  },
  {
    bas_dd: '2026-09-02',
    open_price: 74300,
    high_price: 75800,
    low_price: 73800,
    close_price: 75300,
    volume: 1150000,
    trade_value: 75000000000,
    change_rate: 0.3,
    prtt_rate: '0.0000',
  },
  {
    bas_dd: '2026-09-01',
    open_price: 74400,
    high_price: 75900,
    low_price: 73900,
    close_price: 75400,
    volume: 1200000,
    trade_value: 75000000000,
    change_rate: '0.0000',
    prtt_rate: '0.0000',
  },
]

function setup124Handlers() {
  server.use(
    http.get('/api/stock-master/stats', () =>
      HttpResponse.json(wrap(SAMPLE_STATS_124)),
    ),
    http.get('/api/stock-master/list', () =>
      HttpResponse.json(wrap(SAMPLE_LIST)),
    ),
    http.get('/api/stock-master/scan-pool/summary', () =>
      HttpResponse.json(wrap({ eager_refresh_today: 3 })),
    ),
    http.get('/api/stock-master/:ticker/daily', () =>
      HttpResponse.json(wrap(SAMPLE_DAILY_ROWS)),
    ),
    http.get('/api/stock-master/005930', () =>
      HttpResponse.json(
        wrap({
          ...SAMPLE_DETAIL,
          raw: {
            ...SAMPLE_DETAIL.raw,
            hts_avls: 500000,
            acml_tr_pbmn: 70_000_000_000,
            lstn_stcn: 5_969_782_550,
            prdy_vrss: 1500,
          },
        }),
      ),
    ),
    http.get('/api/stock-master/005930/history', () =>
      HttpResponse.json(wrap(SAMPLE_HISTORY)),
    ),
  )
}

describe('사이클 124 G-STATS-8 (HIGH) — Stats 카드 8개 렌더', () => {
  it('G-STATS-8: 신규 4 카드 testid 가 모두 렌더된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-stats-card')).toBeDefined()
    })

    // 신규 4 카드 testid 영속
    for (const testid of [
      'stock-master-stats-with-hts-avls',
      'stock-master-stats-with-acml-tr-pbmn',
      'stock-master-stats-total-daily-rows',
      'stock-master-stats-last-daily-load-at',
    ]) {
      expect(
        screen.getByTestId(testid),
        `신규 stats 카드 testid '${testid}' 누락 — 사이클 124 Q3=A 위반`,
      ).toBeDefined()
    }
  })

  it('G-STATS-8: with_hts_avls=2800 / with_acml_tr_pbmn=2700 값이 카드에 표시된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-stats-with-hts-avls')).toBeDefined()
    })

    const htsCard = screen.getByTestId('stock-master-stats-with-hts-avls')
    expect(htsCard.textContent).toContain('2800')

    const trCard = screen.getByTestId('stock-master-stats-with-acml-tr-pbmn')
    expect(trCard.textContent).toContain('2700')
  })

  it('G-STATS-8: total_daily_rows=84000 이 쉼표 포함 숫자로 표시된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-stats-total-daily-rows')).toBeDefined()
    })

    const totalRowsCard = screen.getByTestId('stock-master-stats-total-daily-rows')
    // toLocaleString('ko-KR') 적용 → "84,000" 형식
    expect(totalRowsCard.textContent).toMatch(/84[,.]?000/)
  })

  it('G-STATS-8: last_daily_load_at 가 KST 포맷으로 마지막 일봉 적재 카드에 표시된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-stats-last-daily-load-at')).toBeDefined()
    })

    const lastLoadCard = screen.getByTestId('stock-master-stats-last-daily-load-at')
    // KST 포맷 (formatKst 적용) — 날짜 포함 텍스트
    expect(lastLoadCard.textContent).toMatch(/2026|미적재/)
  })
})

describe('사이클 124 G-TAB-1 (HIGH) — detail 모달 탭 네비게이션', () => {
  it('G-TAB-1: ticker 클릭 시 detail 모달에 탭 네비게이션 testid 가 존재한다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByText('005930')).toBeDefined()
    })
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-modal')).toBeDefined()
    })

    // 탭 컨테이너 + 2개 탭 버튼 testid 영속
    expect(screen.getByTestId('stock-master-detail-tabs')).toBeDefined()
    expect(screen.getByTestId('stock-master-tab-detail')).toBeDefined()
    expect(screen.getByTestId('stock-master-tab-daily')).toBeDefined()
  })

  it('G-TAB-1: 기본 탭은 "상세" 탭 (detail) 이 활성 상태이다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-tabs')).toBeDefined()
    })

    const detailTab = screen.getByTestId('stock-master-tab-detail')
    // 상세 탭은 blue border-b-2 활성 스타일 (border-blue-500 클래스)
    expect(detailTab.className).toContain('border-blue-500')
  })
})

describe('사이클 124 G-TAB-2 (HIGH) — 일봉 탭 전환 + OHLCV 테이블', () => {
  it('G-TAB-2: "일봉 (30일)" 탭 클릭 시 stock-master-daily-table 이 렌더된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-tabs')).toBeDefined()
    })

    // 일봉 탭 클릭
    fireEvent.click(screen.getByTestId('stock-master-tab-daily'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-daily-table')).toBeDefined()
    })
  })

  it('G-TAB-2: 일봉 테이블에 기준일 / 시가 / 고가 / 저가 / 종가 / 거래량 / 등락률 헤더 존재', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-tabs')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('stock-master-tab-daily'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-daily-table')).toBeDefined()
    })

    const table = screen.getByTestId('stock-master-daily-table')
    const headerText = table.textContent || ''
    for (const header of ['기준일', '시가', '고가', '저가', '종가', '거래량', '등락률']) {
      expect(
        headerText.includes(header),
        `일봉 테이블 헤더 '${header}' 누락 — G-TAB-2 위반`,
      ).toBe(true)
    }
  })

  it('G-TAB-2: 일봉 테이블에 mock 데이터 행 (bas_dd "2026-09-05") 이 표시된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-tabs')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('stock-master-tab-daily'))

    await waitFor(() => {
      // SAMPLE_DAILY_ROWS 기준일 = "2026-09-05" (첫 번째 행, i=0 → 5-0=5).
      // cycle266 §C-3 — `bas_dd` 는 DATE 컬럼이라 응답이 `YYYY-MM-DD` 다
      // (종전 목의 `20260613` 은 KIS 원본 필드 모양이지 우리 응답 모양이 아니다).
      expect(screen.getByText('2026-09-05')).toBeDefined()
    })
  })
})

describe('사이클 124 G-HIGHLIGHT-NEW (MEDIUM) — 신규 4 키 amber highlight', () => {
  it('G-HIGHLIGHT-NEW: hts_avls / acml_tr_pbmn / lstn_stcn / prdy_vrss 가 amber highlight 로 렌더된다', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    // detail 데이터 로드 완료 대기 (모달 + data 렌더 완료 시점)
    for (const key of ['hts_avls', 'acml_tr_pbmn', 'lstn_stcn', 'prdy_vrss']) {
      await waitFor(
        () =>
          expect(
            screen.getByTestId(`stock-master-detail-highlight-${key}`),
            `신규 highlight 키 '${key}' testid 누락 — 사이클 124 Q2=A 위반`,
          ).toBeDefined(),
        { timeout: 3000 },
      )
    }
  })

  it('G-HIGHLIGHT-NEW: 기존 5 키 highlight 도 동시 렌더 (영속 위반 0)', async () => {
    setup124Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    // 기존 5 키도 영속 (사이클 85 Q11=B) — detail 데이터 로드 완료 대기
    for (const key of ['bfdy_clpr', 'acml_vol', 'nxt_tradable', 'krx_halted', 'admin_item']) {
      await waitFor(
        () =>
          expect(
            screen.getByTestId(`stock-master-detail-highlight-${key}`),
            `기존 highlight 키 '${key}' 누락 — 사이클 85 Q11=B 위반`,
          ).toBeDefined(),
        { timeout: 3000 },
      )
    }
  })
})

describe('사이클 124 G-DAILY-AST (MEDIUM) — DailyTab useQuery retry:1 AST 정적 가드', () => {
  it('G-DAILY-AST: StockMaster.tsx 에 stock-master-daily-table testid 가 존재한다', () => {
    const source = readFileSync(
      path.join(__dirname, '..', 'StockMaster.tsx'),
      'utf-8',
    )
    expect(
      source.includes('stock-master-daily-table'),
      "StockMaster.tsx 에 data-testid 'stock-master-daily-table' 누락 — 사이클 124 Q1=A 위반",
    ).toBe(true)
  })

  it('G-DAILY-AST: DailyTab useQuery 에 retry: 1 명시 (사이클 65 H3 영속)', () => {
    const source = readFileSync(
      path.join(__dirname, '..', 'StockMaster.tsx'),
      'utf-8',
    )
    // DailyTab 함수 내에 retry: 1 + refetchInterval: 60_000 동시 존재
    expect(
      /DailyTab[\s\S]{0,600}retry\s*:\s*1/.test(source),
      'DailyTab useQuery 에 retry: 1 누락 — 사이클 65 H3 영속 위반',
    ).toBe(true)
    expect(
      /DailyTab[\s\S]{0,600}refetchInterval\s*:\s*60_?000/.test(source),
      'DailyTab useQuery 에 refetchInterval: 60_000 누락 — Q13=B 영속 위반',
    ).toBe(true)
  })

  it('G-DAILY-AST: fetchDaily 함수가 stock-master.ts API 클라이언트에 존재한다', () => {
    const source = readFileSync(
      path.join(__dirname, '../../api/stock-master.ts'),
      'utf-8',
    )
    expect(
      source.includes('fetchDaily'),
      'stock-master.ts 에 fetchDaily 함수 누락 — 사이클 124 Q1=A 위반',
    ).toBe(true)
    expect(
      source.includes('/daily'),
      'stock-master.ts 에 /daily 경로 누락 — 사이클 124 Q1=A 위반',
    ).toBe(true)
  })
})

describe('사이클 124 G-STATS-AST (MEDIUM) — Stats 신규 4 키 타입 정합 AST', () => {
  it('G-STATS-AST: stock-master.ts 타입 파일에 StockMasterDailyRow 인터페이스가 존재한다', () => {
    const source = readFileSync(
      path.join(__dirname, '../../types/stock-master.ts'),
      'utf-8',
    )
    expect(
      source.includes('StockMasterDailyRow'),
      'types/stock-master.ts 에 StockMasterDailyRow 인터페이스 누락 — 사이클 124 Q1=A 위반',
    ).toBe(true)
    // 필수 필드 영속
    for (const field of ['bas_dd', 'open_price', 'close_price', 'volume', 'change_rate']) {
      expect(
        source.includes(field),
        `StockMasterDailyRow 인터페이스에 '${field}' 필드 누락 — 사이클 124 Q1=A 위반`,
      ).toBe(true)
    }
  })

  it('G-STATS-AST: StockMasterStats 에 신규 4 필드가 정의되어 있다', () => {
    const source = readFileSync(
      path.join(__dirname, '../../types/stock-master.ts'),
      'utf-8',
    )
    for (const field of ['with_hts_avls', 'with_acml_tr_pbmn', 'total_daily_rows', 'last_daily_load_at']) {
      expect(
        source.includes(field),
        `StockMasterStats 에 '${field}' 필드 누락 — 사이클 124 Q3=A 위반`,
      ).toBe(true)
    }
  })
})

// ────────────────────────────────────────────────────────────────────────
// 기존 영속 테스트 계속
// ────────────────────────────────────────────────────────────────────────

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
