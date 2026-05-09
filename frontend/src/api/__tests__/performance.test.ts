import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { getPerformanceSummary } from "../performance";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("performance API wrapper", () => {
  it("getPerformanceSummary unwraps and returns data", async () => {
    server.use(
      http.get("/api/performance/summary", () =>
        HttpResponse.json(
          wrap({
            total_days: 5,
            total_profit_rate: 1.23,
            avg_daily_profit_rate: 0.5,
            latest_asset: 10_500_000,
            strategy: "total",
          }),
        ),
      ),
    );
    const data = await getPerformanceSummary();
    expect(data.total_days).toBe(5);
    expect(data.total_profit_rate).toBeCloseTo(1.23);
  });

  it("strategy 인자가 query param 으로 전달된다", async () => {
    let capturedQuery = "";
    server.use(
      http.get("/api/performance/summary", ({ request }) => {
        capturedQuery = new URL(request.url).searchParams.toString();
        return HttpResponse.json(
          wrap({
            total_days: 1,
            total_profit_rate: 0,
            avg_daily_profit_rate: 0,
            latest_asset: 0,
            strategy: "momentum",
          }),
        );
      }),
    );
    await getPerformanceSummary("momentum");
    expect(capturedQuery).toContain("strategy=momentum");
  });
});
