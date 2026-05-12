/**
 * L3 — TradeHistoryGrid KST 시각 표시 일관성 (2026-05-12).
 *
 * 배경: 005930 보완 INSERT 결함 추적 결과, 백엔드는 `_to_kst` 헬퍼로 KST 변환을
 * 강제했지만 프론트엔드 `parseKST()` 는 실제론 `new Date(timestamp)` 후
 * `getFullYear()/getHours()` 를 브라우저 로컬 timezone 으로 추출 → 함수명과
 * 동작이 불일치. UTC ISO 가 트레이드 응답에 섞이면 환경별로 다른 시각 표시.
 *
 * 요구 행위:
 *  I. UTC ISO `2026-05-11T23:05:47Z` 입력 시 KST 환산으로 `26-05-12 / 08:05:47` 표시
 *     (브라우저 timezone 무관)
 *
 * 테스트 환경: vitest 의 jsdom 기본 timezone 은 호스트 OS 의존. 본 테스트는
 * `process.env.TZ='UTC'` 를 명시해 결정론적으로 동작 — KST 강제가 없으면
 * 브라우저는 UTC 시각 그대로 (`23:05:47`) 표시 → 단언 실패 → Red.
 */

import { describe, expect, it, beforeAll, afterAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "../../test/server";
import { wrap } from "../../test/factories";
import { TestProviders } from "../../test/providers";
import TradeHistoryGrid from "../TradeHistoryGrid";

// 결정론적 검증을 위해 테스트 프로세스 TZ 를 UTC 로 고정.
// `new Date(...)` + `d.getHours()` 등 로컬타임 추출은 이 TZ 따라가므로
// KST 강제 변환 없이는 UTC 시각이 그대로 표시된다.
const ORIG_TZ = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "UTC";
});
afterAll(() => {
  process.env.TZ = ORIG_TZ;
});

describe("TradeHistoryGrid — KST 시각 표시 (L3)", () => {
  it("UTC ISO 타임스탬프를 KST 로 환산해 주문일/주문시각 컬럼에 표시한다", async () => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json(
          wrap({
            trades: [
              {
                id: 1,
                // 2026-05-11 23:05:47 UTC = 2026-05-12 08:05:47 KST
                timestamp: "2026-05-11T23:05:47Z",
                ticker: "005930",
                ticker_name: "삼성전자",
                trade_type: "BUY",
                price: 70000,
                quantity: 10,
                profit_loss: 0,
                status: "COMPLETED",
                strategy: "momentum",
                order_no: "0000001111",
              },
            ],
            total: 1,
            total_pages: 1,
            page: 1,
            size: 20,
          }),
        ),
      ),
    );

    render(
      <TestProviders>
        <TradeHistoryGrid />
      </TestProviders>,
    );

    // 종목명이 렌더되면 그리드가 준비된 상태.
    await waitFor(() => expect(screen.getByText("삼성전자")).toBeInTheDocument());

    // KST 변환: 주문일 = 26-05-12, 주문시각 = 08:05:47
    expect(screen.getByText("26-05-12")).toBeInTheDocument();
    expect(screen.getByText("08:05:47")).toBeInTheDocument();
  });
});
