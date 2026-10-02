/**
 * cycle403 — ETF 추세 전략(etf_trend) 신설의 프론트엔드 몫 중 StockMaster 영역.
 *
 * 배경:
 * - ETF 추세 유니버스 판정 4 키(`scty_grp_id_cd`/`etf_txtn_type_cd`/`etf_chas_erng_rt_dbnb`/
 *   `etf_etn_ivst_heed_item_yn`)는 `src/db/stock_master.py::list_etf_trend_universe` 와
 *   ETF 판정 정본 `src/engine/etf_like.py::ETF_GROUP_CODES` 가 모두 **`raw`** JSONB 컬럼에서
 *   읽는다(`raw->>'scty_grp_id_cd'` 등) — `master_raw` 컬럼이 아니다.
 * - `GET /api/stock-master/{ticker}` 상세 응답은 `src/models/stock.py::StockBasics` 를
 *   직렬화하는데, 이 모델은 `raw` 필드만 갖고 `master_raw` 는 애초에 내려오지 않는다
 *   (`src/db/stock_master.py::_from_row`). `StockMaster.tsx::getCategoryItems` 도
 *   `detail.raw` 만 조회한다(`detail.master_raw` 는 보지 않는다). 그래서 직전 사이클이
 *   이 4 키를 `master_raw.` 접두사로 등록한 것은 화면에 영원히 찍히지 않는 죽은 칸이었다
 *   (독립 검토 MED-4). 이 사이클은 접두사를 떼고 다른 `raw` 기반 키(`bfdy_clpr` 등)와
 *   같은 규칙으로 맞춘다.
 * - 루트 CLAUDE.md 「stock_master / stock_master_daily UI 동기화 의무」 — raw JSONB 키
 *   추가 시 FIELD_LABELS 한글 라벨 + CATEGORY_KEYS 배치가 의무다.
 * - 이 가드는 소스 문자열만 보지 않고 **실제로 렌더해서** 라벨·값이 보이는지 확인한다
 *   (사용자 메모리 feedback_new_ui_field_must_show_value — 검사 초록이 값이 찍힌다는
 *   증거가 아니다).
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { http, HttpResponse } from "msw";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import StockMaster from "../StockMaster";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STOCKMASTER_SRC_PATH = resolve(__dirname, "..", "StockMaster.tsx");

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
  count_all: 1,
  bfdy_clpr_present: 1,
  nxt_tradable_count: 1,
  top_10_recent: [
    { ticker: "069500", name: "KODEX 200", refreshed_at: "2026-10-03T09:00:00+09:00" },
  ],
  with_hts_avls: 1,
  with_acml_tr_pbmn: 1,
  total_daily_rows: 0,
  last_daily_load_at: null,
};

const SAMPLE_LIST = [
  {
    ticker: "069500",
    name: "KODEX 200",
    excg_dvsn_cd: "02",
    nxt_tradable: true,
    krx_halted: false,
    admin_item: false,
    refreshed_at: "2026-10-03T09:00:00+09:00",
    raw: { bfdy_clpr: 36000, acml_vol: 1000000 },
  },
];

// ETF 추세 유니버스 4 키는 `raw` 안에 있다 — master_raw 가 아니다.
const SAMPLE_DETAIL = {
  ticker: "069500",
  name: "KODEX 200",
  excg_dvsn_cd: "02",
  nxt_tradable: true,
  krx_halted: false,
  admin_item: false,
  refreshed_at: "2026-10-03T09:00:00+09:00",
  raw: {
    bfdy_clpr: 36000,
    acml_vol: 1000000,
    scty_grp_id_cd: "EF",
    etf_txtn_type_cd: "01",
    etf_chas_erng_rt_dbnb: "1",
    etf_etn_ivst_heed_item_yn: "N",
  },
};

function setupHandlers() {
  server.use(
    http.get("/api/stock-master/stats", () => HttpResponse.json(wrap(SAMPLE_STATS))),
    http.get("/api/stock-master/list", () => HttpResponse.json(wrap(SAMPLE_LIST))),
    http.get("/api/stock-master/scan-pool/summary", () =>
      HttpResponse.json(wrap({ eager_refresh_today: 0 })),
    ),
    http.get("/api/stock-master/069500", () => HttpResponse.json(wrap(SAMPLE_DETAIL))),
    http.get("/api/stock-master/069500/history", () => HttpResponse.json(wrap([]))),
  );
}

describe("cycle403 — StockMaster ETF 추세 유니버스 4 키가 raw 에서 실제로 렌더된다", () => {
  it("G-FE-ETF1: detail 모달이 raw 안의 ETF 4 키를 한글 라벨 + 값으로 보여준다", async () => {
    setupHandlers();
    render(withProviders(<StockMaster />));

    await waitFor(() => expect(screen.getByText("069500")).toBeDefined());
    fireEvent.click(screen.getByText("069500"));

    await waitFor(() => {
      expect(screen.getByTestId("stock-master-detail-modal")).toBeDefined();
    });

    // 라벨이 보여야 하고, (지웠던 master_raw 가 아니라) raw 에서 읽은 값이 그 옆에 보여야 한다.
    const expected: Array<[string, string]> = [
      ["증권그룹코드", "EF"],
      ["ETF 과세유형", "01"],
      ["ETF 추적배수", "1"],
      ["ETF/ETN 투자유의", "N"],
    ];
    for (const [labelFragment, value] of expected) {
      const label = await screen.findByText((content) => content.includes(labelFragment));
      const row = label.closest("div.text-sm") as HTMLElement | null;
      expect(row, `${labelFragment} 행을 찾을 수 없음`).not.toBeNull();
      expect(row?.textContent).toContain(value);
    }
  });

  it("G-FE-ETF2: 소스가 master_raw 접두사가 아니라 raw 평키로 ETF 4 키를 찾는다", () => {
    const src = readFileSync(STOCKMASTER_SRC_PATH, "utf-8");

    // 접두사를 뗀 평키 — getCategoryItems 가 detail.raw 만 조회하므로 이 모양이어야 값이 찍힌다.
    for (const key of [
      "scty_grp_id_cd",
      "etf_txtn_type_cd",
      "etf_chas_erng_rt_dbnb",
      "etf_etn_ivst_heed_item_yn",
    ]) {
      expect(src.includes(`'${key}'`), `${key} 가 소스에 없음`).toBe(true);
      expect(src.includes(`'master_raw.${key}'`), `${key} 가 여전히 master_raw. 접두사`).toBe(
        false,
      );
    }
  });
});
