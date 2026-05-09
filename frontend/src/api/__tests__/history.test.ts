import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { getTradeHistory } from "../history";
import { wrap, makeTrade } from "../../test/factories";
import { server } from "../../test/server";

describe("history API wrapper", () => {
  it("페이징 응답을 그대로 반환", async () => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json(
          wrap({
            trades: [makeTrade({ id: 1 })],
            total: 1,
            page: 1,
            size: 20,
            total_pages: 1,
          }),
        ),
      ),
    );
    const data = await getTradeHistory({ page: 1, size: 20 });
    expect(data.trades).toHaveLength(1);
    expect(data.total).toBe(1);
    expect(data.total_pages).toBe(1);
  });

  it("page/size/strategy/ticker 가 query param 으로 전달된다", async () => {
    let capturedQuery = "";
    server.use(
      http.get("/api/history", ({ request }) => {
        capturedQuery = new URL(request.url).searchParams.toString();
        return HttpResponse.json(
          wrap({ trades: [], total: 0, page: 2, size: 50, total_pages: 0 }),
        );
      }),
    );
    await getTradeHistory({ page: 2, size: 50, strategy: "momentum", ticker: "005930" });
    expect(capturedQuery).toContain("page=2");
    expect(capturedQuery).toContain("size=50");
    expect(capturedQuery).toContain("strategy=momentum");
    expect(capturedQuery).toContain("ticker=005930");
  });
});
