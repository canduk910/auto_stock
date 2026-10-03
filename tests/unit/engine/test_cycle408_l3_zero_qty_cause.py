"""cycle408-L3 — 「매수 수량 0 → 900s cooldown」 WARNING 꼬리에 원인(funds|cap|unknown)을 붙인다.

결함: `execute_buy` 의 `quantity <= 0` 분기가 원인과 무관하게 같은 WARNING 을 남겨,
21:30 리포트·주간 자문이 ρ축·K축 사이징 캡 차단을 「투자금 부족」으로 오독했다
(09-28 ρ 10·자금 3 / 09-29 ρ 2·자금 2). 원인 마커는 INFO 라 2일 뒤 사라진다.

명세 = `_workspace/refactor/2026-10-04_eight_area_observability_fixes.md` L3 안 A.
- 판정: `잔여 = state.total_investment - strategy._calc_used_funds()` (순수 동기 읽기)
  · `잔여 < 현재가` → `funds` · 그 외 → `cap` · 판정 예외 → `unknown`(흡수).
- 메시지 앞부분 byte 동일 + 꼬리 `, 원인: %s, 잔여: %d)` 추가.
- 행위 불변 — `block_low_funds(+900)` 1회 · return · await 추가 0 · 원인별 쿨다운 차등 없음.
"""

from __future__ import annotations

import ast
import inspect
import logging
import textwrap
import time
from unittest.mock import AsyncMock

import pytest

from src.engine import order_engine as _oe
from src.engine.log_metrics_collector import _normalize_message
from src.engine.order_engine import LOW_FUNDS_COOLDOWN, OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.balance import BuyableInfo

pytestmark = pytest.mark.unit

_PREFIX = "매수 수량 0 → 900s cooldown: "


class _ZeroQtyStrategy(StrategyBase):
    """calc_buy_quantity 가 항상 0 — 사이징 갈래는 이 테스트의 관심이 아니다."""

    def __init__(self) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id="momentum",
                name="momentum-zero",
                enabled=True,
                weight=1.0,
                params={"exchange": "KRX"},
            )
        )

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


@pytest.fixture
def strategy() -> _ZeroQtyStrategy:
    return _ZeroQtyStrategy()


@pytest.fixture
def engine(strategy: _ZeroQtyStrategy) -> OrderEngine:
    reg = StrategyRegistry()
    reg.register(strategy)
    return OrderEngine(reg)


@pytest.fixture
def mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    get_buyable = AsyncMock(
        return_value=BuyableInfo(
            cash_available=10_000_000, max_buy_amount=10_000_000, max_buy_quantity=999,
        )
    )
    place_order = AsyncMock()
    insert_trade = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "get_buyable", get_buyable)
    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(_oe, "insert_trade", insert_trade)
    return {"get_buyable": get_buyable, "place_order": place_order, "insert_trade": insert_trade}


def _zero_qty_warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(_PREFIX)
    ]


async def _run(engine, strategy, mocks, caplog, ticker="012200", price=10_000):
    calls: list[tuple[str, float]] = []
    orig = strategy.state.block_low_funds

    def _rec(t, until):
        calls.append((t, until))
        orig(t, until)

    strategy.state.block_low_funds = _rec  # type: ignore[method-assign]
    pending_before = (set(strategy.state.pending_buys), dict(strategy.state.pending_buy_amounts))
    before = time.time()
    with caplog.at_level(logging.WARNING):
        await engine.execute_buy(ticker, price, strategy)
    after = time.time()

    # 공통 불변 — 쿨다운 1회 · 900s · 주문/장부 무접촉 · get_buyable 추가 호출 0
    assert len(calls) == 1
    assert calls[0][0] == ticker
    assert before + LOW_FUNDS_COOLDOWN - 1 <= calls[0][1] <= after + LOW_FUNDS_COOLDOWN + 1
    assert mocks["place_order"].await_count == 0
    assert mocks["insert_trade"].await_count == 0
    assert mocks["get_buyable"].await_count <= 1
    assert (set(strategy.state.pending_buys), dict(strategy.state.pending_buy_amounts)) == pending_before

    msgs = _zero_qty_warnings(caplog)
    assert len(msgs) == 1, msgs
    return msgs[0]


