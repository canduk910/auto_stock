/**
 * 사이클 85 — stock-master API 단위 테스트 (L-API + H-404 + H-422).
 *
 * 답습 패턴: balance.test.ts / cash_usage_ratio.test.ts (사이클 65 trade-amount-filter).
 *
 * 검증 영역:
 * - L-API: 5 함수 (fetchStats / fetchList / fetchScanPoolSummary / fetchDetail / fetchHistory)
 *   모두 ApiResponse<T> 래퍼 data.data 추출 정합
 * - H-404: fetchDetail('999999') 시 백엔드 404 응답 → axios error throw
 * - H-422: fetchList(0, 0) / fetchList(1001, 0) / fetchList(100, -1) 시 백엔드 422 → axios error throw
 */
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import {
  fetchStats,
  fetchList,
  fetchScanPoolSummary,
  fetchDetail,
  fetchHistory,
  refreshUniverseNow,
} from "../stock-master";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("사이클 85 — stock-master API 래퍼 (L-API)", () => {
  it("L-API-1: fetchStats 가 ApiResponse<StockMasterStats> 의 data 를 추출한다", async () => {
    server.use(
      http.get("/api/stock-master/stats", () =>
        HttpResponse.json(
          wrap({
            count_all: 29,
            bfdy_clpr_present: 28,
            nxt_tradable_count: 25,
            top_10_recent: [
              { ticker: "005930", name: "삼성전자", refreshed_at: "2026-06-09T09:00:00+09:00" },
            ],
          }),
        ),
      ),
    );
    const data = await fetchStats();
    expect(data.count_all).toBe(29);
    expect(data.bfdy_clpr_present).toBe(28);
    expect(data.nxt_tradable_count).toBe(25);
    expect(data.top_10_recent).toHaveLength(1);
    expect(data.top_10_recent[0].ticker).toBe("005930");
  });

  it("L-API-2: fetchList 가 페이징 인자를 전송하고 list 를 반환한다", async () => {
    let receivedUrl = "";
    server.use(
      http.get("/api/stock-master/list", ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json(
          wrap([
            {
              ticker: "005930",
              name: "삼성전자",
              excg_dvsn_cd: "01",
              nxt_tradable: true,
              krx_halted: false,
              admin_item: false,
              refreshed_at: "2026-06-09T09:00:00+09:00",
              raw: { bfdy_clpr: 70000 },
            },
          ]),
        );
      }),
    );
    const items = await fetchList(100, 0);
    expect(items).toHaveLength(1);
    expect(items[0].ticker).toBe("005930");
    expect(receivedUrl).toContain("limit=100");
    expect(receivedUrl).toContain("offset=0");
  });

  it("L-API-3: fetchScanPoolSummary 가 eager_refresh_today 를 추출한다", async () => {
    server.use(
      http.get("/api/stock-master/scan-pool/summary", () =>
        HttpResponse.json(wrap({ eager_refresh_today: 7 })),
      ),
    );
    const data = await fetchScanPoolSummary();
    expect(data.eager_refresh_today).toBe(7);
  });

  it("L-API-4: fetchDetail 이 ticker 별 detail 을 추출한다", async () => {
    server.use(
      http.get("/api/stock-master/005930", () =>
        HttpResponse.json(
          wrap({
            ticker: "005930",
            name: "삼성전자",
            excg_dvsn_cd: "01",
            nxt_tradable: true,
            krx_halted: false,
            admin_item: false,
            refreshed_at: "2026-06-09T09:00:00+09:00",
            raw: { bfdy_clpr: 70000, acml_vol: 1000000 },
          }),
        ),
      ),
    );
    const detail = await fetchDetail("005930");
    expect(detail.ticker).toBe("005930");
    expect(detail.raw.bfdy_clpr).toBe(70000);
  });

  it("L-API-5: fetchHistory 가 ticker 별 history 를 추출한다", async () => {
    server.use(
      http.get("/api/stock-master/005930/history", () =>
        HttpResponse.json(
          wrap([
            {
              id: 1,
              ticker: "005930",
              change_type: "TTL_REFRESH",
              before_raw: { bfdy_clpr: 70000 },
              after_raw: { bfdy_clpr: 70000 },
              changed_at: "2026-06-09T09:00:00+09:00",
            },
          ]),
        ),
      ),
    );
    const items = await fetchHistory("005930", 100);
    expect(items).toHaveLength(1);
    expect(items[0].change_type).toBe("TTL_REFRESH");
  });
});

describe("사이클 85 — stock-master API 에러 처리 (H-404 + H-422)", () => {
  it("H-404: fetchDetail 시 백엔드 404 응답 → axios error throw", async () => {
    server.use(
      http.get("/api/stock-master/999999", () =>
        HttpResponse.json(
          { success: false, data: null, message: "ticker not found" },
          { status: 404 },
        ),
      ),
    );
    await expect(fetchDetail("999999")).rejects.toThrow();
  });

  it("H-422-1: fetchList(0, 0) (limit < 1) → 422 axios error throw", async () => {
    server.use(
      http.get("/api/stock-master/list", () =>
        HttpResponse.json(
          { detail: [{ loc: ["query", "limit"], msg: "ensure ge 1" }] },
          { status: 422 },
        ),
      ),
    );
    await expect(fetchList(0, 0)).rejects.toThrow();
  });

  it("H-422-2: fetchList(1001, 0) (limit > 1000) → 422 axios error throw", async () => {
    server.use(
      http.get("/api/stock-master/list", () =>
        HttpResponse.json(
          { detail: [{ loc: ["query", "limit"], msg: "ensure le 1000" }] },
          { status: 422 },
        ),
      ),
    );
    await expect(fetchList(1001, 0)).rejects.toThrow();
  });

  it("H-422-3: fetchList(100, -1) (offset < 0) → 422 axios error throw", async () => {
    server.use(
      http.get("/api/stock-master/list", () =>
        HttpResponse.json(
          { detail: [{ loc: ["query", "offset"], msg: "ensure ge 0" }] },
          { status: 422 },
        ),
      ),
    );
    await expect(fetchList(100, -1)).rejects.toThrow();
  });
});

describe("사이클 90 H-5 (HIGH) — refreshUniverseNow API 정합", () => {
  it("H-5: refreshUniverseNow 가 POST 호출 + ApiResponse<RefreshUniverseResult> data 추출", async () => {
    let receivedMethod = "";
    server.use(
      http.post("/api/stock-master/refresh-universe", ({ request }) => {
        receivedMethod = request.method;
        return HttpResponse.json(
          wrap({ universe: 487, elapsed_ms: 24823 }),
        );
      }),
    );
    const result = await refreshUniverseNow();
    expect(result.universe).toBe(487);
    expect(result.elapsed_ms).toBe(24823);
    expect(receivedMethod).toBe("POST");
  });

  it("H-5-conflict: refreshUniverseNow 가 409 Conflict 응답 시 axios error throw", async () => {
    server.use(
      http.post("/api/stock-master/refresh-universe", () =>
        HttpResponse.json(
          { detail: "universe refresh 진행 중 — 잠시 후 재시도" },
          { status: 409 },
        ),
      ),
    );
    await expect(refreshUniverseNow()).rejects.toThrow();
  });

  it("H-5-empty: refreshUniverseNow 가 universe=0 graceful 응답 처리", async () => {
    server.use(
      http.post("/api/stock-master/refresh-universe", () =>
        HttpResponse.json(wrap({ universe: 0, elapsed_ms: 120 })),
      ),
    );
    const result = await refreshUniverseNow();
    expect(result.universe).toBe(0);
    expect(result.elapsed_ms).toBe(120);
  });
});
