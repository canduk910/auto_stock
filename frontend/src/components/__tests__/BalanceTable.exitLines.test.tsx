/**
 * cycle339 — 잔고 표의 손절가·목표가 컬럼 (사용자 요청 2026-09-21).
 *
 * > "잔고내역에 각 종목별로 전략별 진입할 때 설정한 손절가와 목표가 정보가
 * > 추가로 있었으면 좋겠는데"
 *
 * 🔴 이 그물은 **값**을 잰다. 「컬럼이 있다」만 보면 손절가와 목표가를 맞바꾸거나,
 * 매수 트리거 가격을 목표가로 넣거나, 결측을 0 으로 그려도 전부 초록이다.
 * 운영자가 "여기까지는 버틴다" 를 판단하는 화면이라 **틀린 손절가는 없는 것보다
 * 나쁘다.**
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

describe("BalanceTable — 손절가 · 목표가", () => {
  it("두 컬럼이 현재가와 평가금액 사이에 선다", async () => {
    setup([makeHolding({ stop_price: 66500, stop_source: "effective" })]);
    await screen.findByText("삼성전자");

    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    const iCur = headers.indexOf("현재가");
    const iStop = headers.indexOf("손절가");
    const iTarget = headers.indexOf("목표가");
    const iEval = headers.indexOf("평가금액");
    expect(iCur).toBeGreaterThanOrEqual(0);
    expect(iStop).toBe(iCur + 1);
    expect(iTarget).toBe(iStop + 1);
    expect(iEval).toBe(iTarget + 1);
  });

  it("🔴 손절가와 목표가가 서로 다른 칸에 제 값으로 들어간다", async () => {
    setup([
      makeHolding({
        stop_price: 66500,
        stop_source: "effective",
        target_price: 84000,
        target_source: "measured_move",
      }),
    ]);
    await screen.findByText("삼성전자");
    // 두 수가 서로 달라야 맞바꿈을 잡는다.
    expect(screen.getByTestId("stop-price-005930")).toHaveTextContent("66,500");
    expect(screen.getByTestId("target-price-005930")).toHaveTextContent("84,000");
    expect(screen.getByTestId("stop-price-005930")).not.toHaveTextContent("84,000");
    expect(screen.getByTestId("target-price-005930")).not.toHaveTextContent("66,500");
  });

  it("🔴 값이 없으면 — 이지 0 이 아니다", async () => {
    setup([makeHolding({ stop_price: null, target_price: null })]);
    await screen.findByText("삼성전자");
    const stop = screen.getByTestId("stop-price-005930");
    const target = screen.getByTestId("target-price-005930");
    expect(stop).toHaveTextContent("—");
    expect(stop).not.toHaveTextContent("0");
    expect(target).toHaveTextContent("—");
    expect(target).not.toHaveTextContent("0");
  });

  it("필드가 아예 없는 옛 응답에도 깨지지 않는다", async () => {
    setup([makeHolding()]); // stop_price/target_price 키 자체가 없다
    await screen.findByText("삼성전자");
    expect(screen.getByTestId("stop-price-005930")).toHaveTextContent("—");
    expect(screen.getByTestId("target-price-005930")).toHaveTextContent("—");
  });

  it("🔴 근사 손절선은 「근사」로 표시하고 설명이 한계를 말한다", async () => {
    setup([makeHolding({ stop_price: 66500, stop_source: "hard_pct" })]);
    await screen.findByText("삼성전자");
    const cell = screen.getByTestId("stop-price-005930");
    expect(cell).toHaveTextContent("66,500");
    expect(cell).toHaveTextContent("근사");
    const title = cell.getAttribute("title") ?? "";
    expect(title).toContain("근사");
    // 실효 손절선과 섞이지 않도록 산식을 밝힌다.
    expect(title).toContain("하드손절");
  });

  it("실효 손절선에는 「근사」를 붙이지 않는다", async () => {
    setup([makeHolding({ stop_price: 66500, stop_source: "effective" })]);
    await screen.findByText("삼성전자");
    const cell = screen.getByTestId("stop-price-005930");
    expect(cell).toHaveTextContent("66,500");
    expect(cell).not.toHaveTextContent("근사");
    expect(cell.getAttribute("title") ?? "").toContain("실효 손절선");
  });

  it("🔴 설명이 「가격 무관 청산은 담기지 않는다」를 말한다", async () => {
    // 15:20 일괄매도·스테이지 종료·익일청산은 이 숫자에 없다 — 안 밝히면
    // 운영자가 그 가격까지 안 팔린다고 읽는다.
    setup([makeHolding({ stop_price: 66500, stop_source: "effective" })]);
    await screen.findByText("삼성전자");
    const title = screen.getByTestId("stop-price-005930").getAttribute("title") ?? "";
    expect(title).toContain("익일청산");
    // 🔴 「무조건 팔리는 것」과 「조건이 함께 붙는 것」을 **갈라서** 말해야 한다.
    //    20일 신고가 스윙의 2영업일 청산은 돌파고점 아래일 때만 발동한다 —
    //    뭉뚱그려 「가격 무관」이라 적으면 운영자가 위험을 과대평가한다.
    expect(title).toContain("보유일수만으로 팔리는 것");
    expect(title).toContain("다른 조건이 함께 붙는 것");
    expect(title).toContain("돌파고점 아래면");
    expect(title).toContain("이 가격에 닿기 전에 팔릴 수 있다");
  });

  it("목표가가 없는 전략은 설명이 그 사실을 말한다", async () => {
    setup([makeHolding({ target_price: null })]);
    await screen.findByText("삼성전자");
    const title = screen.getByTestId("target-price-005930").getAttribute("title") ?? "";
    expect(title).toContain("목표가를 쓰지 않는다");
  });

  it("측정 목표가는 부분 익절 트리거임을 밝힌다", async () => {
    setup([makeHolding({ target_price: 84000, target_source: "measured_move" })]);
    await screen.findByText("삼성전자");
    const title = screen.getByTestId("target-price-005930").getAttribute("title") ?? "";
    expect(title).toContain("부분 익절");
    expect(title).toContain("전량 청산선이 아니다");
  });

  it("🔴 엔진 정지 중은 「값 없음」과 다르게 보인다", async () => {
    // 엔진은 21:30 에 메모리 포지션을 비우고 07:45 에 되살린다. 그 사이의 `—` 를
    // 「손절선 없음」과 같은 모양으로 그리면 운영자가 아침에 "손절이 안 걸려 있다"
    // 로 읽는다 — 2026-09-21 23:57 배포 직후 보유 9건 전부 그렇게 보였다.
    setup([makeHolding({ stop_price: null, stop_source: "engine_idle" })]);
    await screen.findByText("삼성전자");
    const cell = screen.getByTestId("stop-price-005930");
    expect(cell).toHaveTextContent("⏸");
    expect(cell).not.toHaveTextContent("근사");
    const title = cell.getAttribute("title") ?? "";
    expect(title).toContain("매매 엔진 정지 중");
    expect(title).toContain("손절선이 없다는 뜻이 아니다");
  });

  it("엔진 정지와 판정 불가는 설명이 다르다", async () => {
    setup([makeHolding({ stop_price: null, stop_source: null })]);
    await screen.findByText("삼성전자");
    const title = screen.getByTestId("stop-price-005930").getAttribute("title") ?? "";
    expect(title).toContain("판정할 수 없다");
    expect(title).not.toContain("엔진 정지");
  });

  it("🔴 모드가 갈리는 전략은 숫자를 지어내지 않는다", async () => {
    // 롱테일은 당일/상한가 모드에서 손절 기준이 다르다(-5 / -3.5). 하나로 접으면
    // 한쪽이 틀리고, 운영자가 1.5%p 여유를 더 있다고 오판한다.
    setup([makeHolding({ stop_price: null, stop_source: "mode_dependent" })]);
    await screen.findByText("삼성전자");
    const cell = screen.getByTestId("stop-price-005930");
    expect(cell).toHaveTextContent("—");
    expect(cell).toHaveTextContent("모드별");
    expect(cell).not.toHaveTextContent("⏸");
    const title = cell.getAttribute("title") ?? "";
    expect(title).toContain("보유 중 손절 기준이 바뀐다");
  });

  it("🔴 이미 도달한 목표가는 그 사실을 표시한다", async () => {
    setup([makeHolding({ target_price: 84000, target_source: "measured_move_hit" })]);
    await screen.findByText("삼성전자");
    const cell = screen.getByTestId("target-price-005930");
    expect(cell).toHaveTextContent("84,000");
    expect(cell).toHaveTextContent("도달");
    expect(cell.getAttribute("title") ?? "").toContain("이미 도달");
  });

  it("아직 도달하지 않은 목표가에는 「도달」을 붙이지 않는다", async () => {
    setup([makeHolding({ target_price: 84000, target_source: "measured_move" })]);
    await screen.findByText("삼성전자");
    const cell = screen.getByTestId("target-price-005930");
    expect(cell).toHaveTextContent("84,000");
    expect(cell).not.toHaveTextContent("도달");
  });

  it("보유 0 행의 colSpan 이 컬럼 수와 맞는다", async () => {
    setup([]);
    const empty = await screen.findByText("보유 종목이 없습니다.");
    const headers = screen.getAllByRole("columnheader").length;
    expect(Number(empty.getAttribute("colSpan"))).toBe(headers);
  });
});
