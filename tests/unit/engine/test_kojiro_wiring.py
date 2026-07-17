"""고지로 배선 회귀 가드 — 등록/멀티데이/폴루프 공유순차/PARAM_RANGES 정합.

핵심 (계획 §6 멀티데이/재시작 + 적대검증):
- kojiro ∈ _MULTIDAY_STRATEGIES AND check_force_clear()==[] (결합 가드, obs-M/restart-H2).
- Position(kojiro, buy_date<today).is_next_day == False (익일청산 큐 미편입).
- entry-H: 공유 순차 폴루프 → donchian∩kojiro 동일 종목 execute_buy 1회만 (double-buy 차단).
- kojiro 등록 + _SWING_POLL_STRATEGIES + _FALLBACK + PARAM_RANGES 정체성 제외.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import datetime as _dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler, _SWING_POLL_STRATEGIES
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.recommendation_engine import PARAM_RANGES, _FALLBACK_STRATEGIES

pytestmark = pytest.mark.unit

KST = _dt.timezone(_dt.timedelta(hours=9))


# ── 상수/멀티데이/폴백 ──

def test_swing_poll_strategies_constant():
    assert _SWING_POLL_STRATEGIES == ("donchian_swing", "kojiro")


def test_kojiro_multiday_and_force_clear_combined_guard():
    # 결합 가드: 둘 중 하나만이면 FAIL (배지 오표시 / 15:20 강제청산 소멸 차단)
    assert "kojiro" in Position._MULTIDAY_STRATEGIES
    strat = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.1))
    assert strat.check_force_clear() == []


def test_kojiro_position_is_next_day_false():
    yesterday = _dt.datetime.now(KST).date() - _dt.timedelta(days=3)
    pos = Position(ticker="005930", buy_price=10000, quantity=1, order_no="O",
                   strategy_id="kojiro", buy_date=yesterday)
    # 멀티데이 → 익일청산 대상 아님 (재시작 복구 후 강제 매도 차단, restart-H2)
    assert pos.is_next_day is False


def test_kojiro_in_fallback_strategies():
    assert "kojiro" in _FALLBACK_STRATEGIES


def test_kojiro_identity_params_excluded_from_param_ranges():
    p = KojiroStrategy.DEFAULT_PARAMS
    # 정체성/손절 배수 = AI 자동튜닝 제외 (obs-M)
    for key in ("ema_short", "ema_mid", "ema_long", "macd_signal", "atr_period",
                "stop_atr", "trail_atr", "atr_ratio_min", "atr_ratio_max",
                "gap_up_skip_pct", "gap_down_skip_pct"):
        assert key not in PARAM_RANGES, f"{key} 는 PARAM_RANGES 편입 금지"
    # atr_trail_mult(전역 PARAM_RANGES 키) 재사용 금지
    assert "atr_trail_mult" not in p


def test_kojiro_registered_in_scheduler_source():
    # 전체 인스턴스화(무거움) 대신 등록 블록 소스 확인.
    import inspect
    src = inspect.getsource(TradingScheduler)
    assert 'strategy_id="kojiro"' in src
    assert "KojiroStrategy(" in src
    assert "registry.register(kojiro)" in src


# ── entry-H: 공유 순차 폴루프 double-buy 차단 ──

class _FakeSwing(StrategyBase):
    """스윙 폴 인터페이스만 모킹 (strategy_id 파라미터화)."""

    def __init__(self, strategy_id: str, scanned: list[str]):
        super().__init__(StrategyConfig(strategy_id=strategy_id, name=strategy_id,
                                        weight=0.2, enabled=True))
        self._scanned_tickers = list(scanned)
        self._bought_today: set[str] = set()

    async def prepare(self) -> None:
        pass

    def get_scanned_tickers(self) -> list[str]:
        return list(self._scanned_tickers)

    def check_buy_signal(self, ticker, current_price, open_price) -> Signal:
        if ticker in self._bought_today:
            return Signal.NONE
        self._bought_today.add(ticker)
        return Signal.BUY

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 1


@contextlib.contextmanager
def _freeze_kst(hh, mm):
    # datetime 모듈 클래스 자체를 patch — 함수-로컬 `from datetime import datetime` 전파.
    import datetime as _dtmod
    base_kst = _dt.datetime(2026, 5, 8, hh, mm, tzinfo=KST)
    real = _dtmod.datetime

    class _F(_dtmod.datetime):
        @classmethod
        def now(cls, tz=None):
            return base_kst if tz is not None else base_kst.replace(tzinfo=None)

    _dtmod.datetime = _F
    try:
        yield
    finally:
        _dtmod.datetime = real


async def test_shared_sequential_poll_prevents_double_buy():
    """donchian∩kojiro 동일 종목 X → 공유 순차 폴루프에서 execute_buy 1회만."""
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._pending_next_day_clear = set()
    sched._running = True
    ds = _FakeSwing("donchian_swing", ["005930"])
    kj = _FakeSwing("kojiro", ["005930"])
    sched.registry.register(ds)
    sched.registry.register(kj)

    # execute_buy 가 실제처럼 pending_buys 등록 (전략 A 등록 → 전략 B is_blocked 차단)
    async def _exec(ticker, current_price, st, *, soft_multiplier=1.0):
        st.state.pending_buys.add(ticker)
    sched.order_engine = MagicMock()
    sched.order_engine.execute_buy = AsyncMock(side_effect=_exec)

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}
    with _freeze_kst(9, 10), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)), \
         patch("src.engine.scanner.kis_ws") as _ws:
        _ws.subscribe = AsyncMock()

        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop

    # 동일 종목 005930 은 정확히 1회만 매수 (donchian 먼저 → kojiro 차단)
    assert sched.order_engine.execute_buy.call_count == 1
    called_tickers = [c.args[0] for c in sched.order_engine.execute_buy.call_args_list]
    assert called_tickers == ["005930"]
