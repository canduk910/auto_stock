/**
 * Phase 4 (2026-05-16) — Recommendations 페이지의 백테스트 비교 카드.
 *
 * 요구 행위:
 * A. backtest_summary == null → 미실행 안내 메시지 ("백테스트 미실행") + placeholder 렌더
 * B. 자기 전략 current==null AND recommended==null (b)폴백 → "로컬 어댑터 대기" 안내
 * C. 자기 전략 정상 데이터 → 8 메트릭 좌(current)/우(recommended) 비교 + diff 컬러 칩
 * D. 이익색(PROFIT_HEX)/손실색(LOSS_HEX), max_drawdown 부호 역전
 * E. peer 전략 데이터 — 5개 peer mini 비교 (자율 결정: 표시함)
 * F. 숫자 포맷 — 수익률 소수 2자리 + %, sharpe/sortino 소수 2자리, total_trades 콤마
 * G. data-testid 일관성
 *
 * cycle261 (2026-09-05) — DK Stock 디자인시스템 v2 전환에 맞춰 색 단언을 hex 리터럴에서
 * `utils/pnlColor` 상수 import 로 바꿨다. 팔레트가 다시 바뀌어도 이 파일은 무수정이고,
 * 두 정본(index.css @theme ↔ pnlColor.ts) 드리프트는 designSystem.v2 가드가 따로 잡는다.
 */

import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import BacktestComparisonCard from "../BacktestComparisonCard";
import type { BacktestSummary } from "../../../types/backtest";
import { PROFIT_HEX, LOSS_HEX, NEUTRAL_HEX } from "../../../utils/pnlColor";

/**
 * inline style 의 color 단언용 패턴.
 * jsdom 은 `style` 속성을 `color: rgb(r, g, b)` 로 직렬화하므로 hex/rgb 양쪽을 허용한다.
 */
function colorPattern(hex: string): RegExp {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return new RegExp(`${hex}|rgb\\(\\s*${r},\\s*${g},\\s*${b}\\s*\\)`, "i");
}

const PROFIT_STYLE = colorPattern(PROFIT_HEX);
const LOSS_STYLE = colorPattern(LOSS_HEX);
const NEUTRAL_STYLE = colorPattern(NEUTRAL_HEX);

// Phase 6.1 (2026-05-17) — 외부 MCP 실측 검증으로 MDD 양수(절대값) 컨벤션 확정.
// 픽스처는 양수형 MDD 를 사용한다 (예: 8.5 — 절대값). 추천 MDD 가 더 크면 손실 악화.
function makeMetrics(over: Partial<Record<string, number>> = {}) {
  return {
    total_return_pct: 12.34,
    cagr: 8.1,
    sharpe_ratio: 1.23,
    sortino_ratio: 1.5,
    max_drawdown: 8.5,
    win_rate: 0.55,
    profit_factor: 1.8,
    total_trades: 42,
    ...over,
  };
}

function makeSummary(over: Partial<BacktestSummary> = {}): BacktestSummary {
  return {
    current: {
      momentum: makeMetrics(),
      volatility_breakout: makeMetrics({ total_return_pct: 5.0 }),
      donchian_swing: makeMetrics({ total_return_pct: 3.0 }),
      long_tail_volatility: null,
      bull_flag_breakout: null,
      vcp_breakout: null,
    },
    recommended: {
      momentum: makeMetrics({
        total_return_pct: 15.0,
        sharpe_ratio: 1.4,
        max_drawdown: 10.0, // 양수 컨벤션 — 추천 MDD 가 더 크면 손실 악화 (10.0 > 8.5)
        win_rate: 0.6,
        profit_factor: 2.0,
        total_trades: 50,
      }),
      volatility_breakout: makeMetrics({ total_return_pct: 4.0 }),
      donchian_swing: makeMetrics({ total_return_pct: 4.0 }),
      long_tail_volatility: null,
      bull_flag_breakout: null,
      vcp_breakout: null,
    },
    diff: {
      momentum: {
        total_return_pct: 2.66,
        sharpe_ratio: 0.17,
        max_drawdown: 1.5, // 양수 diff — 추천 MDD 더 큼 → 손실 악화 → 파랑
        win_rate: 0.05,
        profit_factor: 0.2,
        total_trades: 8,
      },
      volatility_breakout: { total_return_pct: -1.0 },
      donchian_swing: { total_return_pct: 1.0 },
    },
    ...over,
  };
}

