import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { getTradingStatus, startTrading, stopTrading } from "../trading";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("trading API wrapper", () => {
  it("getTradingStatus unwraps ApiResponse 의 data 필드", async () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(
          wrap({ is_running: true, env: "vts", board: "main", strategies: {} }),
        ),
      ),
    );
    const status = await getTradingStatus();
    expect(status.is_running).toBe(true);
    expect(status.env).toBe("vts");
  });

  it("startTrading 은 success/message 만 반환한다", async () => {
    server.use(
      http.post("/api/trading/start", () =>
        HttpResponse.json({ success: true, data: null, message: "매매 시작" }),
      ),
    );
    const r = await startTrading();
    expect(r.success).toBe(true);
    expect(r.message).toBe("매매 시작");
  });

  it("이미 실행 중일 때 startTrading 은 success=false 반환", async () => {
    server.use(
      http.post("/api/trading/start", () =>
        HttpResponse.json({ success: false, data: null, message: "이미 실행 중입니다" }),
      ),
    );
    const r = await startTrading();
    expect(r.success).toBe(false);
    expect(r.message).toContain("실행 중");
  });

  it("stopTrading 은 단순 envelope 만 추출", async () => {
    server.use(
      http.post("/api/trading/stop", () =>
        HttpResponse.json({ success: true, data: null, message: "매매 중지" }),
      ),
    );
    const r = await stopTrading();
    expect(r.success).toBe(true);
  });
});
