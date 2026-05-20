/**
 * 사이클 6 (2026-05-17) — `components/SystemLogsTab.tsx`.
 *
 * 요구 행위:
 *  1. 기본 from_date/to_date 가 오늘(KST) 로 설정되어 API 호출 인자 포함.
 *  2. 날짜 변경 + 적용 클릭 → API 재호출.
 *  3. 레벨 선택 → API 호출 인자에 level 포함 + page 1 리셋.
 *  4. 페이징 "다음" 클릭 → page=2 로 API 재호출.
 *  5. total_pages=1 일 때 "다음" disabled.
 *  6. 빈 결과 "로그가 없습니다." 표시.
 *  7. timestamp 가 KST 시각으로 표시 (Asia/Seoul, UTC 23시 → KST 8시).
 */

import { describe, expect, it, beforeAll, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import SystemLogsTab from "../SystemLogsTab";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

// KST 오늘 (en-CA 포맷 = YYYY-MM-DD)
function todayKST(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

describe("SystemLogsTab", () => {
  it("기본 from_date/to_date 가 KST 오늘로 세팅 + API 호출", async () => {
    const today = todayKST();
    let lastUrl: URL | null = null;
    server.use(
      http.get("/api/logs", ({ request }) => {
        lastUrl = new URL(request.url);
        return HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 }));
      }),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(lastUrl).not.toBeNull();
    });
    expect(lastUrl!.searchParams.get("from_date")).toBe(today);
    expect(lastUrl!.searchParams.get("to_date")).toBe(today);
    expect(lastUrl!.searchParams.get("page")).toBe("1");

    // 입력값도 today
    expect(
      (screen.getByTestId("system-logs-from-date") as HTMLInputElement).value,
    ).toBe(today);
    expect(
      (screen.getByTestId("system-logs-to-date") as HTMLInputElement).value,
    ).toBe(today);
  });

  it("from_date 변경 후 적용 → 새 from_date 로 API 재호출 + page 리셋", async () => {
    const calls: string[] = [];
    server.use(
      http.get("/api/logs", ({ request }) => {
        const url = new URL(request.url);
        calls.push(url.searchParams.get("from_date") ?? "");
        return HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 }));
      }),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));

    fireEvent.change(screen.getByTestId("system-logs-from-date"), {
      target: { value: "2026-05-10" },
    });
    fireEvent.click(screen.getByTestId("system-logs-apply"));

    await waitFor(() => {
      expect(calls).toContain("2026-05-10");
    });
  });

  it("level=ERROR 선택 → API 인자에 level=ERROR 전달", async () => {
    const calls: string[] = [];
    server.use(
      http.get("/api/logs", ({ request }) => {
        const url = new URL(request.url);
        calls.push(url.searchParams.get("level") ?? "");
        return HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 }));
      }),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    fireEvent.click(await screen.findByTestId("system-logs-level-ERROR"));

    await waitFor(() => {
      expect(calls).toContain("ERROR");
    });
  });

  it("페이징 다음 버튼 → page=2 API 호출", async () => {
    const pages: string[] = [];
    server.use(
      http.get("/api/logs", ({ request }) => {
        const url = new URL(request.url);
        pages.push(url.searchParams.get("page") ?? "");
        return HttpResponse.json(
          wrap({
            items: [
              { id: 1, timestamp: "2026-05-17T01:00:00Z", log_level: "INFO", message: "m" },
            ],
            total: 120,
            total_pages: 3,
          }),
        );
      }),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    await waitFor(() => expect(pages.length).toBeGreaterThan(0));

    const next = await screen.findByTestId("system-logs-next");
    expect(next).not.toBeDisabled();
    fireEvent.click(next);

    await waitFor(() => {
      expect(pages).toContain("2");
    });
  });

  it("total_pages=1 이면 '다음' 버튼 disabled", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(
          wrap({
            items: [
              { id: 1, timestamp: "2026-05-17T01:00:00Z", log_level: "INFO", message: "ok" },
            ],
            total: 1,
            total_pages: 1,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    const next = await screen.findByTestId("system-logs-next");
    await waitFor(() => {
      expect(next).toBeDisabled();
    });
    expect(screen.getByTestId("system-logs-prev")).toBeDisabled();
  });

  it("빈 결과 → '로그가 없습니다.' 표시", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getByText("로그가 없습니다.")).toBeInTheDocument();
    });
  });

  it("from_date > to_date 시 422 가드 메시지 + API 호출 차단", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
    );
    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    fireEvent.change(screen.getByTestId("system-logs-from-date"), {
      target: { value: "2026-05-17" },
    });
    fireEvent.change(screen.getByTestId("system-logs-to-date"), {
      target: { value: "2026-05-15" },
    });
    fireEvent.click(screen.getByTestId("system-logs-apply"));

    await waitFor(() => {
      expect(screen.getByTestId("system-logs-date-error")).toBeInTheDocument();
    });
  });
});