@pytest.mark.asyncio
async def test_zero_qty_when_remaining_below_price_then_cause_funds(engine, strategy, mocks, caplog):
    strategy.state.total_investment = 100_000
    strategy.state.positions["000660"] = Position(
        ticker="000660", buy_price=95_000, quantity=1, order_no="X", strategy_id="momentum",
    )
    msg = await _run(engine, strategy, mocks, caplog)
    assert msg == (
        "매수 수량 0 → 900s cooldown: 012200 "
        "(투자금: 100000, 현재가: 10000, 전략: momentum, 원인: funds, 잔여: 5000)"
    )


@pytest.mark.asyncio
async def test_zero_qty_when_remaining_covers_price_then_cause_cap(engine, strategy, mocks, caplog):
    strategy.state.total_investment = 1_000_000
    msg = await _run(engine, strategy, mocks, caplog)
    assert msg == (
        "매수 수량 0 → 900s cooldown: 012200 "
        "(투자금: 1000000, 현재가: 10000, 전략: momentum, 원인: cap, 잔여: 1000000)"
    )


@pytest.mark.asyncio
async def test_zero_qty_when_remaining_equals_price_then_cause_cap(engine, strategy, mocks, caplog):
    """경계 — 잔여 == 현재가 면 1주는 살 수 있으므로 자금이 아니다(`_fallback_one_share` 와 같은 부등호)."""
    strategy.state.total_investment = 10_000
    msg = await _run(engine, strategy, mocks, caplog)
    assert msg.endswith("원인: cap, 잔여: 10000)")


@pytest.mark.asyncio
async def test_zero_qty_when_cause_probe_raises_then_unknown_and_no_propagation(
    engine, strategy, mocks, caplog, monkeypatch,
):
    strategy.state.total_investment = 1_000_000

    def _boom() -> int:
        raise RuntimeError("probe failure")

    monkeypatch.setattr(strategy, "_calc_used_funds", _boom)
    msg = await _run(engine, strategy, mocks, caplog)
    assert msg.startswith(
        "매수 수량 0 → 900s cooldown: 012200 (투자금: 1000000, 현재가: 10000, 전략: momentum, "
    )
    assert "원인: unknown" in msg


@pytest.mark.asyncio
async def test_normalized_patterns_split_by_cause_and_merge_within_cause(
    engine, strategy, mocks, caplog,
):
    """21:30 `top_patterns` — 원인이 다르면 패턴이 갈리고, 같은 원인은 잔여 숫자와 무관하게 하나."""
    out: dict[str, str] = {}
    for key, total, ticker in (
        ("cap_a", 1_000_000, "012200"),
        ("cap_b", 2_000_000, "005930"),
        ("funds_a", 5_000, "035420"),
        ("funds_b", 7_000, "000270"),
    ):
        strategy.state.total_investment = total
        caplog.clear()
        mocks["get_buyable"].reset_mock()
        out[key] = _normalize_message(await _run(engine, strategy, mocks, caplog, ticker=ticker))
    assert out["cap_a"] == out["cap_b"]
    assert out["funds_a"] == out["funds_b"]
    assert out["cap_a"] != out["funds_a"]
    assert "원인: cap" in out["cap_a"] and "원인: funds" in out["funds_a"]


def _zero_qty_branch(fn_src: str) -> ast.If:
    tree = ast.parse(textwrap.dedent(fn_src))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "quantity"
            and isinstance(node.test.ops[0], ast.LtE)
        ):
            return node
    raise AssertionError("execute_buy 의 `if quantity <= 0:` 분기를 찾지 못했다")


def test_zero_qty_branch_is_await_free_and_cooldown_precedes_warning():
    """원인 판정은 동기 — 분기 안 Await 0. 쿨다운 등록이 판정·로그보다 먼저(행위 순서 불변)."""
    branch = _zero_qty_branch(inspect.getsource(OrderEngine.execute_buy))
    assert not [n for n in ast.walk(branch) if isinstance(n, ast.Await)]
    first = branch.body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
    assert getattr(first.value.func, "attr", None) == "block_low_funds"
    assert isinstance(branch.body[-1], ast.Return)
