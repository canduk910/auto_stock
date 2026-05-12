"""종목별 마지막 tick 수신 시각 추적 + 5분 주기 미수신 카운트 로깅 (Phase D).

결함 배경: 2026-05-11 운영. VB/LTV가 종일 시세를 받지 못했으나 구독은 정상이었고
"구독 완료" 로그까지 정상이라 운영 중에는 시세 수신 여부를 알 수 없었다.

본 테스트는 다음을 검증한다:

1. `scanner.ticker_last_tick: dict[str, datetime]` 글로벌 dict 존재
2. `RiskManager.on_tick` 호출 시 `ticker_last_tick[ticker]`가 호출 시점(KST)으로 갱신
3. `TradingScheduler._report_tick_coverage()` 가 KisWebSocket 구독 종목 중 최근 60초 이내 tick 수신
   비율을 카운트해 `INFO` 로그 1행 + `system_logs` 1행으로 노출 (prefix `[tick_coverage]`)
4. `KisWebSocket.get_subscribed_tickers()` 가 TICK 구독 종목만 반환
5. `_reset_daily_state()` 가 `ticker_last_tick.clear()` 수행
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


KST_TZ = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼: 각 테스트 시작 시 scanner.ticker_last_tick 비우기
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_ticker_last_tick():
    from src.engine import scanner as scanner_module

    scanner_module.ticker_last_tick.clear()
    yield
    scanner_module.ticker_last_tick.clear()


# ===========================================================================
# Case A: 구독 5종목 중 3종목 최근 30초 내 tick → fresh=3, stale=2
# ===========================================================================
@pytest.mark.asyncio
async def test_report_tick_coverage_fresh_and_stale_mixed(caplog):
    """3종목 fresh + 2종목 stale 분리 카운트."""
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket import kis_ws

    now = datetime.now(KST_TZ)
    scanner_module.ticker_last_tick.update({
        "000001": now - timedelta(seconds=5),
        "000002": now - timedelta(seconds=20),
        "000003": now - timedelta(seconds=55),
        "000004": now - timedelta(seconds=120),  # stale
        "000005": now - timedelta(seconds=600),  # stale
    })

    with patch.object(kis_ws, "get_subscribed_tickers",
                      return_value={"000001", "000002", "000003", "000004", "000005"}):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()) as mock_write_log:
            caplog.set_level(logging.INFO, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    # 로그 1행 노출
    coverage_msgs = [r for r in caplog.records if "[tick_coverage]" in r.getMessage()]
    assert len(coverage_msgs) == 1, f"로그가 정확히 1행 노출되어야 한다: {[r.getMessage() for r in caplog.records]}"
    msg = coverage_msgs[0].getMessage()
    assert "subscribed=5" in msg or "구독=5" in msg
    assert "fresh=3" in msg or "수신=3" in msg
    assert "stale=2" in msg or "미수신=2" in msg

    # system_logs 1행
    mock_write_log.assert_called_once()
    args, kwargs = mock_write_log.call_args
    log_payload = args[1] if len(args) >= 2 else kwargs.get("message", "")
    assert "[tick_coverage]" in log_payload
    assert "subscribed=5" in log_payload
    assert "fresh=3" in log_payload
    assert "stale=2" in log_payload


# ===========================================================================
# Case B: 구독 5종목 중 0종목 tick → fresh=0, stale=5 (어제 사고 시뮬레이션)
# ===========================================================================
@pytest.mark.asyncio
async def test_report_tick_coverage_all_stale(caplog):
    """모든 종목이 미수신이면 fresh=0, stale=N — 어제(2026-05-11) 운영 사고 패턴."""
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket import kis_ws

    # ticker_last_tick 자체가 비어있는 상태 (구독은 됐으나 tick 무수신)
    assert len(scanner_module.ticker_last_tick) == 0

    with patch.object(kis_ws, "get_subscribed_tickers",
                      return_value={"A1", "A2", "A3", "A4", "A5"}):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()) as mock_write_log:
            caplog.set_level(logging.INFO, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    coverage_msgs = [r for r in caplog.records if "[tick_coverage]" in r.getMessage()]
    assert len(coverage_msgs) == 1
    msg = coverage_msgs[0].getMessage()
    assert "subscribed=5" in msg or "구독=5" in msg
    assert "fresh=0" in msg or "수신=0" in msg
    assert "stale=5" in msg or "미수신=5" in msg

    mock_write_log.assert_called_once()
    log_payload = mock_write_log.call_args.args[1]
    assert "stale=5" in log_payload


# ===========================================================================
# Case C: ticker_last_tick 없는 종목 → stale 카운트
# ===========================================================================
@pytest.mark.asyncio
async def test_report_tick_coverage_missing_keys_count_as_stale(caplog):
    """ticker_last_tick에 키 자체가 없는 종목은 stale로 카운트해야 한다.

    구독 직후 0초 경과 시점에 보고가 발화될 수 있으므로 (구독은 됐으나 첫 tick 전).
    """
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket import kis_ws

    now = datetime.now(KST_TZ)
    # 구독 3종목 중 1종목만 ticker_last_tick에 등록
    scanner_module.ticker_last_tick["B1"] = now - timedelta(seconds=10)
    # B2, B3 는 missing

    with patch.object(kis_ws, "get_subscribed_tickers",
                      return_value={"B1", "B2", "B3"}):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()):
            caplog.set_level(logging.INFO, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    msg = next(r.getMessage() for r in caplog.records if "[tick_coverage]" in r.getMessage())
    assert "fresh=1" in msg or "수신=1" in msg
    assert "stale=2" in msg or "미수신=2" in msg


# ===========================================================================
# Case D: _reset_daily_state() 후 모두 stale (ticker_last_tick.clear)
# ===========================================================================
def test_reset_daily_state_clears_ticker_last_tick():
    """_reset_daily_state는 ticker_last_tick도 다른 scanner dict들과 함께 비워야 한다."""
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler

    now = datetime.now(KST_TZ)
    scanner_module.ticker_last_tick.update({
        "C1": now,
        "C2": now - timedelta(seconds=30),
        "C3": now - timedelta(seconds=300),
    })
    assert len(scanner_module.ticker_last_tick) == 3

    sched = TradingScheduler()
    sched._reset_daily_state()

    assert len(scanner_module.ticker_last_tick) == 0, \
        "_reset_daily_state 후 ticker_last_tick은 비어야 한다"


# ===========================================================================
# Case E: on_tick 호출 → ticker_last_tick 갱신
# ===========================================================================
@pytest.mark.asyncio
async def test_on_tick_updates_ticker_last_tick():
    """RiskManager.on_tick 호출 시 ticker_last_tick[ticker]가 호출 시점(KST)으로 갱신되어야 한다.

    호출 직후와 datetime.now(KST_TZ) 차이가 1초 이내여야 함.
    """
    from src.engine import scanner as scanner_module
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = type("FakeOrderEngine", (), {})()
    rm = RiskManager(registry, order_engine)

    # 전일종가 사전 시드 (prdy_ctrt 계산용)
    scanner_module.ticker_prev_close["D1"] = 1000

    before = datetime.now(KST_TZ)
    await rm.on_tick("D1", current_price=1100, open_price=1050, change_rate=10.0)
    after = datetime.now(KST_TZ)

    assert "D1" in scanner_module.ticker_last_tick, "on_tick 호출 후 ticker_last_tick에 키가 등록되어야 한다"
    last = scanner_module.ticker_last_tick["D1"]

    # tzinfo는 KST 호환 (offset이 +09:00 이거나 명시적 timezone)
    assert last.tzinfo is not None
    assert (last - before).total_seconds() >= -0.01
    assert (after - last).total_seconds() >= -0.01
    # 안전 마진: 호출 직후 1초 이내
    assert (after - before).total_seconds() < 1.0


# ===========================================================================
# Case F: KisWebSocket.get_subscribed_tickers() TICK 구독만 반환
# ===========================================================================
def test_get_subscribed_tickers_filters_tick_only():
    """체결통보(H0STCNI0/H0STCNI9)나 장운영정보(H0UNMKO0)는 제외하고 TICK_TR_ID만 반환."""
    from src.engine.scanner import TICK_TR_ID
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        ("H0STCNI0", "MYHTSID"),     # 체결통보 — 제외
        ("H0UNMKO0", "005930"),       # 장운영정보 — 제외
        (TICK_TR_ID, "035720"),
    }

    result = ws.get_subscribed_tickers()
    assert result == {"005930", "000660", "035720"}, \
        f"TICK_TR_ID 구독만 반환되어야 하지만 실제: {result}"
