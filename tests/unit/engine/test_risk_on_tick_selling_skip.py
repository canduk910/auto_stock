"""사이클 19 (2026-05-20) — RiskManager.on_tick `_selling` 가드 회귀 가드.

배경 (운영 결함):
- 2026-05-20 08:41:33~08:41:40 042700 한미반도체 VB 손절 매도 1주 시장가 발사 (1회 정상)
- 그러나 7초 동안 `[volatility_breakout] 변동성돌파 손절: ...` INFO 로그 18+ 행 폭주
- 근본 원인: `risk.on_tick` 보유 분기에서 `_selling` 검사 없이 매 tick `check_exit_signal` 호출
  → 매도 발사 후 체결통보 도착 전까지 손절 로그 반복

수정:
- `risk.on_tick` 보유 분기에서 `check_exit_signal` 호출 *전* `order_engine._selling` 검사
- `ticker in self.order_engine._selling` → continue (다음 전략으로)

검증 (3 케이스):
1. (A) `_selling` 비어있음 → check_exit_signal 정상 호출 + STOP_LOSS 시 execute_sell 호출
2. (B) `_selling` 에 ticker 있음 → check_exit_signal 호출 안 함 + execute_sell 호출 안 함
3. (C) 매도 진행 중 종목 + 다른 보유 종목 → 다른 종목은 정상 평가 (격리)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


class _SpyStrategy(StrategyBase):
    """check_exit_signal / check_buy_signal 호출 추적 + 반환 신호 지정 가능."""

    def __init__(self, config, exit_signal: Signal = Signal.NONE):
        super().__init__(config)
        self.exit_calls: list[tuple[str, int, int]] = []
        self.buy_calls: list[tuple[str, int, int]] = []
        self._exit_signal = exit_signal

    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        self.buy_calls.append((ticker, current_price, open_price))
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        self.exit_calls.append((ticker, current_price, open_price))
        return self._exit_signal

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


@pytest.fixture(autouse=True)
def _active_main_board(monkeypatch):
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))


@pytest.fixture(autouse=True)
def _ticker_prev_close(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prev_close", {"042700": 100_000, "005930": 70_000})
    monkeypatch.setattr(scanner, "ticker_prices", {})


def _make_order_engine_with_selling(selling: set[str]) -> MagicMock:
    """order_engine 모의 객체 — `_selling` set + execute_sell/execute_buy AsyncMock."""
    order_engine = MagicMock()
    order_engine._selling = selling
    order_engine.execute_sell = AsyncMock()
    order_engine.execute_buy = AsyncMock()
    return order_engine


# ---------------------------------------------------------------------------
# Case (A): `_selling` 비어있음 → check_exit_signal 정상 호출 + STOP_LOSS 시 execute_sell
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_selling_empty_exit_signal_evaluated_and_sell_executed():
    """매도 진행 중이 아니면 손절 신호 정상 평가 + execute_sell 호출."""
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(
            strategy_id="volatility_breakout", name="VB", weight=1.0, enabled=True,
            params={"tradable_boards": ["main"]},
        ),
        exit_signal=Signal.STOP_LOSS,  # 손절 신호 반환
    )
    vb.state.positions["042700"] = Position(
        ticker="042700", buy_price=100_000, quantity=1,
        order_no="O-1", strategy_id="volatility_breakout",
    )
    registry.register(vb)

    order_engine = _make_order_engine_with_selling(set())  # 매도 진행 중 종목 없음
    risk = RiskManager(registry, order_engine)

    await risk.on_tick("042700", current_price=92_000, open_price=100_000, change_rate=-8.0)

    # check_exit_signal 정상 호출
    assert len(vb.exit_calls) == 1
    assert vb.exit_calls[0] == ("042700", 92_000, 100_000)
    # STOP_LOSS 신호 → execute_sell 호출
    assert order_engine.execute_sell.call_count == 1
    call_args = order_engine.execute_sell.call_args
    assert call_args.args[0] == "042700"
    assert call_args.args[1] == Signal.STOP_LOSS
    assert call_args.args[2] == "volatility_breakout"


# ---------------------------------------------------------------------------
# Case (B): `_selling` 에 ticker → check_exit_signal 호출 안 함 + execute_sell 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_selling_in_progress_exit_signal_skipped():
    """매도 발사 후 체결통보 도착 전 → check_exit_signal/execute_sell 모두 0회.

    이것이 사이클 19 의 핵심: 로그 폭주 차단.
    """
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(
            strategy_id="volatility_breakout", name="VB", weight=1.0, enabled=True,
            params={"tradable_boards": ["main"]},
        ),
        exit_signal=Signal.STOP_LOSS,  # 손절 신호 반환 (호출됐다면)
    )
    vb.state.positions["042700"] = Position(
        ticker="042700", buy_price=100_000, quantity=1,
        order_no="O-1", strategy_id="volatility_breakout",
    )
    registry.register(vb)

    # 042700 매도 진행 중 (execute_sell 이 이미 발사된 상태)
    order_engine = _make_order_engine_with_selling({"042700"})
    risk = RiskManager(registry, order_engine)

    # 손절 임계 충족 가격으로 on_tick — 가드가 없다면 check_exit_signal + execute_sell 발사
    await risk.on_tick("042700", current_price=92_000, open_price=100_000, change_rate=-8.0)

    # 가드 동작: check_exit_signal 호출 0회 → 로그 폭주 차단
    assert vb.exit_calls == [], (
        f"_selling 에 ticker 있으면 check_exit_signal skip — 손절 로그 폭주 차단. "
        f"실제 호출={vb.exit_calls}"
    )
    # execute_sell 도 호출 0회 (이미 매도 진행 중이므로 중복 발사 불필요)
    assert order_engine.execute_sell.call_count == 0


# ---------------------------------------------------------------------------
# Case (C): 매도 진행 중 종목 + 다른 보유 종목 → 다른 종목은 정상 평가 (격리)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_selling_skip_isolated_per_ticker():
    """042700 매도 진행 중이어도 005930 (다른 보유 종목) 은 정상 손절 평가.

    가드는 ticker 단위 격리 — 다른 보유 종목 청산 의무 보존.
    """
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(
            strategy_id="volatility_breakout", name="VB", weight=1.0, enabled=True,
            params={"tradable_boards": ["main"]},
        ),
        exit_signal=Signal.STOP_LOSS,
    )
    # 두 종목 보유
    vb.state.positions["042700"] = Position(
        ticker="042700", buy_price=100_000, quantity=1,
        order_no="O-1", strategy_id="volatility_breakout",
    )
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=10,
        order_no="O-2", strategy_id="volatility_breakout",
    )
    registry.register(vb)

    # 042700 만 매도 진행 중
    order_engine = _make_order_engine_with_selling({"042700"})
    risk = RiskManager(registry, order_engine)

    # 042700 tick — skip 되어야 함
    await risk.on_tick("042700", current_price=92_000, open_price=100_000, change_rate=-8.0)
    # 005930 tick — 정상 평가되어야 함
    await risk.on_tick("005930", current_price=64_000, open_price=70_000, change_rate=-8.57)

    # 042700: check_exit_signal skip
    exit_tickers = [call[0] for call in vb.exit_calls]
    assert "042700" not in exit_tickers, (
        f"매도 진행 중 042700 은 skip. 실제 호출={exit_tickers}"
    )
    # 005930: check_exit_signal 정상 호출
    assert "005930" in exit_tickers, (
        f"매도 진행 안 한 005930 은 정상 평가. 실제 호출={exit_tickers}"
    )
    # execute_sell — 005930 만 1회
    assert order_engine.execute_sell.call_count == 1
    assert order_engine.execute_sell.call_args.args[0] == "005930"
