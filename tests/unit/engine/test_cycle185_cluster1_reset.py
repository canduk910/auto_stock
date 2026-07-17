"""사이클 185 클러스터 ① Red — 전략 인스턴스 상태 일일 미리셋 (strat-2~5).

승인 계획 `~/.claude/plans/hazy-prancing-cookie.md` + Red 설계
`_workspace/red/cycle185_cluster1_reset.md` + domain-expert 자문
`_workspace/domain_consult/cycle185_position_closed_cleanup.md`.

**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

결함:
- `scheduler._reset_daily_state()` 가 registry 순회에서 `strategy.state.*` 만 비우고
  전략 인스턴스 자신의 dict/set 필드는 미참조. 전략은 프로세스 생애 싱글톤 →
  영업일 가로질러 누적. 4건 잔존:
  | strat-4 momentum `_prev_prdy_rate` (transient) | 익일 첫 틱 갭상승 거짓 돌파 즉시 매수 |
  | strat-3 BFB `_breakout_first_seen` (transient, L978 고아) | retention 가드 우회 |
  | strat-2 LTV `_limit_up_reached` (보유결합) | 재매수 종목 전일 상한가 모드 잔존 |
  | strat-5 BFB `_partial_exit` (보유결합) | 재진입 종목 익절 영구 억제 |

두 메커니즘 분리:
- 메커니즘 1 (transient = 매수 전 전용) → 20:10 일괄 리셋 (`_reset_daily_state` 배선).
- 메커니즘 2 (보유결합 = 청산 모드) → 전량 매도 체결 시점 정리 (`on_position_closed` hook).

가드 → Red/Green 분류:
- 메커니즘 1: G1-MOM-RESET / G1-BFB-RESET / G1-WIRING-ISO = Red.
  G1-MOM-LEAK-CONTROL = 특성 문서 (양쪽 PASS).
- 메커니즘 2 Red: G2-LTV-DISCARD / G2-LTV-REBUY-FRESH / G2-LTV-CYCLE142-SEQUENCE /
  G2-BFB-POP / G2-BFB-REENTRY / G2-SECONDARY-COMMON / G2-OE-ISO.
  양쪽 PASS (불변식 SAFETY): G2-LTV-HELD-SAFETY / G2-LTV-PARTIAL-SAFETY / G2-BFB-PARTIAL-SAFETY.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 더미 전략 — 배선 격리 가드 (raise stub) 용
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": "KRX"},
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _make_momentum() -> MomentumStrategy:
    return MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="momentum", params={"exchange": "KRX"})
    )


def _make_ltv() -> LongTailVolatilityStrategy:
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="ltv", params={"exchange": "KRX"})
    )


def _make_bfb() -> BullFlagBreakoutStrategy:
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="bfb", params={"exchange": "KRX"})
    )


def _pos(
    ticker: str,
    strategy_id: str,
    *,
    buy_price: int = 10_000,
    quantity: int = 1,
    high_since_buy: int = 0,
) -> Position:
    return Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=quantity,
        order_no="O-PRE",
        strategy_id=strategy_id,
        high_since_buy=high_since_buy,
    )


def _build_scheduler():
    from src.engine.scheduler import TradingScheduler

    return TradingScheduler()


@contextlib.contextmanager
def _isolate_scheduler(sched, strategies):
    """`_reset_daily_state` 의 registry 순회만 노출, OrderEngine/RiskManager 격리 (cycle61 답습)."""
    with patch.object(sched.registry, "all", return_value=strategies), patch.object(
        sched,
        "order_engine",
        MagicMock(
            _selling=set(),
            _filled_qty={},
            _order_qty={},
            _order_strategy={},
            _order_ticker={},
            _pending_buy_orders={},
            _pending_cancel_tasks={},
            reset_daily_state=MagicMock(),
        ),
    ), patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())):
        yield


# ---------------------------------------------------------------------------
# order_engine 매도 체결 mock 픽스처 (cycle147 패턴 재사용)
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_insert_trade(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "insert_trade", mock)
    return mock


@pytest.fixture
def mock_delete_position(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", mock)
    return mock


@pytest.fixture
def mock_update_trade_status(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """affected=1 반환 → 보정 INSERT 분기 미진입 (cycle147 답습)."""
    mock = AsyncMock(return_value=1)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "update_trade_status", mock)
    return mock


@pytest.fixture
def mock_unsubscribe(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._unsubscribe_if_no_other_strategy",
        mock,
    )
    return mock


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", mock)
    return mock


@pytest.fixture
def mock_strategy_exchange(monkeypatch: pytest.MonkeyPatch):
    async def _fake(self, strategy_id, *, ticker=None):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async", _fake
    )
    return _fake


@pytest.fixture
def mock_get_balance(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """secondary hook reconciliation 의 get_balance() 1회 호출 격리 (cycle 59 CI hang 차단)."""
    mock = AsyncMock(return_value=([], None))
    import src.api.balance as _balance

    monkeypatch.setattr(_balance, "get_balance", mock)
    return mock


# ===========================================================================
# 메커니즘 1 — transient 상태 일일 리셋 (strat-3 BFB, strat-4 momentum)
# ===========================================================================
class TestMechanism1ResetDailyState:
    """`scheduler._reset_daily_state()` registry 순회에 per-strategy `_reset_daily_state()` 배선."""

    def test_G1_MOM_RESET_momentum_prev_prdy_rate_cleared(self) -> None:
        """G1-MOM-RESET (Red): 전일 seed → reset → `_prev_prdy_rate=={}` + 첫 틱 기록만 NONE.

        현재 FAIL = 배선 부재 → dict 미클리어 → 익일 첫 틱 즉시 거짓 돌파 BUY.
        """
        mom = _make_momentum()
        mom._prev_prdy_rate["005930"] = 28.0  # 전일 잔존
        sched = _build_scheduler()
        with _isolate_scheduler(sched, [mom]):
            sched._reset_daily_state()

        assert mom._prev_prdy_rate == {}, (
            "momentum _prev_prdy_rate 미클리어 → 익일 첫 틱 전일값 비교 거짓 돌파"
        )

        # 익일 첫 틱 (change_rate=+29.5%) — dict 비었으므로 기록만 NONE (즉시 BUY 아님)
        from src.engine import scanner as _scanner

        _scanner.ticker_prev_close["005930"] = 10_000
        try:
            sig = mom.check_buy_signal("005930", 12_950, 12_950)  # +29.5%
        finally:
            _scanner.ticker_prev_close.pop("005930", None)
        assert sig == Signal.NONE, "리셋 후 첫 틱은 기록만 (거짓 돌파 차단)"

    def test_G1_MOM_LEAK_CONTROL_seed_without_reset_immediate_buy(self) -> None:
        """G1-MOM-LEAK-CONTROL (특성, 양쪽 PASS): 리셋 미발생 시 seed 잔존 → 첫 틱 즉시 BUY.

        리셋 필요성 동기 문서화 — 전일 28% seed + 익일 첫 틱 29.5% → prev<29<=cur 돌파 즉시 매수.
        """
        mom = _make_momentum()
        mom.state.total_investment = 10_000_000
        mom._prev_prdy_rate["005930"] = 28.0  # 전일 잔존 (리셋 미발생)

        from src.engine import scanner as _scanner

        _scanner.ticker_prev_close["005930"] = 10_000
        try:
            sig = mom.check_buy_signal("005930", 12_950, 12_950)  # +29.5%
        finally:
            _scanner.ticker_prev_close.pop("005930", None)
        assert sig == Signal.BUY, "seed 잔존 시 첫 틱 즉시 거짓 돌파 매수 (리셋 필요성 동기)"

    def test_G1_BFB_RESET_breakout_first_seen_cleared(self) -> None:
        """G1-BFB-RESET (Red): 전일 retention seed → reset → `_breakout_first_seen=={}`.

        현재 FAIL = BFB `_reset_daily_state`(L978) 고아 (호출처 0건) → retention 가드 우회.
        """
        bfb = _make_bfb()
        bfb._breakout_first_seen["005930"] = datetime.now(KST)
        sched = _build_scheduler()
        with _isolate_scheduler(sched, [bfb]):
            sched._reset_daily_state()

        assert bfb._breakout_first_seen == {}, (
            "BFB _reset_daily_state(L978) 고아 — 배선 부재로 전일 retention dict 잔존"
        )

    def test_G1_WIRING_ISO_raise_stub_swallowed_others_cleared(self) -> None:
        """G1-WIRING-ISO (Red, HIGH): raise stub 전략 first 주입 → 예외 삼킴 + 나머지 정상.

        (a) raise stub 호출됨 (배선 존재) — 현재 FAIL = 미호출.
        (b) 다른 전략 state.positions clear (loop 계속).
        (c) `_pending_next_day_clear` clear (loop 후 도달).
        NAIVE green (try/except 누락) 시 예외 전파 → (b)/(c) 미도달 FAIL.
        """
        raise_stub = _DummyStrategy("raise_stub")
        raise_stub._reset_daily_state = MagicMock(side_effect=RuntimeError("boom"))
        normal = _DummyStrategy("normal")
        normal.state.positions["005930"] = _pos("005930", "normal")

        sched = _build_scheduler()
        sched._pending_next_day_clear.add(("005930", "normal"))

        with _isolate_scheduler(sched, [raise_stub, normal]):
            # 예외 전파 없이 완료 (try/except 격리) — naive green 은 여기서 raise
            sched._reset_daily_state()

        # (a) raise stub 호출됨 — 배선 존재 검증 (Red FAIL = 미호출)
        raise_stub._reset_daily_state.assert_called_once()
        # (b) 다른 전략 state clear (loop 계속)
        assert normal.state.positions == {}, "예외 격리 후 다음 전략 state clear 도달 의무"
        # (c) 익일 청산 set clear (loop 후 도달)
        assert sched._pending_next_day_clear == set(), "loop 후 _pending_next_day_clear clear 도달 의무"


# ===========================================================================
# 메커니즘 2 — 보유결합 상태 매도 체결 시점 정리 (strat-2 LTV, strat-5 BFB)
# ===========================================================================
class TestMechanism2OnPositionClosed:
    """`StrategyBase.on_position_closed(ticker)` no-op + LTV/BFB override + order_engine 2 site 배선."""

    # ---- LTV `_limit_up_reached` ------------------------------------------
    @pytest.mark.asyncio
    async def test_G2_LTV_DISCARD_full_sell_discards_flag(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-LTV-DISCARD (Red, HIGH): 전량 매도 → on_position_closed → `_limit_up_reached` discard."""
        ltv = _make_ltv()
        ltv.state.positions["093370"] = _pos("093370", "long_tail_volatility")
        ltv._limit_up_reached.add("093370")
        reg = StrategyRegistry()
        reg.register(ltv)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "long_tail_volatility"
        engine._order_ticker["O1"] = "093370"

        await engine.handle_execution_notice("093370", "O1", "SELL", 10_000, 1)

        assert "093370" not in ltv.state.positions, "전량 체결 → positions del"
        assert "093370" not in ltv._limit_up_reached, (
            "전량 매도 → on_position_closed → _limit_up_reached discard (재매수 누설 차단)"
        )

    @pytest.mark.asyncio
    async def test_G2_LTV_REBUY_FRESH_reentry_today_mode(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-LTV-REBUY-FRESH (Red, HIGH): 매도→discard 후 재매수 → 당일 모드 -3% STOP_LOSS.

        현재 FAIL = stale flag → 상한가 모드 → -3.5% > -5% NONE + check_force_clear 제외.
        """
        ltv = _make_ltv()
        ltv.state.positions["093370"] = _pos("093370", "long_tail_volatility", buy_price=10_000)
        ltv._limit_up_reached.add("093370")
        reg = StrategyRegistry()
        reg.register(ltv)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "long_tail_volatility"
        engine._order_ticker["O1"] = "093370"

        await engine.handle_execution_notice("093370", "O1", "SELL", 10_000, 1)
        assert "093370" not in ltv._limit_up_reached, "재매수 fresh 의 선결 조건 = 매도 시 discard"

        # 재매수 (fresh, buy_date=today → is_next_day False)
        ltv.state.sold_today.discard("093370")
        ltv.state.positions["093370"] = _pos("093370", "long_tail_volatility", buy_price=10_000)

        # check_exit -3.5% → 당일 모드 STOP_LOSS (intraday -3%, overnight -5% 아님)
        sig = ltv.check_exit_signal("093370", 9_650, 9_650)  # -3.5%
        assert sig == Signal.STOP_LOSS, "재매수 fresh → 당일 모드 -3% 손절 (상한가 -5% 아님)"
        assert "093370" in ltv.check_force_clear(), "재매수 fresh → 15:20 강제청산 대상 포함"

    def test_G2_LTV_HELD_SAFETY_reset_does_not_touch_flag(self) -> None:
        """G2-LTV-HELD-SAFETY (양쪽 PASS, HIGH SAFETY): 보유 중 일괄 리셋이 flag 절대 미접촉.

        mechanism1 `_reset_daily_state` 가 보유결합 flag 를 건드리지 않음 (밤샘 청산모드 보존).
        """
        ltv = _make_ltv()
        ltv.state.positions["093370"] = _pos("093370", "long_tail_volatility")
        ltv._limit_up_reached.add("093370")

        sched = _build_scheduler()
        with _isolate_scheduler(sched, [ltv]):
            sched._reset_daily_state()

        assert "093370" in ltv._limit_up_reached, (
            "일괄 리셋이 보유결합 flag 미접촉 — 밤샘 보유 청산모드 보존"
        )

    @pytest.mark.asyncio
    async def test_G2_LTV_PARTIAL_SAFETY_partial_keeps_flag_and_mode(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-LTV-PARTIAL-SAFETY (양쪽 PASS, HIGH): 부분 체결 → 잔량 보유 + flag 유지 + 상한가 모드 보존.

        full-fill 한정 hook → 부분 체결은 on_position_closed 미발화 → 잔량 청산정책(-5% overnight) 보존.
        """
        ltv = _make_ltv()
        ltv.state.positions["093370"] = _pos(
            "093370", "long_tail_volatility", buy_price=10_000, quantity=10
        )
        ltv._limit_up_reached.add("093370")
        reg = StrategyRegistry()
        reg.register(ltv)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "long_tail_volatility"
        engine._order_ticker["O1"] = "093370"
        engine._order_qty["O1"] = 10  # ordered 10
        engine._schedule_cancel_and_reorder = MagicMock()  # 잔여 취소 task 격리

        await engine.handle_execution_notice("093370", "O1", "SELL", 10_000, 4)  # partial 4/10

        assert "093370" in ltv.state.positions, "부분 체결 → 잔량 보유"
        assert "093370" in ltv._limit_up_reached, "부분 체결 → flag 유지 (잔량 청산모드 보존)"

        # 잔량 check_exit -3.5% → 상한가 모드 (overnight -5%) → NONE (당일 -3% 강등 아님)
        sig = ltv.check_exit_signal("093370", 9_650, 9_650)
        assert sig == Signal.NONE, "상한가 모드 잔량 -5% overnight 보존 (-3% 당일 강등 아님)"

    @pytest.mark.asyncio
    @freeze_time("2024-06-27 08:00:00")
    async def test_G2_LTV_CYCLE142_SEQUENCE_add_then_sell_discards(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-LTV-CYCLE142-SEQUENCE (Red, HIGH, freezegun): 08:00 add → 보유 flag → 매도 → discard.

        순서역전 부재 — 매도된 X 는 미재부착 (cycle142 재확립은 보유 종목 한정).
        현재 FAIL = 매도 후 discard 부재 → flag 잔존.
        """
        ltv = _make_ltv()
        ltv.state.positions["093370"] = _pos("093370", "long_tail_volatility")
        # 08:00 cycle142 재확립 시뮬레이션 (보유 종목 상한가 모드 재진입)
        ltv._limit_up_reached.add("093370")
        assert "093370" in ltv._limit_up_reached, "보유 중 flag 유지 (cycle142 재확립)"

        reg = StrategyRegistry()
        reg.register(ltv)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "long_tail_volatility"
        engine._order_ticker["O1"] = "093370"

        # 장중 전량 매도
        await engine.handle_execution_notice("093370", "O1", "SELL", 10_000, 1)

        assert "093370" not in ltv.state.positions, "전량 매도 → positions 소멸"
        assert "093370" not in ltv._limit_up_reached, (
            "전량 매도 후 discard — 매도된 X 미재부착 (순서역전 부재)"
        )

    # ---- BFB `_partial_exit` ----------------------------------------------
    @pytest.mark.asyncio
    async def test_G2_BFB_POP_full_sell_pops_partial_exit(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-BFB-POP (Red): 전량 매도 → on_position_closed → `_partial_exit` pop."""
        bfb = _make_bfb()
        bfb.state.positions["005930"] = _pos("005930", "bull_flag_breakout", buy_price=11_500)
        bfb._partial_exit["005930"] = True
        reg = StrategyRegistry()
        reg.register(bfb)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "bull_flag_breakout"
        engine._order_ticker["O1"] = "005930"

        await engine.handle_execution_notice("005930", "O1", "SELL", 14_000, 1)

        assert "005930" not in bfb.state.positions, "전량 체결 → positions del"
        assert "005930" not in bfb._partial_exit, "전량 매도 → on_position_closed → _partial_exit pop"

    @pytest.mark.asyncio
    async def test_G2_BFB_REENTRY_measured_move_refires(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-BFB-REENTRY (Red): 매도→pop 후 재진입 + measured-move 도달 → TRAILING_STOP 발화.

        현재 FAIL = stale `_partial_exit=True` → 영구 억제 (NONE).
        """
        bfb = _make_bfb()
        bfb._candidates["005930"] = {
            "pole_high": 12_000,
            "pole_start": 10_000,
            "flag_high": 12_000,
            "flag_low": 11_000,
            "atr14": 100,
        }
        bfb.state.positions["005930"] = _pos("005930", "bull_flag_breakout", buy_price=11_500)
        bfb._partial_exit["005930"] = True  # 전일 stale (억제 상태)
        reg = StrategyRegistry()
        reg.register(bfb)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "bull_flag_breakout"
        engine._order_ticker["O1"] = "005930"

        await engine.handle_execution_notice("005930", "O1", "SELL", 14_000, 1)
        assert "005930" not in bfb._partial_exit, "재진입 fresh 의 선결 조건 = 매도 시 pop"

        # 재진입 (fresh)
        bfb.state.sold_today.discard("005930")
        bfb.state.positions["005930"] = _pos("005930", "bull_flag_breakout", buy_price=11_500)

        # measured_target = flag_high(12000) + (pole_high - pole_start)(2000) = 14000
        sig = bfb.check_exit_signal("005930", 14_000, 14_000)
        assert sig == Signal.TRAILING_STOP, (
            "재진입 measured-move 재발화 (per-holding-period once-only, 영구 억제 아님)"
        )

    @pytest.mark.asyncio
    async def test_G2_BFB_PARTIAL_SAFETY_partial_keeps_suppression(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-BFB-PARTIAL-SAFETY (양쪽 PASS): 부분 체결 → `_partial_exit` 유지 (재발화 억제 보존).

        full-fill 한정 hook → 부분 체결은 미pop → 잔량 측정이동 재발화 억제 (이미 마킹).
        """
        bfb = _make_bfb()
        bfb._candidates["005930"] = {
            "pole_high": 12_000,
            "pole_start": 10_000,
            "flag_high": 12_000,
            "flag_low": 11_000,
            "atr14": 100,
        }
        bfb.state.positions["005930"] = _pos(
            "005930", "bull_flag_breakout", buy_price=11_500, quantity=10
        )
        bfb._partial_exit["005930"] = True  # measured-move 이미 마킹
        reg = StrategyRegistry()
        reg.register(bfb)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "bull_flag_breakout"
        engine._order_ticker["O1"] = "005930"
        engine._order_qty["O1"] = 10
        engine._schedule_cancel_and_reorder = MagicMock()

        await engine.handle_execution_notice("005930", "O1", "SELL", 14_000, 4)  # partial 4/10

        assert "005930" in bfb.state.positions, "부분 체결 → 잔량 보유"
        assert bfb._partial_exit.get("005930") is True, "부분 체결 → _partial_exit 유지 (억제 보존)"

        # 잔량 measured-move 재평가 → already_partial True → 억제 (재발화 아님)
        sig = bfb.check_exit_signal("005930", 14_000, 14_000)
        assert sig != Signal.TRAILING_STOP, "잔량 측정이동 억제 (이미 마킹, ATR 트레일링 경로)"

    # ---- secondary hook (execute_sell reconciliation) + 격리 --------------
    @pytest.mark.asyncio
    async def test_G2_SECONDARY_COMMON_insufficient_qty_reconciliation_discards(
        self,
        mock_place_order: AsyncMock,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_write_log: AsyncMock,
        mock_strategy_exchange,
        mock_get_balance: AsyncMock,
    ) -> None:
        """G2-SECONDARY-COMMON (Red, HIGH): execute_sell insufficient_quantity → positions pop + discard.

        외부 증발 포지션 (수동 HTS 매도) catch-all — reconciliation site(L793) 직후 on_position_closed.
        현재 FAIL = positions pop 만, flag 잔존.
        """
        ltv = _make_ltv()
        ltv.state.positions["093370"] = _pos(
            "093370", "long_tail_volatility", buy_price=10_000, quantity=10
        )
        ltv._limit_up_reached.add("093370")
        reg = StrategyRegistry()
        reg.register(ltv)
        engine = OrderEngine(reg)

        qty_reject = KisApiError(rt_cd="1", msg_cd="APBK1234", msg1="매도가능수량이 부족합니다.")
        mock_place_order.side_effect = [qty_reject]

        await engine.execute_sell("093370", Signal.STOP_LOSS, "long_tail_volatility")

        assert "093370" not in ltv.state.positions, "insufficient_quantity → positions 강제 정리"
        assert "093370" not in ltv._limit_up_reached, (
            "secondary hook (L793 직후) → on_position_closed discard (외부 증발 catch-all)"
        )

    @pytest.mark.asyncio
    async def test_G2_OE_ISO_raise_stub_swallowed_full_path_completes(
        self,
        mock_insert_trade: AsyncMock,
        mock_delete_position: AsyncMock,
        mock_update_trade_status: AsyncMock,
        mock_unsubscribe: AsyncMock,
    ) -> None:
        """G2-OE-ISO (Red, HIGH): on_position_closed raise stub → `_handle_sell_fill` 전량 분기 격리.

        (a) on_position_closed 호출됨 (배선) — 현재 FAIL = 미호출.
        (b) 예외 삼킴 — del positions / sold_today / DB delete / update / unsubscribe 모두 완료.
        NAIVE green (try/except 누락) 시 예외 전파 → (b) 후속 미완료 FAIL.
        """
        stub = _DummyStrategy("momentum")
        stub.on_position_closed = MagicMock(side_effect=RuntimeError("boom"))
        stub.state.positions["005930"] = _pos("005930", "momentum", buy_price=10_000)
        reg = StrategyRegistry()
        reg.register(stub)
        engine = OrderEngine(reg)
        engine._order_strategy["O1"] = "momentum"
        engine._order_ticker["O1"] = "005930"

        await engine.handle_execution_notice("005930", "O1", "SELL", 10_000, 1)

        # (a) 배선 존재 — on_position_closed 호출됨 (Red FAIL = 미호출)
        stub.on_position_closed.assert_called_once_with("005930")
        # (b) 예외 격리 — 매도 본류 전부 완료 (assert_awaited 는 미호출 시 자체 raise)
        assert "005930" not in stub.state.positions, "del positions 완료"
        assert "005930" in stub.state.sold_today, "sold_today.add 완료 (hook 예외 격리)"
        mock_delete_position.assert_awaited()  # DB delete 완료
        mock_update_trade_status.assert_awaited()  # update_trade_status 완료
        mock_unsubscribe.assert_awaited()  # unsubscribe 완료
