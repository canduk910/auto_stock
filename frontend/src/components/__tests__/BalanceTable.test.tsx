/**
 * BalanceTable — 거래시장 컬럼 (J1, 2026-05-11).
 *
 * `/api/balance` Holding 응답에 stock_master(CTPF1002R 캐시) 의
 *   `nxt_tradable / krx_halted / excg_dvsn_cd` 가 join 되면
 * 보유 종목 행마다 거래시장 배지를 5가지 케이스로 노출한다.
 *
 *   nxt_tradable=true  && !krx_halted   → `KRX+NXT` (emerald)
 *   nxt_tradable=true  && krx_halted    → `NXT만`   (amber)
 *   nxt_tradable=false && !krx_halted   → `KRX`     (gray)
 *   krx_halted=true    && !nxt_tradable → `정지`    (red)
 *   모든 필드 null/undefined            → `확인중`   (light-gray)
 */

import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import BalanceTable from "../BalanceTable";
import type { Holding } from "../../types/balance";

function makeHolding(overrides: Partial<Holding> = {}): Holding {
  return {
    ticker: "005930",
    name: "삼성전자",
    quantity: 10,
    sellable_quantity: 10,
    avg_price: 70000,
    purchase_amount: 700000,
    current_price: 72000,
    eval_amount: 720000,
    eval_profit_loss: 20000,
    eval_profit_rate: 2.86,
    nxt_tradable: null,
    krx_halted: null,
    excg_dvsn_cd: null,
    ...overrides,
  };
}

function setupBalance(holdings: Holding[]) {
  server.use(
    http.get("/api/balance", () =>
      HttpResponse.json(
        wrap({
          holdings,
          summary: {
            deposit: 10_000_000,
            stock_eval_amount: 720_000,
            total_eval_amount: 10_720_000,
            net_asset: 10_720_000,
            purchase_total: 700_000,
            eval_total: 720_000,
            profit_loss_total: 20_000,
          },
        })
      )
    ),
    // 자동매매 상태는 비활성으로 — selectedStrategy=all 분기에서 전략 매핑 없이 표시.
    http.get("/api/trading/status", () =>
      HttpResponse.json(
        wrap({
          running: false,
          env: "vts",
          positions: 0,
          pending_buys: 0,
          position_tickers: [],
          phase: "main_trading",
          scan: {
            filtered_tickers: [],
            filtered_count: 0,
            subscribed_tickers: [],
            subscribed_count: 0,
            last_scan_time: null,
            ticker_names: {},
            ticker_prices: {},
            ticker_market_info: {},
          },
          positions_detail: {},
          orders: {
            pending_buy_tickers: [],
            pending_buy_orders: {},
            fills: {},
            pending_cancels: [],
          },
          strategy: {
            buy_disabled: false,
            daily_realized_pnl: 0,
            total_investment: 0,
            buy_signals: [],
          },
          strategies: {},
        })
      )
    ),
  );
}

async function renderTable() {
  render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>
  );
  // 폴링 첫 응답 도착 대기 — 보유 종목명이 표시되면 ready.
  await screen.findByRole("table");
}

describe("BalanceTable — 거래시장 컬럼 (J1)", () => {
  it("KRX+NXT 배지: nxt_tradable=true && !krx_halted → emerald", async () => {
    setupBalance([
      makeHolding({
        ticker: "005930",
        name: "삼성전자",
        nxt_tradable: true,
        krx_halted: false,
        excg_dvsn_cd: "02",
      }),
    ]);
    await renderTable();

    const badge = await screen.findByTestId("market-badge-005930");
    expect(badge.textContent).toMatch(/KRX\+NXT/);
    expect(badge.className).toMatch(/emerald/);
  });

  it("NXT만 배지: nxt_tradable=true && krx_halted → amber", async () => {
    setupBalance([
      makeHolding({
        ticker: "012200",
        name: "계양전기",
        nxt_tradable: true,
        krx_halted: true,
        excg_dvsn_cd: "02",
      }),
    ]);
    await renderTable();

    const badge = await screen.findByTestId("market-badge-012200");
    expect(badge.textContent).toMatch(/NXT만/);
    expect(badge.className).toMatch(/amber/);
  });

  it("KRX 배지: nxt_tradable=false && !krx_halted → gray", async () => {
    setupBalance([
      makeHolding({
        ticker: "005380",
        name: "현대차",
        nxt_tradable: false,
        krx_halted: false,
        excg_dvsn_cd: "02",
      }),
    ]);
    await renderTable();

    const badge = await screen.findByTestId("market-badge-005380");
    // "KRX+NXT" 가 아닌 단독 "KRX" 라벨이어야 한다.
    expect(badge.textContent?.trim()).toBe("KRX");
    expect(badge.className).toMatch(/gray/);
  });

  it("정지 배지: krx_halted=true && nxt_tradable=false → red", async () => {
    setupBalance([
      makeHolding({
        ticker: "099999",
        name: "정지종목",
        nxt_tradable: false,
        krx_halted: true,
        excg_dvsn_cd: "02",
      }),
    ]);
    await renderTable();

    const badge = await screen.findByTestId("market-badge-099999");
    expect(badge.textContent).toMatch(/정지/);
    expect(badge.className).toMatch(/red/);
  });

  it("확인중 배지: 모든 필드 null → light-gray", async () => {
    setupBalance([
      makeHolding({
        ticker: "900110",
        name: "확인안된종목",
        nxt_tradable: null,
        krx_halted: null,
        excg_dvsn_cd: null,
      }),
    ]);
    await renderTable();

    const badge = await screen.findByTestId("market-badge-900110");
    expect(badge.textContent).toMatch(/확인중/);
    expect(badge.className).toMatch(/gray/);
  });

  it("거래시장 컬럼 헤더가 표시된다 (회귀 가드)", async () => {
    setupBalance([
      makeHolding({
        ticker: "005930",
        nxt_tradable: true,
        krx_halted: false,
        excg_dvsn_cd: "02",
      }),
    ]);
    await renderTable();

    const table = await screen.findByRole("table");
    const header = within(table).getByText("거래시장");
    expect(header.tagName).toBe("TH");
  });
});
