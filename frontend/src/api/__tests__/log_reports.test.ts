import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { listLogReports, getLogReport, runLogReport } from "../log_reports";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

const mockReport = {
  id: 1,
  target_date: "2026-05-08",
  summary: "정상",
  findings: [],
  metrics: {},
  model: "gpt-4",
  created_at: "2026-05-08T20:15:00+09:00",
};

describe("log_reports API wrapper", () => {
  it("listLogReports 는 days 쿼리를 전달", async () => {
    let captured = "";
    server.use(
      http.get("/api/log-reports", ({ request }) => {
        captured = new URL(request.url).searchParams.toString();
        return HttpResponse.json(wrap([mockReport]));
      }),
    );
    const list = await listLogReports(7);
    expect(captured).toContain("days=7");
    expect(list).toHaveLength(1);
  });

  it("getLogReport(date) 가 존재하지 않으면 null", async () => {
    server.use(
      http.get("/api/log-reports/:d", () =>
        HttpResponse.json({ success: false, data: null, message: "리포트가 없습니다" }),
      ),
    );
    const r = await getLogReport("2026-05-08");
    expect(r).toBeNull();
  });

  it("getLogReport 는 응답을 unwrap", async () => {
    server.use(
      http.get("/api/log-reports/:d", () =>
        HttpResponse.json(wrap(mockReport)),
      ),
    );
    const r = await getLogReport("2026-05-08");
    expect(r?.id).toBe(1);
  });

  it("runLogReport 는 success/data 반환", async () => {
    server.use(
      http.post("/api/log-reports/run", () =>
        HttpResponse.json(wrap(mockReport)),
      ),
    );
    const r = await runLogReport();
    expect(r.success).toBe(true);
  });
});
