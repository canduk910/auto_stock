"""cycle233 M7 — 전략 4종 `get_effective_stop_price` read-only 미러 (R10).

계약: 각 전략의 check_exit 가격선들과 **동일 산식·동일 상태 소스**의 max 를
반환한다(가격 무관 청산 — 시간·stage3·measured-move — 은 모델 제외, kojiro
`_position_stop_price` docstring 선례). **read-only** — 호출이 래치 set·
`_stop_floor`·`_partial_exit`·로그 어느 것도 변경/발화하지 않는다.
미구현 전략(StrategyBase 기본)은 None = 프록시 폴백 신호.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.engine.strategy_base import StrategyConfig


def _pos(buy_price: int, quantity: int = 1, high: int = 0):
    return SimpleNamespace(
        buy_price=buy_price, quantity=quantity,
        high_since_buy=high if high else buy_price,
        buy_date=None,
    )


class TestBaseDefault:
    def test_base_returns_none(self):
        from src.engine.strategy_base import StrategyBase

        class _S(StrategyBase):
            async def prepare(self):
                return None

            def check_buy_signal(self, *a):
                return None

            def check_exit_signal(self, *a):
                return None

            def calc_buy_quantity(self, current_price, ticker=None):
                return 0

        s = _S(StrategyConfig(strategy_id="x", name="x", params={}))
        assert s.get_effective_stop_price("A") is None


class TestKojiroMirror:
    def _make(self):
        from src.engine.strategies.kojiro import KojiroStrategy
        return KojiroStrategy(StrategyConfig(
            strategy_id="kojiro", name="k", params={"exchange": "KRX"}))

    def test_delegates_to_position_stop_price(self):
        s = self._make()
        pos = _pos(50_000, 3, high=55_000)
        s.state.positions["A"] = pos
        s._position_atr["A"] = 1_000.0
        expected = s._position_stop_price("A", pos)
        assert s.get_effective_stop_price("A") == expected
        assert expected > 0

    def test_no_position_returns_none(self):
        s = self._make()
        assert s.get_effective_stop_price("ZZZ") is None


class TestDonchianMirror:
    def _make(self):
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy
        return DonchianSwingStrategy(StrategyConfig(
            strategy_id="donchian_swing", name="d", params={"exchange": "KRX"}))

    def test_turtle_lines_max(self):
        """2ATR base(48,000) vs backstop(45,500) vs 샹들리에(58,000) → 58,000."""
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=60_000)
        s._entry_atr["A"] = 1_000.0
        got = s.get_effective_stop_price("A")
        assert got == 58_000

    def test_turtle_without_high_uses_base_stop(self):
        s = self._make()
        pos = _pos(50_000, 1)
        pos.high_since_buy = 0
        s.state.positions["A"] = pos
        s._entry_atr["A"] = 1_000.0
        # base 48,000 vs backstop 50,000×0.91=45,500 → 48,000
        assert s.get_effective_stop_price("A") == 48_000

    def test_unstamped_uses_fixed_pct(self):
        s = self._make()
        pos = _pos(50_000, 1)
        pos.high_since_buy = 0
        s.state.positions["A"] = pos
        # 미스탬프 → stop_loss_rate -7% → 46,500
        assert s.get_effective_stop_price("A") == 46_500

    def test_breakeven_promote_mirrored_without_log(self, caplog):
        """고점 ≥ buy+1.5×ATR → base 가 buy 로 승격. 미러는 로그 무발화."""
        import logging
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=52_000)
        s._entry_atr["A"] = 1_000.0
        with caplog.at_level(logging.INFO):
            got = s.get_effective_stop_price("A")
        # 승격 base 50,000 vs 샹들리에 52,000−2,000=50,000 → 50,000
        assert got == 50_000
        assert not [r for r in caplog.records
                    if "donchian_breakeven_promote" in r.message]


class TestVcpMirror:
    def _make(self):
        from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
        return VcpBreakoutStrategy(StrategyConfig(
            strategy_id="vcp_breakout", name="v", params={"exchange": "KRX"}))

    def test_structure_and_trailing_max(self):
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=52_000)
        s._position_setup["A"] = {"base_low": 45_000, "atr14": 1_000, "ema50": 47_000}
        # 선: pct −7% 46,500 / base_low 45,000 / 샹들리에 50,000 / ema50 47,000
        assert s.get_effective_stop_price("A") == 50_000

    def test_read_only_no_latch_mutation(self):
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=60_000)
        s._position_setup["A"] = {"base_low": 45_000, "atr14": 1_000, "ema50": 0}
        before = set(s._breakeven_latched)
        s.get_effective_stop_price("A")
        assert set(s._breakeven_latched) == before

    def test_mirror_does_not_consume_setup_conflict_marker(self, caplog):
        """F1 — 미러는 `[setup_structure_conflict]` 를 발화/소비하지 않는다.

        watcher(5분 주기)가 cap 을 선소비하면 cycle228-B 마커의 "청산 평가 문맥"
        D+1 귀인이 무너진다 — observe=False 경로가 그 보호다. 청산 경로(observe
        기본값)는 여전히 발화해야 한다(cap 이 소비되지 않았음의 실증).
        """
        import logging
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=52_000)
        s._position_setup["A"] = {"base_low": 45_000}
        s._candidates["A"] = {"base_low": 46_000, "atr14": 1_000, "ema50": 0}  # 충돌
        with caplog.at_level(logging.INFO):
            s.get_effective_stop_price("A")
        assert not [r for r in caplog.records
                    if "setup_structure_conflict" in r.message], "미러가 마커 발화"
        caplog.clear()
        with caplog.at_level(logging.INFO):
            s.check_exit_signal("A", 51_000, 51_000)
        assert [r for r in caplog.records
                if "setup_structure_conflict" in r.message], (
            "청산 경로 미발화 — 미러가 cap 을 선소비했다는 뜻"
        )


class TestBfbMirror:
    def _make(self):
        from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
        return BullFlagBreakoutStrategy(StrategyConfig(
            strategy_id="bull_flag_breakout", name="b", params={"exchange": "KRX"}))

    def test_structure_and_trailing_max(self):
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=52_000)
        s._position_setup["A"] = {"flag_low": 47_000, "atr14": 1_000}
        # 선: pct −5% 47,500 / flag_low 47,000 / 샹들리에 50,000 → 50,000
        assert s.get_effective_stop_price("A") == 50_000

    def test_measured_move_excluded(self):
        """measured-move(익절 상방 타겟)는 손절선 모델에서 제외 — 상한 오염 금지."""
        s = self._make()
        s.state.positions["A"] = _pos(50_000, 1, high=50_500)
        s._position_setup["A"] = {
            "flag_low": 47_000, "atr14": 1_000,
            "pole_start": 40_000, "pole_high": 49_000, "flag_high": 49_500,
        }
        got = s.get_effective_stop_price("A")
        # measured_target = 49,500+9,000 = 58,500 이 절대 답이 되면 안 된다
        assert got is not None and got < 58_500
