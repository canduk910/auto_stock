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
