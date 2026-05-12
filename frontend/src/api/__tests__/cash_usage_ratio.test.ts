/**
 * J3 Red (2026-05-12) — `cash_usage_ratio` API wrapper.
 *
 * GET `/api/strategies/system/cash-usage-ratio` → `{ratio: number}` (default 1.0)
 * PUT `/api/strategies/system/cash-usage-ratio` body `{ratio: 0.8}` → `{ratio: 0.8}`
 *
 * 보정: 0.83 → 백엔드가 0.85 로 보정해 응답. 응답 ratio 를 그대로 반환해야 한다.
 */

import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { getCashUsageRatio, updateCashUsageRatio } from "../trading";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("cash_usage_ratio API wrapper", () => {
  it("getCashUsageRatio 는 ratio 만 반환 (기본 1.0)", async () => {
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 1.0 })),
      ),
    );
    const ratio = await getCashUsageRatio();
    expect(ratio).toBe(1.0);
  });

  it("getCashUsageRatio 는 서버가 보낸 0.8 을 그대로 반환", async () => {
    server.use(
      http.get("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 0.8 })),
      ),
    );
    const ratio = await getCashUsageRatio();
    expect(ratio).toBe(0.8);
  });

  it("updateCashUsageRatio 는 body 에 ratio 를 보내고 응답 ratio 를 반환", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.put("/api/strategies/system/cash-usage-ratio", async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(wrap({ ratio: 0.8 }));
      }),
    );
    const ratio = await updateCashUsageRatio(0.8);
    expect(ratio).toBe(0.8);
    expect(receivedBody).toEqual({ ratio: 0.8 });
  });

  it("updateCashUsageRatio 는 서버 보정값(0.83→0.85) 을 반환", async () => {
    server.use(
      http.put("/api/strategies/system/cash-usage-ratio", () =>
        HttpResponse.json(wrap({ ratio: 0.85 })),
      ),
    );
    const ratio = await updateCashUsageRatio(0.83);
    expect(ratio).toBe(0.85);
  });
});
