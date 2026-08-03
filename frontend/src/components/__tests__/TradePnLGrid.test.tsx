/**
 * Red — TradePnLGrid 실현손익 요약 바 + 전략 필터 kojiro 추가.
 *
 * 명세: team-lead 메시지 「매매손익 (1) 실현손익 요약 바 + (2) kojiro 필터」.
 * Red 메모: `_workspace/red/pnl_summary_kojiro_filter.md`.
 *
 * 요구 행위:
 *  (a) `data.summary` 값으로 요약 바(testid `pnl-summary`) 렌더 —
 *      실현 합계·손익율·승/패/보합·승률 + 현재 전략 필터 라벨.
 *  (b) 실현손익 값(testid `pnl-summary-realized`)이 양수면 이익색(text-red)/
 *      음수면 손실색(text-blue) — 프로젝트 컨벤션(이익=빨강, 손실=파랑).
 *  (c) 전략 select 에 kojiro(고지로 대순환) option 존재.
 *  (d) 전략을 kojiro 로 변경 시 strategy=kojiro 로 재조회.
 *
 * RED: 현재 TradePnLGrid 는 요약 바 미렌더 + kojiro option 부재 →
 * findByTestId('pnl-summary') 타임아웃 / kojiro option 미존재로 전 케이스 실패.
 */

import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import TradePnLGrid from "../TradePnLGrid";

interface SummaryShape {
  realized_total_krw: number;
  realized_rate_pct: number;
  win_count: number;
  loss_count: number;
  even_count: number;
  win_rate_pct: number;
  closed_count: number;
}

const EMPTY_SUMMARY: SummaryShape = {
  realized_total_krw: 0,
  realized_rate_pct: 0,
  win_count: 0,
  loss_count: 0,
  even_count: 0,
  win_rate_pct: 0,
  closed_count: 0,
};

function pnlPayload(summary: SummaryShape, pairs: unknown[] = []) {
  return wrap({
    pairs,
    summary,
    page: 1,
    size: 30,
    total: pairs.length,
    total_pages: pairs.length > 0 ? 1 : 0,
  });
}

describe("TradePnLGrid — 실현손익 요약 바 + kojiro 필터 (Red)", () => {
  // ---------------------------------------------------------------------
  // (a) 요약 바가 summary 값을 렌더한다
  // ---------------------------------------------------------------------
  it("요약 바에 실현 합계·손익율·승/패/보합·승률·전략 라벨을 렌더한다", async () => {
    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(
          pnlPayload({
            realized_total_krw: 600,
            realized_rate_pct: 2.0,
            win_count: 3,
            loss_count: 1,
            even_count: 2,
            win_rate_pct: 75.0,
            closed_count: 6,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    const summary = await screen.findByTestId("pnl-summary");
    const text = summary.textContent ?? "";
    // 실현 합계
    expect(text).toMatch(/실현/);
    expect(text).toMatch(/600/);
    // 손익율
    expect(text).toMatch(/2(\.0)?\s*%/);
    // 승/패/보합
    expect(text).toMatch(/승\s*3/);
    expect(text).toMatch(/패\s*1/);
    expect(text).toMatch(/보합\s*2/);
    // 승률
    expect(text).toMatch(/승률\s*75/);
    // 현재 전략 필터 라벨 (기본 = 전체)
    expect(text).toMatch(/전체/);
  });

  // ---------------------------------------------------------------------
  // (b) 실현손익 부호별 색상 (이익=빨강 / 손실=파랑)
  // ---------------------------------------------------------------------
  it("실현손익이 양수면 이익색(text-red), 음수면 손실색(text-blue)으로 표시한다", async () => {
    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(
          pnlPayload({
            ...EMPTY_SUMMARY,
            realized_total_krw: 1500,
            realized_rate_pct: 5.0,
            win_count: 2,
            win_rate_pct: 100.0,
            closed_count: 2,
          }),
        ),
      ),
    );

    const { unmount } = render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    const pos = await screen.findByTestId("pnl-summary-realized");
    expect(pos.className).toMatch(/text-red/); // 이익 = 빨강
    unmount();

    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(
          pnlPayload({
            ...EMPTY_SUMMARY,
            realized_total_krw: -1500,
            realized_rate_pct: -5.0,
            loss_count: 2,
            win_rate_pct: 0.0,
            closed_count: 2,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    const neg = await screen.findByTestId("pnl-summary-realized");
    expect(neg.className).toMatch(/text-blue/); // 손실 = 파랑
  });

  // ---------------------------------------------------------------------
  // (c) 전략 select 에 kojiro(고지로 대순환) option 존재
  // ---------------------------------------------------------------------
  it("전략 필터에 kojiro(고지로 대순환) 옵션이 있다", async () => {
    server.use(
      http.get("/api/history/pnl", () =>
        HttpResponse.json(pnlPayload(EMPTY_SUMMARY)),
      ),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    // 로딩 종료 후 select 렌더 대기
    const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
    const option = within(select).getByRole("option", {
      name: "고지로 대순환",
    });
    expect(option).toHaveValue("kojiro");
  });

  // ---------------------------------------------------------------------
  // (d) 전략을 kojiro 로 바꾸면 strategy=kojiro 로 재조회한다
  // ---------------------------------------------------------------------
  it("전략을 kojiro 로 변경하면 strategy=kojiro 로 재조회한다", async () => {
    const seenStrategies: (string | null)[] = [];
    server.use(
      http.get("/api/history/pnl", ({ request }) => {
        seenStrategies.push(new URL(request.url).searchParams.get("strategy"));
        return HttpResponse.json(pnlPayload(EMPTY_SUMMARY));
      }),
    );

    render(
      <TestProviders>
        <TradePnLGrid />
      </TestProviders>,
    );

    // 요약 바가 뜨면 최초 조회 완료 상태
    await screen.findByTestId("pnl-summary");

    const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
    await userEvent.selectOptions(select, "kojiro");

    await waitFor(() =>
      expect(seenStrategies).toContain("kojiro"),
    );
  });
});
