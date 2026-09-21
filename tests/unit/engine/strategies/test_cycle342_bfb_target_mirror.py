"""cycle342 — BFB 측정 목표가 read-only 미러.

## 왜 미러가 필요했나

cycle339 초판은 잔고 화면의 목표가를 `get_targets_status()` 에서 읽었다. 그 함수는
`self._candidates.items()` 를 순회하는데(`bull_flag_breakout.py:798`) `_candidates` 는
`prepare()` 마다 와이프되고 **보유 종목은 셋업이 무너져 후보 자격을 잃는 것이 정상**이다.

운영 DB 실측(`strategy_funnel_snapshots` `step_no=99`, 6영업일) — 보유 2종목
(003160 매수 09-17 · 036800 매수 09-14)이 **하루도** 후보에 없었다. 즉 그 경로로는
화면이 **영구히 빈 칸**이었다.

반면 엔진의 `check_exit_signal` §3 은 `_effective_setup(ticker)` 로 **`_position_setup`
stamp 폴백**을 타서 살아 있다. 같은 파일 안에서 손절가(`flag_low`)는 stamp 를 타는데
목표가만 안 타던 **비대칭**이 결함의 모양이었다.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit


def _pos(buy: int, qty: int = 1, high: int = 0) -> Position:
    p = Position(
        ticker="A", buy_price=buy, quantity=qty, order_no="o",
        strategy_id="bull_flag_breakout", buy_date=date(2026, 9, 14),
    )
    p.high_since_buy = high or buy
    return p


def _make():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    return BullFlagBreakoutStrategy(StrategyConfig(
        strategy_id="bull_flag_breakout", name="b", params={"exchange": "KRX"}))


# ── 값 ────────────────────────────────────────────────────────────────────


def test_target_is_flag_high_plus_pole_width():
    """산식은 `check_exit_signal` §3 과 **같아야** 한다 — 갈리면 화면이 거짓말한다."""
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    s._position_setup["A"] = {
        "flag_high": 55_000, "pole_high": 54_000, "pole_start": 46_000,
    }
    target, hit = s.get_effective_target_price("A")
    assert target == 55_000 + (54_000 - 46_000) == 63_000
    assert hit is False


def test_target_comes_from_the_stamp_not_from_candidates():
    """🔴 **이 케이스가 결함의 핵심이다.**

    `_candidates` 는 비어 있고 stamp 만 있다 = 운영의 **정상 보유 상태**다.
    그래도 값이 나와야 한다.
    """
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    s._candidates.clear()
    s._position_setup["A"] = {
        "flag_high": 55_000, "pole_high": 54_000, "pole_start": 46_000,
    }
    assert s.get_effective_target_price("A")[0] == 63_000
    # 후보 표면은 실제로 비어 있다(대조군이 공허하지 않음을 못 박는다).
    assert s.get_targets_status().get("A") is None


def test_partial_exit_latch_is_reported():
    """이미 발화한 목표는 그 사실을 함께 낸다 — 숫자만 보이면 「아직」으로 읽힌다."""
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    s._position_setup["A"] = {
        "flag_high": 55_000, "pole_high": 54_000, "pole_start": 46_000,
    }
    s._partial_exit["A"] = True
    target, hit = s.get_effective_target_price("A")
    assert target == 63_000
    assert hit is True


# ── 경계 — 키 결손은 미발화가 계약 ────────────────────────────────────────


@pytest.mark.parametrize("setup", [
    {},
    {"flag_high": 55_000},                                   # pole 없음
    {"pole_high": 54_000, "pole_start": 46_000},             # flag_high 없음
    {"flag_high": 0, "pole_high": 54_000, "pole_start": 46_000},
    {"flag_high": 55_000, "pole_high": 46_000, "pole_start": 54_000},  # 폭 음수
    {"flag_high": 55_000, "pole_high": 50_000, "pole_start": 50_000},  # 폭 0
])
def test_missing_or_degenerate_keys_yield_none(setup):
    """임의 기본값으로 목표가를 지어내면 화면이 거짓 익절선을 보여 준다."""
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    s._position_setup["A"] = setup
    assert s.get_effective_target_price("A")[0] is None


def test_unheld_ticker_is_none():
    s = _make()
    s._position_setup["A"] = {
        "flag_high": 55_000, "pole_high": 54_000, "pole_start": 46_000,
    }
    assert s.get_effective_target_price("A") == (None, False)


def test_never_raises_on_broken_state():
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    s._position_setup["A"] = "셋업이 아님"          # type: ignore[assignment]
    assert s.get_effective_target_price("A") == (None, False)


# ── read-only 계약 ────────────────────────────────────────────────────────


def test_mirror_does_not_mutate_state():
    """🔴 read-only — 래치·셋업·후보 어느 것도 건드리지 않는다."""
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    setup = {"flag_high": 55_000, "pole_high": 54_000, "pole_start": 46_000}
    s._position_setup["A"] = dict(setup)
    before_latch = dict(s._partial_exit)
    before_cands = dict(s._candidates)

    for _ in range(3):
        s.get_effective_target_price("A")

    assert s._position_setup["A"] == setup
    assert dict(s._partial_exit) == before_latch, "미러가 익절 래치를 건드렸다"
    assert dict(s._candidates) == before_cands


def test_mirror_calls_effective_setup_with_observe_false():
    """🔴 `observe=True` 면 5분 watcher 의 cap 을 10초 폴링이 **선소비**한다.

    그러면 `[setup_structure_conflict]` 의 D+1 귀인이 무너진다 — 그 마커가
    「청산 평가 문맥」을 뜻한다는 계약이 깨진다.
    """
    s = _make()
    s.state.positions["A"] = _pos(50_000)
    s._position_setup["A"] = {
        "flag_high": 55_000, "pole_high": 54_000, "pole_start": 46_000,
    }
    seen: list[bool] = []
    orig = s._effective_setup

    def spy(ticker, observe=True):
        seen.append(observe)
        return orig(ticker, observe=False)

    s._effective_setup = spy                      # type: ignore[assignment]
    s.get_effective_target_price("A")
    assert seen == [False], f"observe 인자가 {seen} 로 넘어갔다 — False 여야 한다"
