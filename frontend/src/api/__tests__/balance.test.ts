import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { getBalance } from "../balance";
import { failed, wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("balance API wrapper", () => {
  it("/api/balance 응답을 그대로 반환한다", async () => {
    server.use(
      http.get("/api/balance", () =>
        HttpResponse.json(
          wrap({
            holdings: [
              {
                ticker: "005930",
                name: "삼성전자",
                quantity: 10,
                buy_price: 70000,
                current_price: 72000,
                eval_amount: 720000,
                profit_loss: 20000,
                profit_rate: 2.86,
              },
            ],
            summary: {
              deposit: 10_000_000,
              stock_eval_amount: 720_000,
              total_eval_amount: 10_720_000,
              net_asset: 10_720_000,
              purchase_total: 700_000,
              eval_total: 720_000,
              profit_loss_total: 20_000,
            },
          }),
        ),
      ),
    );
    const data = await getBalance();
    expect(data.holdings).toHaveLength(1);
    expect(data.summary.deposit).toBe(10_000_000);
    expect(data.summary.net_asset).toBe(10_720_000);
  });

  it("cycle406 L2 — success=false 응답이면 조용히 null 을 돌려주지 않고 던진다", async () => {
    // 백엔드가 get_balance() 소진 예외를 200 + success=false 로 흡수하게 됐다
    // (src/routes/balance.py cycle406). 여기서 그대로 data.data(=null)를 돌려주면
    // BalanceTable 의 `if (!data) return null` 이 아무 설명 없이 빈 화면을 그린다 —
    // react-query 의 기존 isError 경로("잔고를 불러올 수 없습니다.")를 타도록 던진다.
    server.use(
      http.get("/api/balance", () => HttpResponse.json(failed("잔고 조회 실패: 소진"))),
    );
    await expect(getBalance()).rejects.toThrow("잔고 조회 실패: 소진");
  });
});
