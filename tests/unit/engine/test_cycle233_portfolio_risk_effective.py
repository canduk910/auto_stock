"""cycle233 M1 — portfolio_risk 척도 병기 + over_cap 관측 (R1·R2·R3).

자문 정본 = `_workspace/domain_consult/cycle232_risk_control_review.md` §2.4-β(척도 병기)
+ §2.5 부속안 ③(1주 폴백 초과 관측). 계약:

- `compute_portfolio_risk_snapshot(..., stop_price_of=None)` — **미전달 시 기존 반환
  byte 동일**(사이클 H 계약 보존). 전달 시 per-position 실효 리스크
  `qty × max(0, buy − stop)` 를 병기(`effective` 키 + by_strategy 확장).
- stop ≥ buy → 실효 0 (확정 이익이 타 종목 실노출을 상쇄하면 캡이 무력화 — kojiro
  `_open_risk_won` 음수 금지 규약과 동일 축).
- 콜러블 예외/None/≤0 → **프록시 폴백**(관측이 죽으면 안 된다) + coverage 미계상.
- `compute_over_cap_positions` — 별도 함수(스냅샷 계약 무접촉). 000815 실측 수치
  (405,500×1주 / budget 789,130 / ratio 0.166 → over_ratio 3.10)가 결정적 입력.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.engine.portfolio_risk import compute_portfolio_risk_snapshot


def _strat(sid: str, positions: dict, *, params: dict | None = None,
           total_investment: int = 0):
    return SimpleNamespace(
        strategy_id=sid,
        config=SimpleNamespace(params=params or {}),
        state=SimpleNamespace(positions=positions, total_investment=total_investment),
    )


def _pos(buy_price: int, quantity: int):
    return SimpleNamespace(buy_price=buy_price, quantity=quantity)


class TestR1ContractPreserved:
    """R1 — stop_price_of 미전달 = 기존 스냅샷 계약 byte 동일."""

    def test_no_effective_key_when_not_provided(self):
        strategies = [_strat("kojiro", {"000815": _pos(405_500, 1)},
                             params={"hard_stop_pct": -8.0})]
        snap = compute_portfolio_risk_snapshot(
            strategies, net_asset=2_630_434,
            hard_stop_pcts={"kojiro": -8.0}, sector_of={},
        )
        assert "effective" not in snap
        assert "risk_effective_won" not in snap["by_strategy"]["kojiro"]
        # 기존 키 집합 보존 (사이클 H 계약)
        assert set(snap.keys()) == {
            "total_notional_won", "total_open_risk_won", "open_risk_pct_of_net",
            "concurrent_positions", "by_strategy", "by_sector", "top_sector",
        }


class TestR2EffectiveMeasure:
    """R2 — 척도 병기: 실효 손절선 기반 리스크."""

    def test_effective_uses_injected_stop(self):
        # buy 50,000 × 10주, stop 48,000 → 실효 = 10 × 2,000 = 20,000
        strategies = [_strat("kojiro", {"A": _pos(50_000, 10)})]
        snap = compute_portfolio_risk_snapshot(
            strategies, net_asset=2_630_434,
            hard_stop_pcts={"kojiro": -8.0}, sector_of={},
            stop_price_of=lambda sid, t: 48_000,
        )
        assert snap["effective"]["total_open_risk_effective_won"] == 20_000
        assert snap["by_strategy"]["kojiro"]["risk_effective_won"] == 20_000
        # 프록시는 기존 산식 그대로 병존 (대체 금지 — 자문 반례 2)
        assert snap["total_open_risk_won"] == int(50_000 * 10 * 8.0 / 100)

    def test_stop_above_buy_counts_zero(self):
        """샹들리에가 매수가 위로 올라간 포지션 → proxy > 0 ∧ effective == 0."""
        strategies = [_strat("kojiro", {"A": _pos(48_200, 5)})]
        snap = compute_portfolio_risk_snapshot(
            strategies, net_asset=2_630_434,
            hard_stop_pcts={"kojiro": -8.0}, sector_of={},
            stop_price_of=lambda sid, t: 51_203,  # 실측 슈프리마 사례
        )
        assert snap["total_open_risk_won"] > 0
        assert snap["effective"]["total_open_risk_effective_won"] == 0

    def test_callable_failure_falls_back_to_proxy(self):
        """콜러블 예외 → 프록시 폴백 + coverage 미계상 (fail-open)."""
        def _boom(sid, t):
            raise RuntimeError("live 상태 없음")

        strategies = [_strat("kojiro", {"A": _pos(50_000, 10)})]
        snap = compute_portfolio_risk_snapshot(
            strategies, net_asset=2_630_434,
            hard_stop_pcts={"kojiro": -8.0}, sector_of={},
            stop_price_of=_boom,
        )
        proxy = int(50_000 * 10 * 8.0 / 100)
        assert snap["effective"]["total_open_risk_effective_won"] == proxy
        cov = snap["effective"]["coverage"]
        assert cov["effective_positions"] == 0
        assert cov["total_positions"] == 1

    def test_none_stop_falls_back_to_proxy(self):
        strategies = [_strat("bfb", {"B": _pos(10_000, 3)})]
        snap = compute_portfolio_risk_snapshot(
            strategies, net_asset=1_000_000,
            hard_stop_pcts={"bfb": -5.0}, sector_of={},
            stop_price_of=lambda sid, t: None,
        )
        assert snap["effective"]["total_open_risk_effective_won"] == int(10_000 * 3 * 5.0 / 100)
        assert snap["effective"]["coverage"]["effective_positions"] == 0

    def test_effective_ratio_and_pct(self):
        strategies = [_strat("kojiro", {"A": _pos(50_000, 10)})]
        snap = compute_portfolio_risk_snapshot(
            strategies, net_asset=1_000_000,
            hard_stop_pcts={"kojiro": -8.0}, sector_of={},
            stop_price_of=lambda sid, t: 48_000,
        )
        eff = snap["effective"]
        assert eff["open_risk_effective_pct_of_net"] == pytest.approx(2.0)
        # effective_ratio = 20,000 / 40,000 = 0.5
        assert eff["effective_ratio"] == pytest.approx(0.5)


class TestR3OverCap:
    """R3 — 1주 폴백 notional 초과 관측 (자문 §정정 1 실측 수치)."""

    def test_detects_000815_case(self):
        from src.engine.portfolio_risk import compute_over_cap_positions
        strategies = [_strat(
            "kojiro", {"000815": _pos(405_500, 1)},
            params={"position_ratio": 0.166}, total_investment=789_130,
        )]
        out = compute_over_cap_positions(strategies)
        assert len(out) == 1
        row = out[0]
        assert row["strategy_id"] == "kojiro"
        assert row["ticker"] == "000815"
        assert row["cap_won"] == int(789_130 * 0.166)  # 130,995
        assert row["over_ratio"] == pytest.approx(3.10, abs=0.01)

    def test_skips_when_ratio_missing_or_within_cap(self):
        from src.engine.portfolio_risk import compute_over_cap_positions
        strategies = [
            _strat("momentum", {"C": _pos(405_500, 1)}, params={},
                   total_investment=789_130),                      # ratio 결측 → skip
            _strat("donchian_swing", {"D": _pos(100_000, 1)},
                   params={"position_ratio": 0.2},
                   total_investment=789_130),                      # 100,000 ≤ 157,826 → 미검출
        ]
        assert compute_over_cap_positions(strategies) == []
