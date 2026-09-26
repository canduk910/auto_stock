"""cycle379 Red — ⑨A 배선: `_sync_positions_from_balance` → `buying_reconcile.reconcile_stale_buying`.

명세 = `_workspace/red/cycle379_buying_reconcile_spec.md` §2.1 (scheduler 4줄 — 사용자 승인 · 상한 <3,900)

| # | 계약 |
|---|---|
| W1 | 어느 전략이든 `pending_buys` 가 있으면 leaf 를 부른다 · 없으면 부르지 않는다 |
| W1b | `_selling` 이 비어 있어도 부른다 — selling 위임 `if` 블록 **안**에 넣으면 안 된다 |
| W2 | `holdings` 는 같은 함수 첫 줄 `get_balance()` 결과 객체 그대로(추가 잔고 조회 0) |
| W3 | selling 위임 **뒤**에 부른다 |

`TradingScheduler` 를 세우지 않는다 — 함수를 가짜 `self`(실 registry · 실 OrderEngine)로 직접 부른다.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

_LEAF = "src.engine.buying_reconcile"


class _Strat(StrategyBase):
    def __init__(self, sid: str) -> None:
        super().__init__(StrategyConfig(strategy_id=sid, name=sid, enabled=True, weight=0.5,
                                        params={"exchange": "KRX"}))

    async def prepare(self, *, as_of=None) -> None:  # pragma: no cover
        return None

    def check_buy_signal(self, ticker, current_price, open_price):  # pragma: no cover
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):  # pragma: no cover
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:  # pragma: no cover
        return 0


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import src.db.trade_history as _th
    import src.engine.scheduler as _sched
    import src.engine.selling_reconcile as _sr

    try:
        leaf = importlib.import_module(_LEAF)
    except ModuleNotFoundError:
        leaf = None  # Red — `_sync` 가 테스트 안에서 명시 실패시킨다(fixture ERROR 대신)

    order: list[str] = []
    holdings: list = []  # 식별 대상 — 같은 객체가 leaf 로 가야 한다
    summary = SimpleNamespace(net_asset=0, deposit=0)

    async def _selling(*_a, **_k):
        order.append("selling")

    async def _buying(*_a, **_k):
        order.append("buying")

    sell_spy = AsyncMock(side_effect=_selling)
    buy_spy = AsyncMock(side_effect=_buying)
    monkeypatch.setattr(_sr, "reconcile_stale_selling", sell_spy)
    if leaf is not None:
        monkeypatch.setattr(leaf, "reconcile_stale_buying", buy_spy, raising=False)
    gb = AsyncMock(return_value=(holdings, summary))
    monkeypatch.setattr(_sched, "get_balance", gb)
    monkeypatch.setattr(_th, "mark_pending_buys_completed", AsyncMock(return_value=0))
    monkeypatch.setattr(_th, "get_recent_buy_strategy", AsyncMock(return_value=None))

    reg = StrategyRegistry()
    for sid in ("momentum", "volatility_breakout"):
        reg.register(_Strat(sid))
    eng = OrderEngine(reg)
    fake_self = SimpleNamespace(registry=reg, order_engine=eng)
    return SimpleNamespace(
        sched=_sched, self=fake_self, reg=reg, eng=eng, holdings=holdings, leaf=leaf,
        order=order, sell_spy=sell_spy, buy_spy=buy_spy, get_balance=gb,
    )


async def _sync(env) -> None:
    if env.leaf is None:
        pytest.fail(f"[Red] leaf `{_LEAF}` 미구현 (명세 §2.1)")
    await env.sched.TradingScheduler._sync_positions_from_balance(env.self)


def _call_parts(spy: AsyncMock):
    call = spy.await_args
    a, k = list(call.args), dict(call.kwargs)
    registry = k.get("registry", a[0] if len(a) > 0 else None)
    engine = k.get("order_engine", a[1] if len(a) > 1 else None)
    holdings = k.get("holdings", a[2] if len(a) > 2 else None)
    return registry, engine, holdings


async def test_w1_pending_buy_triggers_leaf_even_when_selling_is_empty(env) -> None:
    env.reg.get("volatility_breakout").state.pending_buys.add("437730")
    assert not env.eng._selling
    await _sync(env)
    assert env.buy_spy.await_count == 1, (
        "pending 이 있으면 buying leaf 를 불러야 한다 — selling `if self.order_engine._selling:` "
        "블록 안에 넣으면 `_selling` 이 빌 때 영영 안 돈다"
    )
    env.sell_spy.assert_not_awaited()


async def test_w1b_no_pending_buy_means_no_leaf_call(env) -> None:
    await _sync(env)
    env.buy_spy.assert_not_awaited()


async def test_w2_leaf_receives_same_holdings_object_registry_and_engine(env) -> None:
    env.reg.get("momentum").state.pending_buys.add("437730")
    await _sync(env)
    registry, engine, holdings = _call_parts(env.buy_spy)
    assert registry is env.reg
    assert engine is env.eng
    assert holdings is env.holdings, "추가 잔고 조회 없이 첫 줄 get_balance() 결과를 넘긴다"
    assert env.get_balance.await_count == 1, "잔고 조회가 늘었다"


async def test_w3_buying_runs_after_selling_delegation(env) -> None:
    env.reg.get("momentum").state.pending_buys.add("437730")
    env.eng._selling.add("161580")
    await _sync(env)
    assert env.order == ["selling", "buying"], f"순서 {env.order} (기대 selling → buying)"
