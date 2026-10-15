/**
 * cycle459 — 대시보드 계좌 요약에 「D+2 예수금」 칸 (사용자 결정 2026-10-15).
 *
 * 자리 = 「예수금」 과 「총 평가금」 사이. 값 = `/api/balance` summary.deposit_d2
 * (KIS TTTC8434R output2 `prvs_rcdl_excc_amt`, 같은 응답 — 잔고 폴링과 같이 갱신).
 * null(모름)·칸 없음(구 서버) = 「—」(0원으로 접지 않는다).
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import { TradingStatusProvider } from "../../contexts/TradingStatusContext";
import BalanceTable from "../BalanceTable";

// 실제 라우트 본문 모양 — deposit_d1/d2 는 정수 원 또는 null.
const BASE_SUMMARY = {
  deposit: 346_455,
  deposit_d1: 296_455,
  deposit_d2: 1_046_455,
  stock_eval_amount: 720_000,
  total_eval_amount: 1_766_455,
  net_asset: 1_766_455,
  purchase_total: 700_000,
  eval_total: 720_000,
  profit_loss_total: 20_000,
};

function setupBalance(summary: Record<string, unknown>) {
  server.use(
    http.get("/api/balance", () =>
      HttpResponse.json(wrap({ holdings: [], summary })),
    ),
  );
}

async function renderTable() {
  render(
    <TestProviders>
      <TradingStatusProvider>
        <BalanceTable selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  );
  return screen.findByTestId("balance-summary-deposit-d2");
}

describe("BalanceTable — D+2 예수금 칸 (cycle459)", () => {
  it("값이 있으면 천 단위 콤마 + 원", async () => {
    setupBalance(BASE_SUMMARY);
    const card = await renderTable();
    expect(card).toHaveTextContent("D+2 예수금");
    expect(card).toHaveTextContent("1,046,455원");
  });

  it("예수금과 총 평가금 사이에 놓인다", async () => {
    setupBalance(BASE_SUMMARY);
    const card = await renderTable();
    const cards = Array.from(card.parentElement!.children);
    const labels = cards.map((c) => c.querySelector("p")?.textContent);
    expect(labels.slice(0, 3)).toEqual(["예수금", "D+2 예수금", "총 평가금"]);
  });

  it("툴팁이 가수도정산금액 뜻을 말한다", async () => {
    setupBalance(BASE_SUMMARY);
    const card = await renderTable();
    expect(card.getAttribute("title")).toBe(
      "D+2 결제 후 예수금(가수도정산금액) — 매도대금이 들어오고 매수대금이 빠진 뒤 금액",
    );
  });

  it("null 이면 「—」 (0원 아님)", async () => {
    setupBalance({ ...BASE_SUMMARY, deposit_d2: null });
    const card = await renderTable();
    expect(card).toHaveTextContent("—");
    expect(card).not.toHaveTextContent("0원");
  });

  it("칸이 없는 구 서버 응답도 「—」", async () => {
    const { deposit_d1: _d1, deposit_d2: _d2, ...old } = BASE_SUMMARY;
    void _d1;
    void _d2;
    setupBalance(old);
    const card = await renderTable();
    expect(card).toHaveTextContent("—");
  });

  it("숫자 문자열이 와도 방어 변환해 보인다", async () => {
    setupBalance({ ...BASE_SUMMARY, deposit_d2: "1046455" });
    const card = await renderTable();
    expect(card).toHaveTextContent("1,046,455원");
  });
});
