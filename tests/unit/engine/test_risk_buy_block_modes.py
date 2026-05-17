"""사이클 8 (2026-05-18) Red — `risk.on_tick` 4 모드 매수 가드 분기.

요구 행위:
- HARD blocked → 매수 skip (사이클 2 회귀)
- WARN blocked → 매수 허용 + WARNING 로그 (`[buy_block_warn] strategy=... reasons=...`)
- SOFT blocked → 매수 허용 + quantity ×0.5 (최소 1주)
- OFF → 가드 자체 비활성, 매수 신호 그대로 발사
- 청산 신호는 모든 모드에서 정상 (가드 무관)

`get_current_regime()` + `BuyBlockState` 를 monkeypatch 로 제어.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_mock_strategy(strategy_id: str = "momentum"):
    state = MagicMock()
    state.buy_disabled = False
    state.positions = {}
    state.signal_count_today = 0
    state.total_investment = 1_000_000
    state.is_low_funds_blocked.return_value = False
    state.has_position.return_value = False

    s = MagicMock()
    s.strategy_id = strategy_id
    s.state = state
    s.config = MagicMock()
    s.config.params = {}
    s.is_daily_loss_exceeded.return_value = False
    s.check_buy_signal.return_value = None
    s.check_exit_signal.return_value = None
    # SOFT 모드용 calc_buy_quantity — 수량 측정용
    s.calc_buy_quantity.return_value = 10
    return s


def _make_risk():
    from src.engine.risk import RiskManager

    registry = MagicMock()
    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm, registry, order_engine


def _patch_buy_block_state(monkeypatch, *, mode, blocked, soft_multiplier=1.0, reasons=None):
    """`MarketRegime.get_buy_block_state()` async 메서드를 BuyBlockState 로 monkeypatch."""
    from src.engine import market_regime as mr
    from src.engine import risk as risk_mod
    from src.engine.market_regime import BuyBlockState, MarketRegime  # type: ignore

    state = BuyBlockState(
        mode=mode,
        blocked=blocked,
        soft_multiplier=soft_multiplier,
        reasons=reasons or [],
    )

    # MarketRegime 인스턴스에 get_buy_block_state 가 state 반환하도록 fake regime 주입
    async def _fake_get_state(self):
        return state

    monkeypatch.setattr(MarketRegime, "get_buy_block_state", _fake_get_state)

    fake_regime = MarketRegime(regime="defensive" if blocked else "neutral")
    monkeypatch.setattr(risk_mod, "get_current_regime", lambda: fake_regime)
    return state


@pytest.fixture(autouse=True)
def _patch_session_tracker(monkeypatch):
    from src.engine import risk as risk_mod
    monkeypatch.setattr(
        risk_mod.session_tracker, "is_tradable",
        lambda strategy_id, params: True,
    )


# ---------------------------------------------------------------------------
# HARD 모드 (회귀 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hard_mode_blocked_skips_buy(monkeypatch):
    """HARD 모드 + 가드 발동 → execute_buy 호출 안 함 (사이클 2 회귀)."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(
        monkeypatch, mode="HARD", blocked=True, reasons=["regime=defensive"],
    )

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_not_awaited()


