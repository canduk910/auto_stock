/**
 * 사이클 6 (2026-05-17) — `pages/Logs.tsx` 탭 컨테이너.
 *
 * 두 탭(시스템 로그 / 일일 로그 분석) + URL 쿼리(`?tab=system|daily-report`) 동기화.
 * 기본 `system`, 알 수 없는 값은 `system` 로 fallback.
 */

import { describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Logs from "../Logs";
import { TestProviders } from "../../test/providers";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

describe("Logs — 탭 컨테이너", () => {
  it("기본 진입 시 시스템 로그 탭이 활성", async () => {
    render(
      <TestProviders initialRoute="/logs">
        <Logs />
      </TestProviders>,
    );

    const sysTab = await screen.findByTestId("logs-tab-system");
    expect(sysTab.getAttribute("aria-selected")).toBe("true");
    // 시스템 로그 본문 노출
    expect(screen.getByTestId("system-logs-body")).toBeInTheDocument();
  });

  it("?tab=daily-report 진입 시 일일 로그 분석 탭이 활성", async () => {
    render(
      <TestProviders initialRoute="/logs?tab=daily-report">
        <Logs />
      </TestProviders>,
    );

    const dailyTab = await screen.findByTestId("logs-tab-daily-report");
    expect(dailyTab.getAttribute("aria-selected")).toBe("true");
    // 일일 분석 h1 노출 (DailyReportTab)
    await waitFor(() => {
      expect(screen.getByText(/일일 로그 분석 리포트/)).toBeInTheDocument()
    });
    // 시스템 로그 본문 미노출
    expect(screen.queryByTestId("system-logs-body")).not.toBeInTheDocument();
  });

  it("시스템 로그 탭 → 일일 로그 분석 탭 클릭 시 활성 전환", async () => {
    render(
      <TestProviders initialRoute="/logs">
        <Logs />
      </TestProviders>,
    );

    const dailyTab = await screen.findByTestId("logs-tab-daily-report");
    fireEvent.click(dailyTab);

    await waitFor(() => {
      expect(dailyTab.getAttribute("aria-selected")).toBe("true");
    });
    expect(screen.queryByTestId("system-logs-body")).not.toBeInTheDocument();
  });

  it("알 수 없는 ?tab 값은 system 으로 fallback", async () => {
    render(
      <TestProviders initialRoute="/logs?tab=garbage">
        <Logs />
      </TestProviders>,
    );

    const sysTab = await screen.findByTestId("logs-tab-system");
    expect(sysTab.getAttribute("aria-selected")).toBe("true");
  });

  it("두 탭 모두 화면에 존재한다 (탭 헤더 visibility)", async () => {
    // /logs 진입 후 시스템 로그 API 가 호출되어도 무해
    server.use(
      http.get("/api/logs", () =>
        HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 })),
      ),
    );
    render(
      <TestProviders initialRoute="/logs">
        <Logs />
      </TestProviders>,
    );

    expect(await screen.findByTestId("logs-tab-system")).toBeInTheDocument();
    expect(screen.getByTestId("logs-tab-daily-report")).toBeInTheDocument();
  });
});
