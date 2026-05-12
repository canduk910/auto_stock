"""src/engine/strategy_base.py 단위 테스트.

Signal 열거, Position 데이터 모델, StrategyState의 캐시/락/cooldown 동작을 다룬다.
StrategyBase 추상 클래스의 헬퍼(is_max_positions, is_daily_loss_exceeded)도 검증.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
    StrategyState,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Signal / Position
# ---------------------------------------------------------------------------
def test_signal_values():
    assert Signal.NONE == "NONE"
    assert Signal.BUY == "BUY"
    assert Signal.STOP_LOSS == "STOP_LOSS"
    assert Signal.NEXT_DAY_CLEAR == "NEXT_DAY_CLEAR"
    assert Signal.TRAILING_STOP == "TRAILING_STOP"
    assert Signal.FORCE_CLEAR == "FORCE_CLEAR"


def test_position_high_since_buy_defaults_to_buy_price():
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum",
    )
    assert pos.high_since_buy == 70000


def test_position_explicit_high_since_buy_is_kept():
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum", high_since_buy=72000,
    )
    assert pos.high_since_buy == 72000


def test_position_is_next_day_when_buy_date_is_yesterday():
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum",
        buy_date=date.today() - timedelta(days=1),
    )
    assert pos.is_next_day is True


def test_position_is_not_next_day_when_buy_date_is_today():
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum",
    )
    assert pos.is_next_day is False


# ---------------------------------------------------------------------------
# I2 (2026-05-12) — donchian_swing 멀티데이 보유: is_next_day 항상 False
#
# 결함: Position.is_next_day가 buy_date < today만 보고 전략 무관 판정 →
# donchian_swing(ATR×2 트레일링/-7% 하드 손절 / 시간 청산 없음 / 멀티데이 보유)
# 둘째 날부터 자동 is_next_day=True 분류 → OrderMonitor "청산" 배지 매일 노출.
# 멀티데이 보유 전략은 시간 청산 개념이 없으므로 항상 False 반환해야 한다.
# 다른 전략(momentum/volatility_breakout/long_tail_volatility)은 기존 동작 유지.
# ---------------------------------------------------------------------------
def test_position_is_next_day_donchian_swing_yesterday_then_false():
    """donchian_swing은 멀티데이 보유 — 어제 매수여도 is_next_day=False."""
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="donchian_swing",
        buy_date=date.today() - timedelta(days=1),
    )
    assert pos.is_next_day is False


def test_position_is_next_day_donchian_swing_today_then_false():
    """donchian_swing은 당일 매수도 당연히 is_next_day=False."""
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="donchian_swing",
    )
    assert pos.is_next_day is False


def test_position_is_next_day_donchian_swing_one_week_ago_then_false():
    """donchian_swing은 1주일 전 매수도 멀티데이 보유 — False 유지."""
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="donchian_swing",
        buy_date=date.today() - timedelta(days=7),
    )
    assert pos.is_next_day is False


def test_position_is_next_day_volatility_breakout_yesterday_then_true():
    """volatility_breakout은 익일 분류 동작 유지 (당일 매매 전략이지만 정의상 True)."""
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="volatility_breakout",
        buy_date=date.today() - timedelta(days=1),
    )
    assert pos.is_next_day is True


def test_position_is_next_day_long_tail_volatility_yesterday_then_true():
    """long_tail_volatility는 상한가 모드 시 익일 청산 — True 유지."""
    pos = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="long_tail_volatility",
        buy_date=date.today() - timedelta(days=1),
    )
    assert pos.is_next_day is True


# ---------------------------------------------------------------------------
# StrategyState — 보유/대기/매도 플래그
# ---------------------------------------------------------------------------
def test_state_has_position_pending_sold_helpers():
    s = StrategyState(strategy_id="momentum")
    assert s.has_position("005930") is False
    s.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O1", strategy_id="momentum",
    )
    assert s.has_position("005930") is True
    s.pending_buys.add("000660")
    assert s.is_buy_pending("000660") is True
    s.sold_today.add("035720")
    assert s.is_sold_today("035720") is True


# ---------------------------------------------------------------------------
# StrategyState — 잔고 부족 락 (block_buy / unblock_buy)
# ---------------------------------------------------------------------------
def test_block_buy_when_until_in_future_then_is_blocked():
    s = StrategyState(strategy_id="momentum")
    s.cached_buyable_qty = 5  # 캐시가 살아있다고 가정
    s.cached_buyable_at = 100.0

    s.block_buy(until_ts=200.0)

    assert s.is_buy_blocked(now_ts=150.0) is True
    # 락 등록과 동시에 매수가능 캐시는 무효화되어야 한다
    assert s.cached_buyable_qty == -1
    assert s.cached_buyable_at == 0.0


def test_block_buy_when_now_past_until_then_not_blocked():
    s = StrategyState(strategy_id="momentum")
    s.block_buy(until_ts=100.0)
    assert s.is_buy_blocked(now_ts=200.0) is False


def test_unblock_buy_resets_lock_and_cache():
    s = StrategyState(strategy_id="momentum")
    s.block_buy(until_ts=500.0)
    s.unblock_buy()
    assert s.buy_blocked_until == 0.0
    assert s.cached_buyable_qty == -1
    assert s.cached_buyable_at == 0.0


# ---------------------------------------------------------------------------
# StrategyState — 매수가능 캐시 TTL
# ---------------------------------------------------------------------------
def test_buyable_cache_fresh_when_within_ttl_and_initialized():
    s = StrategyState(strategy_id="momentum")
    s.cached_buyable_qty = 10
    s.cached_buyable_at = 100.0
    assert s.is_buyable_cache_fresh(now_ts=130.0, ttl=60.0) is True


def test_buyable_cache_stale_when_uninitialized():
    s = StrategyState(strategy_id="momentum")
    # cached_buyable_qty 기본 -1 (미초기화)
    assert s.is_buyable_cache_fresh(now_ts=10.0, ttl=60.0) is False


def test_buyable_cache_stale_when_ttl_exceeded():
    s = StrategyState(strategy_id="momentum")
    s.cached_buyable_qty = 10
    s.cached_buyable_at = 100.0
    assert s.is_buyable_cache_fresh(now_ts=170.0, ttl=60.0) is False


# ---------------------------------------------------------------------------
# StrategyState — per-ticker low_funds cooldown
# ---------------------------------------------------------------------------
def test_low_funds_block_when_within_window_then_true():
    s = StrategyState(strategy_id="momentum")
    s.block_low_funds("005930", until_ts=200.0)
    assert s.is_low_funds_blocked("005930", now_ts=150.0) is True


def test_low_funds_block_when_expired_then_false_and_pruned():
    s = StrategyState(strategy_id="momentum")
    s.block_low_funds("005930", until_ts=100.0)
    # 만료된 시점에 조회하면 False + 자동 정리
    assert s.is_low_funds_blocked("005930", now_ts=200.0) is False
    assert "005930" not in s.low_funds_tickers


def test_clear_low_funds_removes_all_entries():
    s = StrategyState(strategy_id="momentum")
    s.block_low_funds("005930", until_ts=500.0)
    s.block_low_funds("000660", until_ts=600.0)
    s.clear_low_funds()
    assert s.low_funds_tickers == {}


# ---------------------------------------------------------------------------
# StrategyBase — 헬퍼
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    """추상 메서드만 채운 더미 — 헬퍼 동작 검증용."""

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price):
        return 0


def _make_dummy(max_positions=4, daily_loss_limit=-5.0):
    return _DummyStrategy(StrategyConfig(
        strategy_id="dummy", name="Dummy",
        params={"max_positions": max_positions, "daily_loss_limit": daily_loss_limit},
    ))


def test_is_max_positions_when_positions_plus_pending_equals_max_then_true():
    s = _make_dummy(max_positions=2)
    s.state.positions["A"] = Position(
        ticker="A", buy_price=1, quantity=1, order_no="O", strategy_id="dummy",
    )
    s.state.pending_buys.add("B")
    assert s.is_max_positions() is True


def test_is_max_positions_when_below_max_then_false():
    s = _make_dummy(max_positions=4)
    s.state.positions["A"] = Position(
        ticker="A", buy_price=1, quantity=1, order_no="O", strategy_id="dummy",
    )
    assert s.is_max_positions() is False


def test_is_daily_loss_exceeded_when_no_investment_then_false():
    s = _make_dummy()
    s.state.daily_realized_pnl = -1_000_000  # 손실은 있지만
    s.state.total_investment = 0  # 분모 0
    assert s.is_daily_loss_exceeded() is False


def test_is_daily_loss_exceeded_when_loss_rate_breaches_limit_then_true():
    s = _make_dummy(daily_loss_limit=-5.0)
    s.state.total_investment = 10_000_000
    s.state.daily_realized_pnl = -600_000  # -6%
    assert s.is_daily_loss_exceeded() is True


def test_is_daily_loss_exceeded_when_loss_rate_within_limit_then_false():
    s = _make_dummy(daily_loss_limit=-5.0)
    s.state.total_investment = 10_000_000
    s.state.daily_realized_pnl = -400_000  # -4%
    assert s.is_daily_loss_exceeded() is False