@pytest.mark.asyncio
async def test_hard_mode_not_blocked_allows_buy(monkeypatch):
    """HARD 모드 + 가드 미발동 → 정상 매수."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(monkeypatch, mode="HARD", blocked=False, reasons=[])

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()


# ---------------------------------------------------------------------------
# WARN 모드
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_warn_mode_blocked_allows_buy_with_warning_log(monkeypatch, caplog):
    """WARN 모드 + 가드 발동 → 매수 허용 + WARNING 로그."""
    import logging
    from src.engine.strategy_base import Signal

    caplog.set_level(logging.WARNING, logger="src.engine.risk")

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(
        monkeypatch, mode="WARN", blocked=False, soft_multiplier=1.0,
        reasons=["regime=defensive", "vix=27.0 > 25.0"],
    )

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    # 매수는 허용
    order_engine.execute_buy.assert_awaited_once()
    # WARNING 로그가 출력되어야 함 — `[buy_block_warn]` prefix
    assert any(
        "[buy_block_warn]" in r.message and r.levelno == logging.WARNING
        for r in caplog.records
    ), f"WARN 로그 미출력: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# SOFT 모드 — quantity ×0.5
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_soft_mode_blocked_halves_quantity(monkeypatch):
    """SOFT 모드 + 가드 발동 → execute_buy 호출하지만 OrderEngine 에 soft_multiplier 전달.

    구현 옵션 — 가장 안전한 방식: `execute_buy(ticker, current_price, strategy, soft_multiplier=0.5)` kwarg
    전달. OrderEngine 이 quantity = max(1, int(qty * soft_multiplier)) 적용.
    본 테스트는 `execute_buy` 호출의 kwarg 검증.
    """
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(
        monkeypatch, mode="SOFT", blocked=False, soft_multiplier=0.5,
        reasons=["regime=defensive"],
    )

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    # 매수는 허용
    order_engine.execute_buy.assert_awaited_once()
    # soft_multiplier kwarg 전달 검증
    call = order_engine.execute_buy.await_args
    # kwargs 또는 positional 모두 허용 — soft_multiplier 가 0.5 여야
    sm = call.kwargs.get("soft_multiplier")
    assert sm == 0.5, f"execute_buy 에 soft_multiplier=0.5 전달 안됨: kwargs={call.kwargs}"


@pytest.mark.asyncio
async def test_soft_mode_not_blocked_does_not_pass_multiplier(monkeypatch):
    """SOFT 모드 + 가드 미발동 → soft_multiplier=1.0 (또는 미전달) — 정상 quantity."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(
        monkeypatch, mode="SOFT", blocked=False, soft_multiplier=1.0,
        reasons=[],
    )

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()
    call = order_engine.execute_buy.await_args
    sm = call.kwargs.get("soft_multiplier", 1.0)
    assert sm == 1.0


# ---------------------------------------------------------------------------
# OFF 모드 — 가드 비활성
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_off_mode_disables_guard(monkeypatch):
    """OFF 모드 → 가드 평가 자체 비활성. defensive 인데도 매수 허용."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(
        monkeypatch, mode="OFF", blocked=False, soft_multiplier=1.0, reasons=[],
    )

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_awaited_once()


# ---------------------------------------------------------------------------
# 청산은 4 모드 모두 정상 (가드 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["OFF", "WARN", "SOFT", "HARD"])
async def test_exit_signal_unaffected_by_any_mode(monkeypatch, mode):
    """모든 모드에서 청산은 정상 실행 (가드 무관)."""
    from src.engine.strategy_base import Position, Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    pos = Position(
        ticker="005930", buy_price=68000, quantity=1, order_no="ord-1",
        strategy_id="momentum",
    )
    strategy.state.positions = {"005930": pos}
    strategy.state.has_position.return_value = True
    strategy.check_exit_signal.return_value = Signal.STOP_LOSS
    strategy.check_buy_signal.return_value = None
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(monkeypatch, mode=mode, blocked=True, reasons=["x"])

    await rm.on_tick(ticker="005930", current_price=62000, open_price=68000, change_rate=-8.5)

    order_engine.execute_sell.assert_awaited_once()
    order_engine.execute_buy.assert_not_awaited()


# ---------------------------------------------------------------------------
# 회귀 보존 — 기존 cycle-2 동작 (defensive → HARD 차단)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cycle2_regression_defensive_hard_blocks(monkeypatch):
    """사이클 2 회귀 — DB 미설정(기본 HARD) + defensive → 매수 차단."""
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk()
    strategy = _make_mock_strategy("momentum")
    strategy.check_buy_signal.return_value = Signal.BUY
    registry.enabled.return_value = [strategy]
    registry.is_ticker_blocked_for_buy.return_value = False

    _patch_buy_block_state(
        monkeypatch, mode="HARD", blocked=True,
        reasons=["regime=defensive (방어)"],
    )

    await rm.on_tick(ticker="005930", current_price=70000, open_price=69000, change_rate=1.0)

    order_engine.execute_buy.assert_not_awaited()
