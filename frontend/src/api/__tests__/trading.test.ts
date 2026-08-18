import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import axios from "axios";

import {
  getTradingStatus,
  startTrading,
  stopTrading,
  updateStrategyWeights,
} from "../trading";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("trading API wrapper", () => {
  it("getTradingStatus unwraps ApiResponse 의 data 필드", async () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(
          wrap({ running: true, env: "vts", board: "main", strategies: {} }),
        ),
      ),
    );
    const status = await getTradingStatus();
    expect(status.running).toBe(true);
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

// 2026-08-18 — 비중 단위 계약(비율 0.0~1.0) 422 경로 회귀 가드.
// 백엔드 validator 가 던지는 422 는 axios 가 throw 하므로 2xx 본문 해석 경로로는
// 안 잡힌다. 미처리 시 운영자에게 "Request failed with status code 422" 만 보인다.
describe("updateStrategyWeights — 422 검증 응답 처리", () => {
  it("422 배열 detail 에서 한글 메시지를 뽑고 pydantic 영문 접두사는 제거한다", async () => {
    server.use(
      http.put("/api/strategies/weights", () =>
        HttpResponse.json(
          {
            detail: [
              {
                msg: "Value error, 비중은 비율(0.0~1.0)이어야 합니다: momentum=40.0",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await expect(
      updateStrategyWeights({ momentum: 40.0 }),
    ).rejects.toThrow("비중은 비율(0.0~1.0)이어야 합니다: momentum=40.0");

    const err = await updateStrategyWeights({ momentum: 40.0 }).catch(
      (e: unknown) => e as Error,
    );
    expect(err.message).not.toContain("Value error");
  });

  it("422 문자열 detail 은 그대로 전파한다", async () => {
    server.use(
      http.put("/api/strategies/weights", () =>
        HttpResponse.json({ detail: "비중 형식 오류" }, { status: 422 }),
      ),
    );
    await expect(updateStrategyWeights({ momentum: 40.0 })).rejects.toThrow(
      "비중 형식 오류",
    );
  });

  it("422 인데 detail 을 못 읽으면 한글 폴백 메시지를 던진다", async () => {
    server.use(
      http.put("/api/strategies/weights", () =>
        HttpResponse.json({}, { status: 422 }),
      ),
    );
    const err = await updateStrategyWeights({ momentum: 40.0 }).catch(
      (e: unknown) => e as Error,
    );
    expect(err.message).toContain("비중 형식이 올바르지 않습니다");
    expect(err.message).not.toContain("status code 422");
  });

  it("2xx + success=false 는 재포장하지 않고 백엔드 message 를 그대로 전파한다", async () => {
    server.use(
      http.put("/api/strategies/weights", () =>
        HttpResponse.json({
          success: false,
          data: null,
          message: "비중 합이 100%를 초과합니다 (현재 298.0%)",
        }),
      ),
    );
    await expect(updateStrategyWeights({ momentum: 2.98 })).rejects.toThrow(
      "비중 합이 100%를 초과합니다 (현재 298.0%)",
    );
  });

  it("422 외 에러는 한글 치환 없이 axios 에러 그대로 전파한다", async () => {
    server.use(
      http.put("/api/strategies/weights", () =>
        HttpResponse.json({ detail: "internal" }, { status: 500 }),
      ),
    );
    const err = await updateStrategyWeights({ momentum: 0.4 }).catch(
      (e: unknown) => e as Error,
    );
    expect(axios.isAxiosError(err)).toBe(true);
    expect((err as import("axios").AxiosError).response?.status).toBe(500);
    expect(err.message).not.toContain("비중 형식이 올바르지 않습니다");
  });
});
