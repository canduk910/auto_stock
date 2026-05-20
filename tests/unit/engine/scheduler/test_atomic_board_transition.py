"""사이클 26 — _atomic_board_transition / _board_transition_loop 단위 테스트.

계획서 H 영역: 6 케이스
1. 정상 unsub → ACK 확인 → sub 흐름
2. ACK timeout 시 WARNING 로그 + 다음 단계 강행
3. HIGH 우선 (positions/익일청산) 처리
4. 종목 간 50ms sleep
5. _board_transition_loop 종목 list 순회
6. 20:00 종료 시 subscribe 없음 (unsubscribe only)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.engine.strategy_base import StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


def _make_scheduler():
    """테스트용 TradingScheduler 최소 인스턴스."""
    from src.engine.scheduler import TradingScheduler

    with patch("src.engine.scheduler.token_manager"), \
         patch("src.engine.scheduler.kis_ws"), \
         patch("src.engine.scheduler.kis_ws_pool"):
        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = StrategyRegistry()
        sched._pending_next_day_clear = set()
        sched._running = False
        sched._phase = "idle"
        sched._stale_retry_count = {}
        sched._silent_inactive_first_seen = {}
        sched._silent_inactive_recovery_count = {}
        # 웹소켓 풀 목업
        from unittest.mock import MagicMock
        sched._ws_pool = MagicMock()
        return sched


# ---------------------------------------------------------------------------
# 1. 정상 흐름: unsubscribe → ACK 확인 → subscribe
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atomic_board_transition_normal_flow(monkeypatch):
    """unsubscribe 호출 후 _subscriptions_acked 에서 제거 확인 → subscribe 호출."""
    from src.engine import scheduler as sched_mod
    from src.realtime import websocket_pool as wp_mod

    unsub_calls = []
    sub_calls = []

    # _subscriptions_acked: 처음에 stale (H0NXCNT0, 005930) 등록, unsub 후 제거
    acked: set = {("H0NXCNT0", "005930")}

    async def mock_unsubscribe(tr_id, ticker):
        unsub_calls.append((tr_id, ticker))
        acked.discard((tr_id, ticker))

    async def mock_subscribe(tr_id, ticker, priority=None, bypass_limit=False):
        sub_calls.append((tr_id, ticker, priority))

    mock_pool = MagicMock()
    mock_pool.unsubscribe = mock_unsubscribe
    mock_pool.subscribe = mock_subscribe

    monkeypatch.setattr(wp_mod, "kis_ws_pool", mock_pool)
    monkeypatch.setattr(sched_mod, "kis_ws_pool", mock_pool)

    # _subscriptions_acked 를 모듈 수준 mock
    from src.realtime import websocket_pool
    monkeypatch.setattr(websocket_pool, "kis_ws_pool", mock_pool)

    # _atomic_board_transition 이 scheduler 에 존재하는지 확인
    assert hasattr(sched_mod.TradingScheduler, "_atomic_board_transition"), (
        "_atomic_board_transition 메서드 없음"
    )

    sched = _make_scheduler()
    monkeypatch.setattr(sched_mod, "kis_ws_pool", mock_pool)

    # ACK 확인 polling 을 위한 mock
    sched._acked_set = acked
    await sched._atomic_board_transition(
        "005930", "H0NXCNT0", "H0STCNT0", ack_timeout_secs=0.1
    )

    assert ("H0NXCNT0", "005930") in unsub_calls
    assert any("005930" in str(c) and "H0STCNT0" in str(c) for c in sub_calls)


# ---------------------------------------------------------------------------
# 2. ACK timeout: WARNING 로그 + 다음 단계 강행 (subscribe 호출)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atomic_board_transition_ack_timeout_warns_and_proceeds(monkeypatch, caplog):
    """ACK timeout 시 [atomic_transition_ack_timeout] WARNING 로그 + subscribe 강행."""
    import logging
    from src.engine import scheduler as sched_mod
    from src.realtime import websocket_pool as wp_mod

    sub_calls = []

    # acked 에서 절대 제거하지 않음 (timeout 유도)
    acked: set = {("H0NXCNT0", "005930")}

    async def mock_unsubscribe(tr_id, ticker):
        pass  # ACK 제거 안 함

    async def mock_subscribe(tr_id, ticker, priority=None, bypass_limit=False):
        sub_calls.append((tr_id, ticker))

    # _subscriptions_acked 속성을 acked set 으로 설정 — ACK 제거 안 함 (timeout 유도)
    mock_pool = MagicMock()
    mock_pool.unsubscribe = mock_unsubscribe
    mock_pool.subscribe = mock_subscribe
    mock_pool._subscriptions_acked = acked  # ACK 집합 — 절대 비워지지 않음

    monkeypatch.setattr(sched_mod, "kis_ws_pool", mock_pool)

    sched = _make_scheduler()
    sched._acked_set = acked

    with caplog.at_level(logging.WARNING):
        await sched._atomic_board_transition(
            "005930", "H0NXCNT0", "H0STCNT0", ack_timeout_secs=0.05
        )

    # WARNING 로그 확인
    assert any("atomic_transition_ack_timeout" in r.message for r in caplog.records), (
        "[atomic_transition_ack_timeout] WARNING 로그 누락"
    )
    # subscribe 는 강행됨
    assert any("005930" in str(c) for c in sub_calls), "timeout 후에도 subscribe 강행 필요"


# ---------------------------------------------------------------------------
# 3. _board_transition_loop HIGH 우선 처리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_board_transition_loop_high_first(monkeypatch):
    """HIGH 종목(보유/익일청산)이 LOW 종목(후보)보다 먼저 처리되어야 한다."""
    from src.engine import scheduler as sched_mod

    call_order = []

    async def mock_atomic(ticker, stale, new, ack_timeout_secs=2.0):
        call_order.append(ticker)

    sched = _make_scheduler()
    monkeypatch.setattr(sched, "_atomic_board_transition", mock_atomic)

    high_tickers = ["005930", "000660"]
    low_tickers = ["035720", "051910"]
    tickers = low_tickers + high_tickers  # 섞인 순서

    priority_groups = {
        "positions": high_tickers,
        "next_day_clear": [],
        "swing": [],
        "momentum": [],
        "breakout": low_tickers,
    }

    assert hasattr(sched, "_board_transition_loop"), "_board_transition_loop 없음"

    await sched._board_transition_loop(
        "H0NXCNT0", "H0STCNT0", tickers, priority_groups=priority_groups
    )

    # HIGH 종목이 먼저 처리
    high_indices = [call_order.index(t) for t in high_tickers if t in call_order]
    low_indices = [call_order.index(t) for t in low_tickers if t in call_order]

    if high_indices and low_indices:
        assert max(high_indices) < min(low_indices), (
            f"HIGH 종목 {high_tickers} 가 LOW 종목 {low_tickers} 보다 먼저 처리되어야 한다. "
            f"처리 순서: {call_order}"
        )


# ---------------------------------------------------------------------------
# 4. 종목 간 50ms sleep 확인
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atomic_board_transition_50ms_sleep(monkeypatch):
    """_atomic_board_transition 내 50ms sleep 이 호출되어야 한다."""
    from src.engine import scheduler as sched_mod

    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(secs):
        sleep_calls.append(secs)
        # 실제 sleep 은 매우 짧게
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    acked: set = set()  # 이미 비어 있음 — ACK 즉시 확인

    async def mock_unsubscribe(tr_id, ticker):
        acked.discard((tr_id, ticker))

    async def mock_subscribe(tr_id, ticker, priority=None, bypass_limit=False):
        pass

    mock_pool = MagicMock()
    mock_pool.unsubscribe = mock_unsubscribe
    mock_pool.subscribe = mock_subscribe

    sched = _make_scheduler()
    monkeypatch.setattr(sched_mod, "kis_ws_pool", mock_pool)
    sched._acked_set = acked

    await sched._atomic_board_transition(
        "005930", "H0NXCNT0", "H0STCNT0", ack_timeout_secs=0.1
    )

    # 50ms (0.05초) sleep 호출 확인
    assert any(abs(s - 0.05) < 0.01 for s in sleep_calls), (
        f"50ms (0.05s) sleep 미확인. 실제 sleep 호출: {sleep_calls}"
    )


# ---------------------------------------------------------------------------
# 5. _board_transition_loop 종목 list 순회
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_board_transition_loop_processes_all_tickers(monkeypatch):
    """_board_transition_loop 는 모든 종목에 대해 atomic 전환을 호출해야 한다."""
    from src.engine import scheduler as sched_mod

    processed = []

    async def mock_atomic(ticker, stale, new, ack_timeout_secs=2.0):
        processed.append(ticker)

    sched = _make_scheduler()
    monkeypatch.setattr(sched, "_atomic_board_transition", mock_atomic)

    tickers = ["005930", "000660", "035720", "051910", "005380"]
    await sched._board_transition_loop("H0NXCNT0", "H0STCNT0", tickers)

    assert set(processed) == set(tickers), (
        f"모든 종목이 처리되어야 한다. 처리됨: {processed}, 기대: {tickers}"
    )


# ---------------------------------------------------------------------------
# 6. 20:00 종료 시 subscribe 없음 (unsubscribe only)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_board_transition_loop_no_subscribe_at_close(monkeypatch):
    """20:00 장 종료 전환 시 new_tr_id=None 이면 subscribe 를 호출하지 않아야 한다."""
    from src.engine import scheduler as sched_mod

    sub_calls = []
    unsub_calls = []

    async def mock_unsubscribe(tr_id, ticker):
        unsub_calls.append((tr_id, ticker))

    async def mock_subscribe(tr_id, ticker, priority=None, bypass_limit=False):
        sub_calls.append((tr_id, ticker))

    mock_pool = MagicMock()
    mock_pool.unsubscribe = mock_unsubscribe
    mock_pool.subscribe = mock_subscribe

    sched = _make_scheduler()
    monkeypatch.setattr(sched_mod, "kis_ws_pool", mock_pool)
    sched._acked_set = set()

    tickers = ["005930", "000660"]
    # new_tr_id=None → 장 종료, subscribe 없음
    await sched._board_transition_loop("H0NXCNT0", None, tickers)

    assert len(unsub_calls) > 0, "unsubscribe 는 호출되어야 한다"
    assert len(sub_calls) == 0, (
        f"20:00 종료 시 subscribe 없어야 한다. 실제 sub_calls: {sub_calls}"
    )
