"""src/engine/strategy_registry.py 단위 테스트.

전략 등록, 비중 기반 자금 분배, 전략 간 중복 매수 차단 가드를 검증한다.
"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


class _Strat(StrategyBase):
    async def prepare(self):
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price):
        return 0


def _make(strategy_id, weight=0.5, enabled=True):
    return _Strat(StrategyConfig(
        strategy_id=strategy_id, name=strategy_id, weight=weight, enabled=enabled,
    ))


@pytest.fixture
def registry():
    return StrategyRegistry()


# ---------------------------------------------------------------------------
# 등록/조회
# ---------------------------------------------------------------------------
def test_register_and_get(registry):
    s = _make("momentum")
    registry.register(s)
    assert registry.get("momentum") is s
    assert registry.get("nonexistent") is None


def test_all_returns_every_strategy_regardless_of_enabled(registry):
    a = _make("a", enabled=True)
    b = _make("b", enabled=False)
    registry.register(a)
    registry.register(b)
    assert set(registry.all()) == {a, b}


def test_enabled_filters_out_disabled(registry):
    a = _make("a", enabled=True)
    b = _make("b", enabled=False)
    registry.register(a)
    registry.register(b)
    assert registry.enabled() == [a]


# ---------------------------------------------------------------------------
# 자금 분배
# ---------------------------------------------------------------------------
def test_allocate_funds_distributes_by_weight_among_enabled(registry):
    a = _make("a", weight=0.6)
    b = _make("b", weight=0.4)
    registry.register(a)
    registry.register(b)

    registry.allocate_funds(total_asset=10_000_000)

    assert a.state.total_investment == 6_000_000
    assert b.state.total_investment == 4_000_000


def test_allocate_funds_when_disabled_then_excluded(registry):
    a = _make("a", weight=0.6, enabled=True)
    b = _make("b", weight=0.4, enabled=False)
    registry.register(a)
    registry.register(b)

    registry.allocate_funds(total_asset=10_000_000)

    # 활성 a 만 100% 받는다 (b 는 비활성이라 분모에서 제외)
    assert a.state.total_investment == 10_000_000
    assert b.state.total_investment == 0


def test_allocate_funds_when_total_weight_zero_then_zero(registry):
    a = _make("a", weight=0.0, enabled=True)
    registry.register(a)
    # weight=0 이지만 enabled=True 인 경우 — total_weight=0 이라 ratio=0
    # (이런 상태는 update_weights 가 자동으로 비활성화하지만, 직접 register 한 케이스)
    registry.allocate_funds(total_asset=10_000_000)
    assert a.state.total_investment == 0


# ---------------------------------------------------------------------------
# 비중 업데이트 → 자동 활성/비활성 전환
# ---------------------------------------------------------------------------
def test_update_weights_when_zero_then_disables(registry):
    a = _make("a", weight=0.5, enabled=True)
    registry.register(a)

    registry.update_weights({"a": 0.0})

    assert a.config.weight == 0.0
    assert a.config.enabled is False


def test_update_weights_when_positive_then_enables_disabled(registry):
    a = _make("a", weight=0.0, enabled=False)
    registry.register(a)

    registry.update_weights({"a": 0.3})

    assert a.config.weight == 0.3
    assert a.config.enabled is True


def test_update_weights_ignores_unknown_ids(registry):
    # 등록되지 않은 id 가 와도 예외 없이 무시
    registry.update_weights({"ghost": 0.5})  # no-op


# ---------------------------------------------------------------------------
# 전략 간 매수 차단 가드
# ---------------------------------------------------------------------------
def _seed_position(strategy: _Strat, ticker: str):
    strategy.state.positions[ticker] = Position(
        ticker=ticker, buy_price=70000, quantity=10,
        order_no=f"O-{ticker}", strategy_id=strategy.strategy_id,
    )


def test_is_ticker_blocked_when_other_strategy_holds(registry):
    a = _make("a")
    b = _make("b")
    registry.register(a)
    registry.register(b)
    _seed_position(a, "005930")

    # b 가 사려고 해도 a 가 보유 중이라 차단된다
    assert registry.is_ticker_blocked_for_buy("005930") is True


def test_is_ticker_blocked_when_other_strategy_pending(registry):
    a = _make("a")
    b = _make("b")
    registry.register(a)
    registry.register(b)
    a.state.pending_buys.add("005930")

    assert registry.is_ticker_blocked_for_buy("005930") is True


def test_is_ticker_blocked_when_other_strategy_sold_today(registry):
    a = _make("a")
    b = _make("b")
    registry.register(a)
    registry.register(b)
    a.state.sold_today.add("005930")

    assert registry.is_ticker_blocked_for_buy("005930") is True


def test_is_ticker_not_blocked_when_no_strategy_touches_it(registry):
    a = _make("a")
    registry.register(a)
    assert registry.is_ticker_blocked_for_buy("005930") is False


def test_is_ticker_held_by_any_distinguishes_held_from_sold(registry):
    a = _make("a")
    registry.register(a)
    a.state.sold_today.add("005930")
    # sold_today 는 보유가 아니므로 held_by_any 는 False
    assert registry.is_ticker_held_by_any("005930") is False
    a.state.pending_buys.add("000660")
    assert registry.is_ticker_held_by_any("000660") is True


def test_find_strategy_for_ticker_returns_holder(registry):
    a = _make("a")
    b = _make("b")
    registry.register(a)
    registry.register(b)
    _seed_position(b, "005930")

    holder = registry.find_strategy_for_ticker("005930")
    assert holder is b


def test_find_strategy_for_ticker_when_no_holder_then_none(registry):
    a = _make("a")
    registry.register(a)
    assert registry.find_strategy_for_ticker("005930") is None
