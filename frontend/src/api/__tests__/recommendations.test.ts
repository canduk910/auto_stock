import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import {
  listRecommendations,
  applyRecommendation,
  rejectRecommendation,
} from "../recommendations";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

const mockRec = {
  id: "R1",
  strategy_id: "momentum",
  current_params: { position_ratio: 0.25 },
  recommended_params: { position_ratio: 0.3 },
  applied_params: {},
  status: "pending",
  target_date: "2026-05-08",
  reasoning: "..",
  metrics: {},
  created_at: "2026-05-08T16:00:00+09:00",
};

describe("recommendations API wrapper", () => {
  it("list 는 배열을 그대로 반환", async () => {
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(wrap([mockRec])),
      ),
    );
    const list = await listRecommendations();
    expect(list).toHaveLength(1);
    expect(list[0].strategy_id).toBe("momentum");
  });

  it("apply 는 keys body 를 전달하고 success/message 반환", async () => {
    let capturedBody: any = null;
    server.use(
      http.post("/api/recommendations/:id/apply", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          success: true, data: null, message: "1개 적용 완료",
        });
      }),
    );
    const r = await applyRecommendation("R1", ["position_ratio"]);
    expect(capturedBody.keys).toEqual(["position_ratio"]);
    expect(r.success).toBe(true);
    expect(r.message).toContain("적용");
  });

  it("reject 는 success/message 반환", async () => {
    server.use(
      http.post("/api/recommendations/:id/reject", () =>
        HttpResponse.json({ success: true, data: null, message: "추천 거절 완료" }),
      ),
    );
    const r = await rejectRecommendation("R1");
    expect(r.success).toBe(true);
    expect(r.message).toContain("거절");
  });
});
