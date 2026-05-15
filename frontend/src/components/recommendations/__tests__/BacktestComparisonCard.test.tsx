/**
 * Phase 4 (2026-05-16) — Recommendations 페이지의 백테스트 비교 카드.
 *
 * 요구 행위:
 * A. backtest_summary == null → 미실행 안내 메시지 ("백테스트 미실행") + placeholder 렌더
 * B. 자기 전략 current==null AND recommended==null (b)폴백 → "로컬 어댑터 대기" 안내
 * C. 자기 전략 정상 데이터 → 8 메트릭 좌(current)/우(recommended) 비교 + diff 컬러 칩
 * D. 이익색(#FF3333)/손실색(#3366FF), max_drawdown 부호 역전
 * E. peer 전략 데이터 — 5개 peer mini 비교 (자율 결정: 표시함)
 * F. 숫자 포맷 — 수익률 소수 2자리 + %, sharpe/sortino 소수 2자리, total_trades 콤마
 * G. data-testid 일관성
 */

import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import BacktestComparisonCard from "../BacktestComparisonCard";
import type { BacktestSummary } from "../../../types/backtest";

function makeMetrics(over: Partial<Record<string, number>> = {}) {
  return {
    total_return_pct: 12.34,
    cagr: 8.1,
    sharpe_ratio: 1.23,
    sortino_ratio: 1.5,
    max_drawdown: -8.5,
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
        max_drawdown: -10.0, // 더 큰 손실 (절대값 증가)
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
        max_drawdown: -1.5,
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

  it("D: diff 양수 = 이익색(#FF3333), 음수 = 손실색(#3366FF). max_drawdown 부호 역전.", () => {
    const summary = makeSummary();
    render(<BacktestComparisonCard strategyId="momentum" summary={summary} />);
    const card = screen.getByTestId("backtest-comparison-card-momentum");

    // total_return_pct diff +2.66 → 이익색 빨강
    const totalReturnDiff = within(card).getByTestId("metric-diff-total_return_pct");
    expect(totalReturnDiff.getAttribute("style") ?? "").toMatch(/#FF3333|rgb\(255,\s*51,\s*51\)/i);

    // sharpe_ratio diff +0.17 → 이익색
    const sharpeDiff = within(card).getByTestId("metric-diff-sharpe_ratio");
    expect(sharpeDiff.getAttribute("style") ?? "").toMatch(/#FF3333|rgb\(255,\s*51,\s*51\)/i);

    // max_drawdown diff -1.5 → 부호 역전 (실제로는 손실 증가) → 손실색 파랑
    const mddDiff = within(card).getByTestId("metric-diff-max_drawdown");
    expect(mddDiff.getAttribute("style") ?? "").toMatch(/#3366FF|rgb\(51,\s*102,\s*255\)/i);
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
    expect(winRateDiff.getAttribute("style") ?? "").toMatch(/#3366FF|rgb\(51,\s*102,\s*255\)/i);

    const totalDiff = within(card).getByTestId("metric-diff-total_return_pct");
    expect(totalDiff.getAttribute("style") ?? "").toMatch(/#3366FF|rgb\(51,\s*102,\s*255\)/i);
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