describe("BacktestComparisonCard — Phase 4", () => {
  it("A: backtest_summary == null 이면 미실행 안내 placeholder 렌더", () => {
    render(<BacktestComparisonCard strategyId="momentum" summary={null} />);

    const card = screen.getByTestId("backtest-comparison-card-momentum");
    expect(card).toBeInTheDocument();
    expect(card.textContent).toMatch(/백테스트 미실행|진행중|아직/);
  });

  it("B: 자기 전략 current/recommended 모두 null 이면 (b)폴백 안내", () => {
    const summary: BacktestSummary = {
      current: { long_tail_volatility: null },
      recommended: { long_tail_volatility: null },
      diff: {},
    };
    render(
      <BacktestComparisonCard strategyId="long_tail_volatility" summary={summary} />,
    );

    const card = screen.getByTestId("backtest-comparison-card-long_tail_volatility");
    expect(card.textContent).toMatch(/로컬|폴백|어댑터|대기/);
  });

  it("C: 자기 전략 정상 데이터 → 8 메트릭 좌/우 + diff 칩 렌더", () => {
    const summary = makeSummary();
    render(<BacktestComparisonCard strategyId="momentum" summary={summary} />);

    const card = screen.getByTestId("backtest-comparison-card-momentum");
    // 좌(current) 12.34% 노출
    expect(within(card).getByTestId("metric-current-total_return_pct").textContent).toMatch(/12\.34/);
    // 우(recommended) 15.00% 노출
    expect(within(card).getByTestId("metric-recommended-total_return_pct").textContent).toMatch(/15\.00/);
    // diff +2.66
    const diffEl = within(card).getByTestId("metric-diff-total_return_pct");
    expect(diffEl.textContent).toMatch(/2\.66/);

    // 8개 메트릭 모두 렌더
    for (const key of [
      "total_return_pct",
      "cagr",
      "sharpe_ratio",
      "sortino_ratio",
      "max_drawdown",
      "win_rate",
      "profit_factor",
      "total_trades",
    ]) {
      expect(within(card).getByTestId(`metric-current-${key}`)).toBeInTheDocument();
      expect(within(card).getByTestId(`metric-recommended-${key}`)).toBeInTheDocument();
    }
  });

  it("D: diff 양수 = 이익색(PROFIT_HEX), 음수 = 손실색(LOSS_HEX). max_drawdown 부호 역전 (양수 컨벤션).", () => {
    const summary = makeSummary();
    render(<BacktestComparisonCard strategyId="momentum" summary={summary} />);
    const card = screen.getByTestId("backtest-comparison-card-momentum");

    // total_return_pct diff +2.66 → 이익색 빨강
    const totalReturnDiff = within(card).getByTestId("metric-diff-total_return_pct");
    expect(totalReturnDiff.getAttribute("style") ?? "").toMatch(PROFIT_STYLE);

    // sharpe_ratio diff +0.17 → 이익색
    const sharpeDiff = within(card).getByTestId("metric-diff-sharpe_ratio");
    expect(sharpeDiff.getAttribute("style") ?? "").toMatch(PROFIT_STYLE);

    // Phase 6.1 양수 컨벤션: max_drawdown diff +1.5 → 추천 MDD 더 큼 → 손실 증가 → 손실색 파랑 (signInverted)
    const mddDiff = within(card).getByTestId("metric-diff-max_drawdown");
    expect(mddDiff.getAttribute("style") ?? "").toMatch(LOSS_STYLE);
  });

  it("D-2: 일반 메트릭 음수 diff → 손실색 파랑", () => {
    // 자기 전략 momentum 의 win_rate diff 가 음수 케이스 테스트
    const negSummary = makeSummary({
      diff: {
        momentum: { win_rate: -0.05, total_return_pct: -3.0 },
      },
    });
    render(<BacktestComparisonCard strategyId="momentum" summary={negSummary} />);
    const card = screen.getByTestId("backtest-comparison-card-momentum");

    const winRateDiff = within(card).getByTestId("metric-diff-win_rate");
    expect(winRateDiff.getAttribute("style") ?? "").toMatch(LOSS_STYLE);

    const totalDiff = within(card).getByTestId("metric-diff-total_return_pct");
    expect(totalDiff.getAttribute("style") ?? "").toMatch(LOSS_STYLE);
  });

  // cycle261 — 보합(diff 0)도 pnlColor 정본에 위임한다. 카드가 자기만의 중립 hex 를
  // 들고 있으면 팔레트를 갈아끼울 때 이 한 칸만 구 팔레트로 남는다(D 케이스는 못 잡는 사각).
  it("D-3: diff 0 → 보합색(NEUTRAL_HEX)", () => {
    const zeroSummary = makeSummary({
      diff: { momentum: { total_return_pct: 0 } },
    });
    render(<BacktestComparisonCard strategyId="momentum" summary={zeroSummary} />);
    const card = screen.getByTestId("backtest-comparison-card-momentum");

    const zeroDiff = within(card).getByTestId("metric-diff-total_return_pct");
    expect(zeroDiff.getAttribute("style") ?? "").toMatch(NEUTRAL_STYLE);
  });

  it("E: peer 전략 mini 비교 표시 — 5개 peer 모두 카드 렌더", () => {
    const summary = makeSummary();
    render(<BacktestComparisonCard strategyId="momentum" summary={summary} />);

    // peer 전략들이 mini 카드에 노출
    expect(screen.getByTestId("backtest-peer-volatility_breakout")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-peer-donchian_swing")).toBeInTheDocument();
    // (b) 폴백 전략들도 5개 peer 안에 포함 (skipped 상태)
    expect(screen.getByTestId("backtest-peer-long_tail_volatility")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-peer-bull_flag_breakout")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-peer-vcp_breakout")).toBeInTheDocument();

    // 자기 전략은 peer 자리에 미노출
    expect(screen.queryByTestId("backtest-peer-momentum")).not.toBeInTheDocument();
  });

  it("F: 숫자 포맷 — 수익률 소수 2자리 + %, sharpe 소수 2자리, total_trades 콤마 천 단위", () => {
    const summary = makeSummary({
      current: {
        momentum: makeMetrics({ total_trades: 1234 }),
      },
      recommended: {
        momentum: makeMetrics({ total_trades: 2500 }),
      },
      diff: {
        momentum: { total_trades: 1266 },
      },
    });
    render(<BacktestComparisonCard strategyId="momentum" summary={summary} />);
    const card = screen.getByTestId("backtest-comparison-card-momentum");

    // total_return_pct 12.34% 형식
    expect(within(card).getByTestId("metric-current-total_return_pct").textContent).toContain("12.34%");
    // sharpe_ratio 1.23 형식 (% 없음)
    expect(within(card).getByTestId("metric-current-sharpe_ratio").textContent).toContain("1.23");
    expect(within(card).getByTestId("metric-current-sharpe_ratio").textContent).not.toContain("%");
    // total_trades 1,234 콤마
    expect(within(card).getByTestId("metric-current-total_trades").textContent).toContain("1,234");
    expect(within(card).getByTestId("metric-recommended-total_trades").textContent).toContain("2,500");
  });

  // Phase 6.1 (2026-05-17) — MDD 양수(절대값) 컨벤션 회귀 가드.
  // 외부 MCP 실측 검증 결과 max_drawdown 은 양수형 절대값(예: 16.1) 으로 반환됨.
  // 추천 MDD 가 현재보다 크면(절대값 증가 = 손실 더 깊어짐) diff 양수 → 손실 악화 → 파랑.
  // signInverted=true 가 spec 에 적용되어 있어야 통과.
  it("H: MDD 양수 컨벤션 — recommended MDD(15.0) 가 current(10.0) 보다 크면 손실 악화 = 파랑", () => {
    const summary: BacktestSummary = {
      current: {
        momentum: makeMetrics({ max_drawdown: 10.0 }),
      },
      recommended: {
        momentum: makeMetrics({ max_drawdown: 15.0 }),
      },
      diff: {
        // diff = recommended - current = +5.0 → 양수
        // 양수 컨벤션에선 MDD 값 증가 = 손실 절대값 증가 = 악화 → 파랑
        momentum: { max_drawdown: 5.0 },
      },
    };
    render(<BacktestComparisonCard strategyId="momentum" summary={summary} />);
    const card = screen.getByTestId("backtest-comparison-card-momentum");

    const mddDiff = within(card).getByTestId("metric-diff-max_drawdown");
    expect(mddDiff.getAttribute("style") ?? "").toMatch(LOSS_STYLE);
    // 표시 텍스트는 양수 그대로 (+5.00%)
    expect(mddDiff.textContent).toMatch(/\+5\.00/);

    // 반대 케이스: 추천 MDD 가 더 작으면(11.0 → 8.0) diff 음수(-3.0) → 손실 감소 = 개선 = 빨강
    const summary2: BacktestSummary = {
      current: {
        momentum: makeMetrics({ max_drawdown: 11.0 }),
      },
      recommended: {
        momentum: makeMetrics({ max_drawdown: 8.0 }),
      },
      diff: {
        momentum: { max_drawdown: -3.0 },
      },
    };
    const { rerender: _r } = render(
      <BacktestComparisonCard strategyId="momentum" summary={summary2} />,
      { container: document.body.appendChild(document.createElement("div")) },
    );
    void _r;
    const cards = screen.getAllByTestId("backtest-comparison-card-momentum");
    const lastCard = cards[cards.length - 1];
    const mddDiff2 = within(lastCard).getByTestId("metric-diff-max_drawdown");
    expect(mddDiff2.getAttribute("style") ?? "").toMatch(PROFIT_STYLE);
  });

  it("G: data-testid 일관성 — backtest-comparison-card-{strategy_id} 루트 + 메트릭 testid", () => {
    const summary = makeSummary();
    const { rerender } = render(
      <BacktestComparisonCard strategyId="momentum" summary={summary} />,
    );
    expect(screen.getByTestId("backtest-comparison-card-momentum")).toBeInTheDocument();

    rerender(
      <BacktestComparisonCard strategyId="volatility_breakout" summary={summary} />,
    );
    expect(screen.getByTestId("backtest-comparison-card-volatility_breakout")).toBeInTheDocument();
  });
});