describe("SystemLogsTab — 검색 박스 (사이클 6 통합, 2026-05-20)", () => {
  it("검색어 입력 + 검색 버튼 → /api/logs/search 호출 + q 인자 전달", async () => {
    const searchCalls: { q: string; level: string | null }[] = [];
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
      http.get("/api/logs/search", ({ request }) => {
        const url = new URL(request.url);
        searchCalls.push({
          q: url.searchParams.get("q") ?? "",
          level: url.searchParams.get("level"),
        });
        return HttpResponse.json(
          wrap({
            logs: [
              {
                id: 1,
                timestamp: "2026-05-20T01:00:00Z",
                log_level: "ERROR",
                message: "OPSP0002 폭주",
              },
            ],
            total: 1,
            has_more: false,
          }),
        );
      }),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    const input = await screen.findByTestId("system-logs-search-input");
    fireEvent.change(input, { target: { value: "OPSP" } });
    fireEvent.click(screen.getByTestId("system-logs-search-button"));

    await waitFor(() => {
      expect(searchCalls.length).toBeGreaterThan(0);
    });
    expect(searchCalls[searchCalls.length - 1].q).toBe("OPSP");
  });

  it("검색 결과 0건 → '검색 결과가 없습니다.' 메시지", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
      http.get("/api/logs/search", () =>
        HttpResponse.json(wrap({ logs: [], total: 0, has_more: false })),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    const input = await screen.findByTestId("system-logs-search-input");
    fireEvent.change(input, { target: { value: "nonexistent_xyz" } });
    fireEvent.click(screen.getByTestId("system-logs-search-button"));

    await waitFor(() => {
      expect(screen.getByText("검색 결과가 없습니다.")).toBeInTheDocument();
    });
  });

  it("검색 결과 행 렌더 + 검색 모드 진입 (초기화 버튼 노출)", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
      http.get("/api/logs/search", () =>
        HttpResponse.json(
          wrap({
            logs: [
              {
                id: 99,
                timestamp: "2026-05-20T01:00:00Z",
                log_level: "ERROR",
                message: "ERROR_KEY 결함",
              },
            ],
            total: 1,
            has_more: false,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    const input = await screen.findByTestId("system-logs-search-input");
    fireEvent.change(input, { target: { value: "ERROR_KEY" } });
    fireEvent.click(screen.getByTestId("system-logs-search-button"));

    await waitFor(() => {
      const body = screen.getByTestId("system-logs-body");
      expect(body.textContent).toMatch(/ERROR_KEY/);
    });

    // 초기화 버튼 노출
    expect(screen.getByTestId("system-logs-search-clear")).toBeInTheDocument();
  });

  it("초기화 버튼 클릭 → 검색 모드 종료 + /api/logs 페이징 모드 복귀", async () => {
    const logsCalls: string[] = [];
    server.use(
      http.get("/api/logs", ({ request }) => {
        logsCalls.push(new URL(request.url).search);
        return HttpResponse.json(
          wrap({
            items: [
              {
                id: 1,
                timestamp: "2026-05-20T01:00:00Z",
                log_level: "INFO",
                message: "normal log",
              },
            ],
            total: 1,
            total_pages: 1,
          }),
        );
      }),
      http.get("/api/logs/search", () =>
        HttpResponse.json(
          wrap({
            logs: [
              {
                id: 99,
                timestamp: "2026-05-20T01:00:00Z",
                log_level: "ERROR",
                message: "ERROR_KEY",
              },
            ],
            total: 1,
            has_more: false,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    // 1) 검색 모드 진입
    const input = await screen.findByTestId("system-logs-search-input");
    fireEvent.change(input, { target: { value: "ERROR_KEY" } });
    fireEvent.click(screen.getByTestId("system-logs-search-button"));

    const clear = await screen.findByTestId("system-logs-search-clear");

    // 검색 모드에서는 /api/logs 호출 안 함 (페이징 비활성)
    const callsBeforeClear = logsCalls.length;

    // 2) 초기화 클릭
    fireEvent.click(clear);

    // 검색 input 비워짐
    await waitFor(() => {
      expect(
        (screen.getByTestId("system-logs-search-input") as HTMLInputElement).value,
      ).toBe("");
    });

    // /api/logs 재호출 (페이징 모드 복귀)
    await waitFor(() => {
      expect(logsCalls.length).toBeGreaterThan(callsBeforeClear);
    });
  });

  it("has_more=true → '키워드를 좁혀주세요' 안내", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
      http.get("/api/logs/search", () =>
        HttpResponse.json(
          wrap({
            logs: Array.from({ length: 200 }, (_, i) => ({
              id: i,
              timestamp: "2026-05-20T01:00:00Z",
              log_level: "INFO",
              message: `msg_${i}`,
            })),
            total: 500,
            has_more: true,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    const input = await screen.findByTestId("system-logs-search-input");
    fireEvent.change(input, { target: { value: "msg" } });
    fireEvent.click(screen.getByTestId("system-logs-search-button"));

    await waitFor(() => {
      expect(screen.getByTestId("system-logs-search-has-more")).toBeInTheDocument();
    });
  });
});

describe("SystemLogsTab — KST 시각 변환 (L3 컨벤션)", () => {
  const ORIG_TZ = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = "UTC";
  });
  afterAll(() => {
    process.env.TZ = ORIG_TZ;
  });

  it("UTC ISO 입력을 Asia/Seoul 시각으로 표시", async () => {
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(
          wrap({
            items: [
              {
                id: 1,
                // 2026-05-11 23:05:47 UTC = 2026-05-12 08:05:47 KST
                timestamp: "2026-05-11T23:05:47Z",
                log_level: "INFO",
                message: "test message",
              },
            ],
            total: 1,
            total_pages: 1,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <SystemLogsTab />
      </TestProviders>,
    );

    const body = await screen.findByTestId("system-logs-body");
    await waitFor(() => {
      // KST 8시(또는 08시) 가 보여야 함. UTC 23시 표시 차단.
      expect(body.textContent).not.toMatch(/23[:시]/);
      expect(body.textContent).toMatch(/8[:시 ]/);
      expect(body.textContent).toMatch(/2026/);
    });
  });
});
