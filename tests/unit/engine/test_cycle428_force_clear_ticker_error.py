"""cycle428(F-422-1, 항목 3) — 15:20 강제 청산 종목별 `try/except`.

자문 = `_workspace/domain_consult/2026-10-10_f422_1_fallback_network_error.md`
「정량 권고 3」. `_force_clear_main_only` 의 종목 루프에 예상 밖 예외 하나가 나면
그 종목만 `[force_clear_ticker_error]` ERROR 로 남기고 **재발사 없이** 다음
종목으로 넘어간다 — 전체 루프가 끊기면 그날 15:30 `_scan_loop` 재기동·20:00
자문·21:30 정산까지 전부 잃는다(회귀 시나리오 S8).

시나리오 S6~S8(정규장 15:20) 은 `execute_sell` 자체의 행위를 바꾸지 않는다 —
이 테스트는 scheduler 쪽 종목 루프의 격리만 검증한다.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.scheduler import TradingScheduler
from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _freeze_at_force_clear_time():
    with freeze_time("2026-05-15 15:20:30"):
        yield


def _vb_with_two_positions(sched: TradingScheduler):
    vb = sched.registry.get("volatility_breakout")
    assert vb is not None
    vb.config.enabled = True
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=100, quantity=1,
        order_no="O-1", strategy_id="volatility_breakout", buy_date="2026-05-15",
    )
    vb.state.positions["000660"] = Position(
        ticker="000660", buy_price=200, quantity=1,
        order_no="O-2", strategy_id="volatility_breakout", buy_date="2026-05-15",
    )
    return vb


def _records(caplog, level: int, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == level and r.getMessage().startswith(prefix)
    ]


@pytest.mark.asyncio
async def test_s8_ticker_exception_is_isolated_and_loop_continues(caplog):
    """S8 — 한 종목의 예상 밖 예외(가짜 RuntimeError) → `[force_clear_ticker_error]`
    ERROR 1행 · 그 종목 재발사 0 · 다음 종목은 그대로 청산 발사."""
    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    sched = TradingScheduler()
    sched._running = True
    _vb_with_two_positions(sched)

    calls: list[str] = []

    async def _execute_sell(ticker, signal, strategy_id, **kwargs):
        calls.append(ticker)
        if ticker == "005930":
            raise RuntimeError("전송 오류")

    with patch.object(sched.order_engine, "execute_sell", new=AsyncMock(side_effect=_execute_sell)), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()

    assert calls == ["005930", "000660"], (
        "한 종목 예외가 루프를 끊었거나 그 종목을 재발사했다 — "
        f"실제 호출 순서: {calls}"
    )
    err = _records(caplog, logging.ERROR, "[force_clear_ticker_error] ")
    assert len(err) == 1
    assert "ticker=005930" in err[0]
    assert "strategy=volatility_breakout" in err[0]
    assert "RuntimeError" in err[0]


@pytest.mark.asyncio
async def test_s6_normal_clear_has_no_error_marker(caplog):
    """S6(대조) — 정상 청산은 `[force_clear_ticker_error]` 가 전혀 안 뜬다."""
    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    sched = TradingScheduler()
    sched._running = True
    _vb_with_two_positions(sched)

    execute_sell_mock = AsyncMock()
    with patch.object(sched.order_engine, "execute_sell", new=execute_sell_mock), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()

    sell_calls = [c for c in execute_sell_mock.await_args_list if c.args[2] == "volatility_breakout"]
    assert len(sell_calls) == 2
    assert sell_calls[0].args[1] == Signal.FORCE_CLEAR
    assert _records(caplog, logging.ERROR, "[force_clear_ticker_error] ") == []
