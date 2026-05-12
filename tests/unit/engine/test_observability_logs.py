"""가설 검증 로깅 강화 (2026-05-12 G안 부수효과).

5종 가설을 운영자가 Grafana/Loki 에서 즉시 추적할 수 있도록 영문 prefix 로그 강화:
- [tick_coverage]   가설 B — 통합시세 silent inactive (확장)
- [breakout_open_confirm]  가설 C — 시가/Range 오염
- [tradable_skip]   가설 D — 보드 활성도 혼재 (분당 1회 emit)
- [stock_master_miss] 가설 E — stock_master 캐시 miss

가설 A([priority_drop]) 는 test_scanner_priority_order.py 에서 검증.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


KST_TZ = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reset_ticker_last_tick():
    from src.engine import scanner as scanner_module
    scanner_module.ticker_last_tick.clear()
    yield
    scanner_module.ticker_last_tick.clear()


# ===========================================================================
# 가설 B: [tick_coverage] 확장 필드 — ratio / stale_sample / last_tick_avg_age
# ===========================================================================
@pytest.mark.asyncio
async def test_tick_coverage_includes_ratio_and_stale_sample(caplog):
    """확장 형식: ratio + stale_sample + last_tick_avg_age 필드 노출."""
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket import kis_ws

    now = datetime.now(KST_TZ)
    scanner_module.ticker_last_tick.update({
        "000001": now - timedelta(seconds=5),    # fresh
        "000002": now - timedelta(seconds=30),   # fresh
        "000003": now - timedelta(seconds=120),  # stale
        "000004": now - timedelta(seconds=180),  # stale
        "000005": now - timedelta(seconds=240),  # stale
    })

    with patch.object(kis_ws, "get_subscribed_tickers",
                      return_value={"000001", "000002", "000003", "000004", "000005"}):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()):
            caplog.set_level(logging.INFO, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    msgs = [r.getMessage() for r in caplog.records if "[tick_coverage]" in r.getMessage()]
    assert len(msgs) == 1
    msg = msgs[0]
    # 신규 필드 검증
    assert "ratio=" in msg, "ratio 필드 노출 필요"
    assert "stale_sample=" in msg, "stale_sample 필드 노출 필요"
    assert "last_tick_avg_age=" in msg, "last_tick_avg_age 필드 노출 필요"
    # 기존 필드 보존
    assert "subscribed=5" in msg
    assert "fresh=2" in msg
    assert "stale=3" in msg


# ===========================================================================
# 가설 B: stale_ratio > 30% 시 WARNING 레벨 (가시성 강화)
# ===========================================================================
@pytest.mark.asyncio
async def test_tick_coverage_warning_when_stale_ratio_high(caplog):
    """stale 비율 30% 초과 시 WARNING 레벨."""
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket import kis_ws

    # 5종목 중 4종목 stale (80%) → WARNING
    now = datetime.now(KST_TZ)
    scanner_module.ticker_last_tick.update({
        "W1": now - timedelta(seconds=5),  # fresh
        # W2~W5 미등록 → stale
    })

    with patch.object(kis_ws, "get_subscribed_tickers",
                      return_value={"W1", "W2", "W3", "W4", "W5"}):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()) as mock_write_log:
            caplog.set_level(logging.WARNING, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    # WARNING 레벨 1행 노출
    warning_msgs = [r for r in caplog.records
                    if r.levelno == logging.WARNING and "[tick_coverage]" in r.getMessage()]
    assert len(warning_msgs) == 1, f"stale_ratio>30% 시 WARNING 1행 노출 필요"
    # system_logs 도 WARNING 으로
    write_calls = [c for c in mock_write_log.call_args_list if "[tick_coverage]" in str(c)]
    assert any(c.args[0] == "WARNING" for c in write_calls)


# ===========================================================================
# 가설 D: [tradable_skip] 분당 1회 emit
# ===========================================================================
# ===========================================================================
# 가설 D: [tradable_skip] 첫 60s 안에 emit 금지 (Codex 추가검토 2)
# ===========================================================================
@pytest.mark.asyncio
async def test_tradable_skip_does_not_emit_on_first_tick_within_60s(caplog):
    """RiskManager 신규 인스턴스에서 첫 tick 후 60s 미경과면 emit 0회.

    결함: `_last_tradable_emit_ts: float = 0.0` 초기화 → 첫 tradable=False tick 에서
    `now - 0.0 > 60` 즉시 emit. 60s 누적 가드 무력. 가드를 추가해 첫 emit 도
    충분한 누적 후 1회만 노출되어야 함.
    """
    from src.engine.risk import RiskManager
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    class _StubStrategy(StrategyBase):
        async def prepare(self):
            pass
        def check_buy_signal(self, ticker, current_price, open_price):
            return Signal.NONE
        def check_exit_signal(self, ticker, current_price, open_price):
            return Signal.NONE
        def calc_buy_quantity(self, current_price):
            return 0

    registry = StrategyRegistry()
    momentum = _StubStrategy(StrategyConfig(
        strategy_id="momentum", name="MOM", weight=1.0, enabled=True,
        params={"tradable_boards": ["krx_open", "main"]},
    ))
    registry.register(momentum)

    with patch.object(session_tracker, "_active", frozenset({MarketBoard.POST_NXT})):
        order_engine = MagicMock()
        order_engine.execute_buy = AsyncMock()
        order_engine.execute_sell = AsyncMock()

        risk = RiskManager(registry, order_engine)

        from src.engine import scanner
        scanner.ticker_prev_close["005930"] = 70000

        caplog.set_level(logging.INFO, logger="src.engine.risk")

        # 신규 RiskManager — 첫 tick 들. 60s 미경과
        for _ in range(10):
            await risk.on_tick("005930", 75000, 70000, 7.14)

    skip_msgs = [r.getMessage() for r in caplog.records if "[tradable_skip]" in r.getMessage()]
    assert len(skip_msgs) == 0, (
        f"신규 RiskManager 첫 60s 안에 [tradable_skip] emit 금지. 실제={skip_msgs}"
    )


@pytest.mark.asyncio
async def test_tradable_skip_emit_per_minute(caplog):
    """is_tradable=False skip 카운트를 분당 1회 [tradable_skip] INFO 로그로 노출."""
    from src.engine.risk import RiskManager
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    class _StubStrategy(StrategyBase):
        async def prepare(self):
            pass

        def check_buy_signal(self, ticker, current_price, open_price):
            return Signal.NONE

        def check_exit_signal(self, ticker, current_price, open_price):
            return Signal.NONE

        def calc_buy_quantity(self, current_price):
            return 0

    registry = StrategyRegistry()
    momentum = _StubStrategy(StrategyConfig(
        strategy_id="momentum", name="MOM", weight=1.0, enabled=True,
        params={"tradable_boards": ["krx_open", "main"]},
    ))
    registry.register(momentum)

    # 활성 보드 POST_NXT — momentum 의 tradable_boards 와 불일치
    with patch.object(session_tracker, "_active", frozenset({MarketBoard.POST_NXT})):
        order_engine = MagicMock()
        order_engine.execute_buy = AsyncMock()
        order_engine.execute_sell = AsyncMock()

        risk = RiskManager(registry, order_engine)

        from src.engine import scanner
        scanner.ticker_prev_close["005930"] = 70000

        caplog.set_level(logging.INFO, logger="src.engine.risk")

        # 1분 이내 여러 tick — 카운트만 누적, emit 안 됨
        for _ in range(5):
            await risk.on_tick("005930", 75000, 70000, 7.14)

        # 60s 이상 진행 후 emit
        risk._last_tradable_emit_ts = time.time() - 61

        # 추가 tick — emit 트리거
        await risk.on_tick("005930", 75000, 70000, 7.14)

    skip_msgs = [r.getMessage() for r in caplog.records if "[tradable_skip]" in r.getMessage()]
    assert len(skip_msgs) >= 1, "1분 이상 경과 후 [tradable_skip] 1행 노출 필요"
    msg = skip_msgs[-1]
    assert "momentum=" in msg
    assert "active_boards=" in msg


# ===========================================================================
# 가설 E: [stock_master_miss] miss / stale 분기 노출
# ===========================================================================
@pytest.mark.asyncio
async def test_stock_master_miss_logs_when_cache_empty():
    """`_strategy_exchange_async` 안에서 stock_master.get 이 None 반환 시 [stock_master_miss] reason=miss."""
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    # 전략 등록 — exchange="NXT" 로 시도, ticker 인자 전달
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

    class _ST(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a): return Signal.NONE
        def check_exit_signal(self, *a): return Signal.NONE
        def calc_buy_quantity(self, p): return 0

    registry = StrategyRegistry()
    st = _ST(StrategyConfig(
        strategy_id="momentum", name="M", weight=1.0, enabled=True,
        params={"exchange": "NXT"},
    ))
    registry.register(st)
    engine = OrderEngine(registry)

    with patch("src.db.stock_master.get", new=AsyncMock(return_value=None)), \
         patch("src.engine.order_engine.write_log", new=AsyncMock()) as mock_write_log:
        await engine._strategy_exchange_async("momentum", ticker="005930")

    # write_log 가 [stock_master_miss] reason=miss 로그를 호출했는지 확인
    miss_calls = [c for c in mock_write_log.call_args_list if "[stock_master_miss]" in str(c)]
    assert len(miss_calls) >= 1, "stock_master.get 결과 None 시 [stock_master_miss] 로그 노출 필요"
    msg = miss_calls[0].args[1]
    assert "reason=miss" in msg
    assert "ticker=005930" in msg
    assert "strategy=momentum" in msg


@pytest.mark.asyncio
async def test_stock_master_miss_stale_does_not_block_order_path():
    """Codex 추가검토 4 (2026-05-12): stock_master.is_stale 호출이 주문 경로를 블록하지 않아야 한다.

    결함: 기존 코드는 `_strategy_exchange_async` 안에서 `is_stale` 를 직접 await →
    Supabase round-trip 1회가 시장가 매수/매도 latency 에 직접 합산됨.
    수정: stale 체크/로깅을 `asyncio.create_task` 로 fire-and-forget 분리.
    `_strategy_exchange_async` 호출 자체는 `is_stale` 완료 *전* 반환되어야 함.
    """
    import asyncio as _asyncio
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    class _ST(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a): return Signal.NONE
        def check_exit_signal(self, *a): return Signal.NONE
        def calc_buy_quantity(self, p): return 0

    registry = StrategyRegistry()
    st = _ST(StrategyConfig(
        strategy_id="momentum", name="M", weight=1.0, enabled=True,
        params={"exchange": "NXT"},
    ))
    registry.register(st)
    engine = OrderEngine(registry)

    # `is_stale` 가 매우 느린 round-trip (0.3s) 을 시뮬레이션
    is_stale_completed = _asyncio.Event()

    async def _slow_is_stale(_t):
        await _asyncio.sleep(0.3)
        is_stale_completed.set()
        return True

    # stock_master.get 은 nxt_tradable=True 결과 반환 (stale 분기 진입은 별도 path)
    class _Basics:
        nxt_tradable = True

    with patch("src.db.stock_master.get", new=AsyncMock(return_value=_Basics())), \
         patch("src.db.stock_master.is_stale", new=_slow_is_stale), \
         patch("src.engine.order_engine.write_log", new=AsyncMock()):
        # _strategy_exchange_async 호출이 _slow_is_stale 완료 전에 반환되어야 함
        result = await _asyncio.wait_for(
            engine._strategy_exchange_async("momentum", ticker="005930"),
            timeout=0.1,  # is_stale 의 0.3s 보다 짧은 timeout — fire-and-forget 면 통과
        )

    assert result == "NXT"
    # 호출 직후 시점에는 is_stale 가 아직 완료 전이어야 함 (fire-and-forget 증거)
    assert not is_stale_completed.is_set(), (
        "_strategy_exchange_async 가 is_stale 완료를 기다리면 안 됨 (fire-and-forget 필요)"
    )

    # cleanup: 백그라운드 task 가 완료될 때까지 대기 (테스트 격리)
    await _asyncio.sleep(0.4)


# ===========================================================================
# 가설 C: [breakout_open_confirm] — 보드별 시가 확정 후 카운트 노출
# ===========================================================================
@pytest.mark.asyncio
async def test_breakout_open_confirm_log_format(caplog):
    """`_confirm_breakout_open_prices(board=...)` 호출 후 [breakout_open_confirm] 노출.

    형식: [breakout_open_confirm] board=BOARD strategy=SID confirmed=N empty=M sample={...}
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    class _BreakoutStub(StrategyBase):
        def __init__(self, config, scanned_with_open):
            super().__init__(config)
            self._scanned = list(scanned_with_open.keys())
            self._opens = dict(scanned_with_open)

        async def prepare(self): pass
        def check_buy_signal(self, *a): return Signal.NONE
        def check_exit_signal(self, *a): return Signal.NONE
        def calc_buy_quantity(self, p): return 0

        def get_scanned_tickers(self):
            return list(self._scanned)

        def confirm_open_price(self, ticker, board, open_price):
            self._opens[ticker] = open_price

        def get_targets_status(self):
            return {
                t: {
                    "boards": {"main": {"open_price": p, "target_price": 0}},
                    "open_price": p,
                }
                for t, p in self._opens.items()
            }

    sched = TradingScheduler.__new__(TradingScheduler)
    registry = StrategyRegistry()
    sched.registry = registry
    sched._pending_next_day_clear = set()

    vb = _BreakoutStub(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True),
        scanned_with_open={"V1": 10000, "V2": 0, "V3": 20000},  # confirmed=2, empty=1
    )
    registry.register(vb)

    # _confirm_breakout_open_prices 가 외부 fetch 를 하지 않도록 strategy.confirm_open_price 만 모의
    # 또는 직접 _emit_breakout_open_confirm 헬퍼를 검증 — 구현에 헬퍼가 신설된다고 가정
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    # 헬퍼 직접 호출 (구현은 _confirm_breakout_open_prices 안에서 호출)
    if hasattr(sched, "_emit_breakout_open_confirm"):
        sched._emit_breakout_open_confirm("main", vb)

        msgs = [r.getMessage() for r in caplog.records if "[breakout_open_confirm]" in r.getMessage()]
        assert len(msgs) >= 1
        msg = msgs[0]
        assert "board=main" in msg
        assert "strategy=volatility_breakout" in msg
        assert "confirmed=2" in msg
        assert "empty=1" in msg
        assert "sample=" in msg
    else:
        pytest.fail(
            "_emit_breakout_open_confirm 헬퍼가 scheduler 에 신설되어야 함 "
            "(가설 C — _confirm_breakout_open_prices 호출 직후 호출)"
        )
