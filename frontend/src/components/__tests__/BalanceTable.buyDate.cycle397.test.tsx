/**
 * cycle397 — 잔고 표의 매입일 컬럼 (사용자 요청 2026-10-02).
 *
 * > "잔고내역에 매입일을 표기하자. 혹시 여러날짜에 걸쳐 매수했다면(피라미딩으로
 * > 인해) 최초매입일로 표시."
 *
 * 🔴 「새 화면 칸은 값이 찍히는지까지 실측」 규약 — 컬럼이 있다 + 검사 초록만으로는
 * 값이 실제로 찍히는지 보증하지 못한다(2026-09-21 손절가 칸 재발 사고). 보유 11종목
 * 전부 칸이 비지 않는다를 직접 잰다.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
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

function setup(holdings: Holding[]) {
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
    )
  );
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>
  );
}

describe("BalanceTable — 매입일", () => {
  it("헤더가 거래시장 바로 다음에 선다", async () => {
    setup([makeHolding({ buy_date: "2026-09-20" })]);
    await screen.findByText("삼성전자");
    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    const iMarket = headers.indexOf("거래시장");
    const iBuyDate = headers.indexOf("매입일");
    expect(iMarket).toBeGreaterThanOrEqual(0);
    expect(iBuyDate).toBe(iMarket + 1);
  });

  it("매입일이 있으면 그대로 보인다", async () => {
    setup([makeHolding({ buy_date: "2026-09-20" })]);
    await screen.findByText("삼성전자");
    expect(screen.getByTestId("buy-date-005930")).toHaveTextContent("2026-09-20");
  });

  it("🔴 값이 없으면 — 이지 오늘 날짜로 채우지 않는다", async () => {
    setup([makeHolding({ buy_date: null })]);
    await screen.findByText("삼성전자");
    expect(screen.getByTestId("buy-date-005930")).toHaveTextContent("—");
  });

  it("필드가 아예 없는 옛 응답에도 깨지지 않는다", async () => {
    setup([makeHolding()]); // buy_date 키 자체가 없다
    await screen.findByText("삼성전자");
    expect(screen.getByTestId("buy-date-005930")).toHaveTextContent("—");
  });

  it("형식이 이상한 값(타임존 포함 등)은 지어내지 않고 — 로 그린다", async () => {
    setup([makeHolding({ buy_date: "2026-09-20T00:00:00Z" as unknown as string })]);
    await screen.findByText("삼성전자");
    expect(screen.getByTestId("buy-date-005930")).toHaveTextContent("—");
  });

  it("🔴 보유 11종목 전부 매입일 칸이 비지 않는다", async () => {
    const holdings = Array.from({ length: 11 }, (_, i) =>
      makeHolding({
        ticker: `${100000 + i}`,
        name: `종목${i}`,
        buy_date: `2026-09-${String(10 + i).padStart(2, "0")}`,
      })
    );
    setup(holdings);
    await screen.findByText("종목0");
    for (let i = 0; i < 11; i++) {
      const cell = screen.getByTestId(`buy-date-${100000 + i}`);
      expect(cell).not.toHaveTextContent("—");
      expect(cell).toHaveTextContent(`2026-09-${String(10 + i).padStart(2, "0")}`);
    }
  });
});
