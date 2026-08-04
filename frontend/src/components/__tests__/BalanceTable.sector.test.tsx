/**
 * BalanceTable — 섹터 컬럼 (2026-08-04, 사용자 요청).
 *
 * 대시보드 하단 포지션 현황에서 **종목명과 거래시장 사이**에 섹터를 노출한다.
 * 데이터는 `/api/balance` Holding 의 `sector` 필드 — 백엔드가 이미 조회한
 * stock_master basics 를 재사용해 산출한다(추가 DB 호출 0).
 *   1) basics raw `bstp_kor_isnm` (KIS 업종 한글명)
 *   2) 부재 시 `_kojiro_sector_key(master_raw)` (KRX 산업지수 플래그 → 업종코드)
 *   3) 최종 `미분류-{ticker}`
 *
 * UI 규약: 값이 없으면(`null`/`undefined`/빈문자) `-` 로 표시해 열이 밀리지 않게 한다.
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

describe("BalanceTable 섹터 컬럼", () => {
  it("섹터 헤더가 종목명과 거래시장 사이에 있다", async () => {
    setup([makeHolding({ sector: "전기·전자" })]);
    await screen.findByText("삼성전자");

    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    const iName = headers.indexOf("종목명");
    const iSector = headers.indexOf("섹터");
    const iMarket = headers.indexOf("거래시장");
    expect(iName).toBeGreaterThanOrEqual(0);
    expect(iSector).toBe(iName + 1);
    expect(iMarket).toBe(iSector + 1);
  });

  it("섹터 값을 행에 표시한다", async () => {
    setup([makeHolding({ sector: "전기·전자" })]);
    expect(await screen.findByTestId("sector-005930")).toHaveTextContent("전기·전자");
  });

  it("섹터가 없으면 '-' 로 표시한다", async () => {
    setup([makeHolding({ sector: null })]);
    expect(await screen.findByTestId("sector-005930")).toHaveTextContent("-");
  });

  it("미분류 접두 값도 그대로 노출한다", async () => {
    setup([makeHolding({ ticker: "999999", name: "테스트", sector: "미분류-999999" })]);
    expect(await screen.findByTestId("sector-999999")).toHaveTextContent("미분류-999999");
  });

  it("보유 0건 안내 행이 전체 열을 덮는다", async () => {
    setup([]);
    const cell = await screen.findByText("보유 종목이 없습니다.");
    const headerCount = screen.getAllByRole("columnheader").length;
    expect(Number(cell.getAttribute("colspan"))).toBe(headerCount);
  });
});
