"""cycle443 — Ndx2xRiskoffStrategy 전략 레벨 회귀(집행창·상태전이·섀도).

핵심 신호 수학(T7/R4/칸)은 `tests/unit/engine/test_cycle443_ndx2x_core.py` 가 오라클
대조로 이미 덮는다. 이 파일은 "그 수학을 전략이 올바른 시각·상태에서만 쓰는가" —
집행창(09:30~10:30 KST) 게이트·상태 전이(BUY/SELL)·보유 가드·섀도 관문을 겨눈다.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from src.engine import ndx2x_core
from src.engine.strategies.ndx2x_riskoff import Ndx2xRiskoffStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
T = Ndx2xRiskoffStrategy.FIXED_TICKER


def _make(**params) -> Ndx2xRiskoffStrategy:
    return Ndx2xRiskoffStrategy(StrategyConfig(
        strategy_id="ndx2x_riskoff", name="나스닥2배-위험회피", enabled=True, weight=0.0,
        params={"shadow_mode": False, **params},
    ))


def _decision(desired_state, *, cell="10") -> ndx2x_core.DailyDecision:
    return ndx2x_core.DailyDecision(t7=0.01, r4=-0.05, cell=cell, desired_state=desired_state, reason="ok")


def _freeze(monkeypatch, h, m, s=0, *, day=date(2026, 10, 12)):
    fixed = datetime(day.year, day.month, day.day, h, m, s, tzinfo=_KST)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is not None else fixed.replace(tzinfo=None)

    import src.engine.strategies.ndx2x_riskoff as mod
    monkeypatch.setattr(mod, "datetime", _FixedDateTime)


# ─────────────────────────── 집행창(09:30~10:30) ───────────────────────────

def test_check_buy_signal_outside_window_before_open_returns_none(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    _freeze(monkeypatch, 9, 29, 59)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_buy_signal_outside_window_after_close_returns_none(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    _freeze(monkeypatch, 10, 30, 1)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_buy_signal_inside_window_boundary_start_fires(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    _freeze(monkeypatch, 9, 30, 0)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.BUY


def test_check_buy_signal_inside_window_boundary_end_fires(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    _freeze(monkeypatch, 10, 30, 0)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.BUY


def test_check_exit_signal_outside_window_returns_none_even_when_cash(monkeypatch):
    s = _make()
    s._decision = _decision("cash", cell="01")
    s.state.positions[T] = Position(
        ticker=T, buy_price=40_000, quantity=10, order_no="O1",
        strategy_id="ndx2x_riskoff", buy_date=date(2026, 10, 1),
    )
    _freeze(monkeypatch, 15, 0, 0)
    assert s.check_exit_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_exit_signal_inside_window_cash_decision_fires_trend_exit(monkeypatch):
    s = _make()
    s._decision = _decision("cash", cell="01")
    s.state.positions[T] = Position(
        ticker=T, buy_price=40_000, quantity=10, order_no="O1",
        strategy_id="ndx2x_riskoff", buy_date=date(2026, 10, 1),
    )
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_exit_signal(T, 42_000, 41_800) == Signal.TREND_EXIT


# ─────────────────────────── 상태·보유 가드 ───────────────────────────

def test_check_buy_signal_none_when_decision_missing(monkeypatch):
    s = _make()
    s._decision = None
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_buy_signal_none_when_desired_state_is_cash(monkeypatch):
    s = _make()
    s._decision = _decision("cash", cell="01")
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_buy_signal_none_when_already_holding(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    s.state.positions[T] = Position(
        ticker=T, buy_price=40_000, quantity=10, order_no="O1",
        strategy_id="ndx2x_riskoff", buy_date=date(2026, 10, 1),
    )
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_exit_signal_none_when_no_position(monkeypatch):
    s = _make()
    s._decision = _decision("cash", cell="01")
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_exit_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_exit_signal_none_when_desired_state_is_2x(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    s.state.positions[T] = Position(
        ticker=T, buy_price=40_000, quantity=10, order_no="O1",
        strategy_id="ndx2x_riskoff", buy_date=date(2026, 10, 1),
    )
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_exit_signal(T, 42_000, 41_800) == Signal.NONE


def test_check_buy_signal_wrong_ticker_returns_none(monkeypatch):
    s = _make()
    s._decision = _decision("2x")
    _freeze(monkeypatch, 10, 0, 0)
    assert s.check_buy_signal("005930", 42_000, 41_800) == Signal.NONE


# ─────────────────────────── 섀도(기본 True) ───────────────────────────

def test_shadow_mode_default_true_intercepts_buy(monkeypatch, caplog):
    import logging
    s = Ndx2xRiskoffStrategy(StrategyConfig(
        strategy_id="ndx2x_riskoff", name="나스닥2배-위험회피", enabled=True, weight=0.0, params={},
    ))
    assert s.config.params["shadow_mode"] is True
    s._decision = _decision("2x")
    _freeze(monkeypatch, 10, 0, 0)
    caplog.set_level(logging.INFO, logger="src.engine.strategy_base")
    assert s.check_buy_signal(T, 42_000, 41_800) == Signal.NONE
    assert any("[shadow_buy]" in r.getMessage() for r in caplog.records)


# ─────────────────────────── calc_buy_quantity ───────────────────────────

def test_calc_buy_quantity_uses_position_ratio_and_margin():
    s = _make(position_ratio=1.0)
    s.state.total_investment = 1_000_000
    qty = s.calc_buy_quantity(42_000)
    # floor(1_000_000 * 1.0 * 0.995 / 42_000) = floor(23.69...) = 23, 관문(_apply_budget_limit)
    # 잔여 클램프 동일(보유·pending 0)이라 그대로.
    assert qty == 23


def test_calc_buy_quantity_zero_price_is_zero():
    s = _make()
    assert s.calc_buy_quantity(0) == 0


# ─────────────────────────── sync_daily_decision — idempotent + 결측 fail-closed ───────────────────────────

@pytest.mark.asyncio
async def test_sync_daily_decision_is_idempotent_per_day(monkeypatch):
    import src.engine.strategies.ndx2x_riskoff as mod
    s = _make()
    mock_ensure = AsyncMock()
    monkeypatch.setattr(mod, "ensure_history", mock_ensure)
    mock_get_recent = AsyncMock(return_value=[(date(2026, 10, 9), 100.0)] * 400)
    monkeypatch.setattr(mod._overseas_index_db, "get_recent_closes", mock_get_recent)

    today = date(2026, 10, 12)
    await s.sync_daily_decision(today=today)
    await s.sync_daily_decision(today=today)

    assert mock_ensure.await_count == 1  # 두 번째 호출은 재계산 0


@pytest.mark.asyncio
async def test_sync_daily_decision_insufficient_history_is_fail_closed(monkeypatch):
    import src.engine.strategies.ndx2x_riskoff as mod
    s = _make()
    monkeypatch.setattr(mod, "ensure_history", AsyncMock())
    monkeypatch.setattr(mod._overseas_index_db, "get_recent_closes", AsyncMock(return_value=[]))

    decision = await s.sync_daily_decision(today=date(2026, 10, 12))

    assert decision.reason == "insufficient_history"
    assert decision.desired_state is None
