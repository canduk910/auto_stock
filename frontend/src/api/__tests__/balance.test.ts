import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { getBalance } from "../balance";
import { wrap } from "../../test/factories";
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
});
