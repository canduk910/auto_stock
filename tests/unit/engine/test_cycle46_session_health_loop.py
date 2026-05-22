"""사이클 46 (2026-05-22) — refactor-review 카드 #6 (MEDIUM) 5분 emit task 통합.

배경:
- 사이클 28 `_report_tick_coverage` (300s) — `_scan_loop` 안에서 호출 (별도 task 아님)
- 사이클 42 `_heartbeat_metrics_loop` (300s) — 각 KisWebSocket 인스턴스가 독립 task 보유
  - 메인 + 보조 N (ISA/sub/gold) = N+1 개 task 분산

본 사이클 (46) 변경 (세션별 task → scheduler 통합 호출):
- `KisWebSocket._heartbeat_metrics_emit_once()` 단발 헬퍼 추출 (사이클 42 loop 의 emit 로직)
- `KisWebSocket._heartbeat_metrics_loop` 루프 제거 (단발 헬퍼 호출만 보존)
- `connect()/disconnect()` 의 task lifecycle 제거 (좀비 task 방지)
- `TradingScheduler._session_health_loop` 신규 — 5분 주기 task (메인 + 보조 일괄)
  - `_emit_heartbeat_metrics_all_sessions` 헬퍼가 모든 세션 단발 호출
- `_report_tick_coverage` 는 `_scan_loop` 안에서 그대로 (중복 발화 차단)

**중요**: `_stale_watcher_loop` (120s) 는 절대 보존 (사이클 24/29-R1/29-R3 안전망).

안전 가드:
- 카운터 reset 동작 보존 (사이클 42 단발 emit 후 reset)
- 메인 + 보조 인스턴스별 독립 카운터 (사이클 43 라벨 통일 보존)
- 한 세션 실패 → 다른 세션 계속 (graceful)
- asyncio.CancelledError graceful (좀비 task 방지)
- `[ws_heartbeat]` 로그 포맷 동일 (사이클 42 호환)

사양 (H-1 ~ H-7):
- H-1: `KisWebSocket._heartbeat_metrics_emit_once` 단발 헬퍼 존재
- H-2: 단발 emit 후 카운터 reset (사이클 42 정책)
- H-3: 사이클 42 `_heartbeat_metrics_loop` 루프 + task 필드 제거
- H-4: `connect()/disconnect()` task lifecycle 제거 (좀비 task 방지)
- H-5: `TradingScheduler._session_health_loop` 5분 주기 task 신규
- H-6: `_emit_heartbeat_metrics_all_sessions` 메인 + 보조 일괄 호출
- H-7: 한 세션 실패 → 다른 세션 계속 (graceful)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


KST = timezone(timedelta(hours=9))


# ===========================================================================
# H-1: _heartbeat_metrics_emit_once 단발 헬퍼 존재
# ===========================================================================
def test_kis_websocket_has_emit_once_helper():
    """`KisWebSocket._heartbeat_metrics_emit_once` 단발 헬퍼."""
    from src.realtime.websocket import KisWebSocket

    assert hasattr(KisWebSocket, "_heartbeat_metrics_emit_once"), (
        "_heartbeat_metrics_emit_once 헬퍼 누락 (사이클 46)"
    )


# ===========================================================================
# H-2: 단발 emit 후 카운터 reset (사이클 42 정책 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_emit_once_resets_counters(monkeypatch, caplog):
    """단발 emit 호출 → [ws_heartbeat] 1행 + 카운터 reset (사이클 42 동작)."""
    import logging
    from src.realtime import websocket as ws_mod
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._label = "main"
    ws._pingpong_recv_count = 10
    ws._pingpong_last_at = datetime.now(KST) - timedelta(seconds=15)
    ws._pingpong_window_start_at = datetime.now(KST) - timedelta(seconds=300)
    ws._heartbeat_timeout_count = 0

    async def _fake_wl(*a, **kw):
        return None
    monkeypatch.setattr(ws_mod, "write_log", _fake_wl, raising=False)

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    await ws._heartbeat_metrics_emit_once()

    # [ws_heartbeat] INFO 1행
    info_msgs = [r.message for r in caplog.records if "[ws_heartbeat]" in r.message]
    assert len(info_msgs) == 1
    assert "label=main" in info_msgs[0]
    assert "pingpong_recv=10" in info_msgs[0]

    # 카운터 + 윈도우 reset (사이클 42 정책)
    assert ws._pingpong_recv_count == 0
    assert ws._heartbeat_timeout_count == 0


# ===========================================================================
# H-3: 사이클 42 _heartbeat_metrics_loop 루프 + task 필드 제거
# ===========================================================================
def test_heartbeat_metrics_loop_removed():
    """사이클 42 `_heartbeat_metrics_loop` 루프 제거 (단발 헬퍼만 보존)."""
    from src.realtime.websocket import KisWebSocket

    # 사이클 46: 루프 폐기, 단발 헬퍼만 유지
    assert not hasattr(KisWebSocket, "_heartbeat_metrics_loop"), (
        "사이클 46 — `_heartbeat_metrics_loop` 루프는 제거되어야 함 "
        "(scheduler `_session_health_loop` 가 단발 호출)"
    )


def test_heartbeat_metrics_task_field_removed():
    """`_heartbeat_metrics_task` 인스턴스 필드 제거 (좀비 task 방지)."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    # 사이클 46: task lifecycle 제거 → 필드 없음
    assert not hasattr(ws, "_heartbeat_metrics_task"), (
        "사이클 46 — `_heartbeat_metrics_task` 필드 제거 필요"
    )


# ===========================================================================
# H-4: connect()/disconnect() task lifecycle 제거
# ===========================================================================
def test_connect_no_longer_creates_metrics_task():
    """`connect()` 가 `_heartbeat_metrics_task` 생성하지 않음 (소스 검증)."""
    import inspect
    from src.realtime.websocket import KisWebSocket

    src = inspect.getsource(KisWebSocket.connect)
    assert "_heartbeat_metrics_task" not in src, (
        "사이클 46 — connect() 에서 metrics task 생성 제거 필요"
    )


def test_disconnect_no_longer_cancels_metrics_task():
    """`disconnect()` 가 `_heartbeat_metrics_task` 참조하지 않음."""
    import inspect
    from src.realtime.websocket import KisWebSocket

    src = inspect.getsource(KisWebSocket.disconnect)
    assert "_heartbeat_metrics_task" not in src, (
        "사이클 46 — disconnect() 에서 metrics task cancel 제거 필요"
    )


# ===========================================================================
# H-5: TradingScheduler._session_health_loop 5분 주기 task
# ===========================================================================
def test_scheduler_has_session_health_loop():
    """`TradingScheduler._session_health_loop` 신규 task 존재."""
    from src.engine.scheduler import TradingScheduler

    assert hasattr(TradingScheduler, "_session_health_loop"), (
        "`_session_health_loop` 신규 task 누락 (사이클 46)"
    )


@pytest.mark.asyncio
async def test_session_health_loop_calls_emit_all_sessions(monkeypatch):
    """`_session_health_loop` 1회 사이클 → emit_all_sessions 호출."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    call_log = []

    async def _fake_emit_all():
        call_log.append("emit_all")

    sched._emit_heartbeat_metrics_all_sessions = _fake_emit_all

    # 1회 사이클 시뮬 — sleep 호출 1번 후 종료
    real_sleep = asyncio.sleep
    call_n = {"n": 0}

    async def _fake_sleep(secs):
        call_n["n"] += 1
        if call_n["n"] >= 2:
            sched._running = False
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    await sched._session_health_loop()

    # 최소 1회 emit_all 호출됨
    assert len(call_log) >= 1


# ===========================================================================
# H-6: _emit_heartbeat_metrics_all_sessions 메인 + 보조 일괄 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_emit_heartbeat_metrics_all_sessions_iterates_main_and_quotes(monkeypatch):
    """메인 (`kis_ws`) + 보조 (`kis_ws_pool._quotes`) 모든 세션 emit_once 호출."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)

    # 메인 + 보조 3개 mock
    main_ws = MagicMock()
    main_ws._label = "main"
    main_ws._heartbeat_metrics_emit_once = AsyncMock()
    quote_isa = MagicMock()
    quote_isa._label = "ISA"
    quote_isa._heartbeat_metrics_emit_once = AsyncMock()
    quote_sub = MagicMock()
    quote_sub._label = "sub"
    quote_sub._heartbeat_metrics_emit_once = AsyncMock()
    quote_gold = MagicMock()
    quote_gold._label = "gold"
    quote_gold._heartbeat_metrics_emit_once = AsyncMock()

    # kis_ws / kis_ws_pool mock
    from src.realtime import websocket as ws_mod
    from src.realtime import websocket_pool as wp_mod
    monkeypatch.setattr(ws_mod, "kis_ws", main_ws, raising=False)
    fake_pool = MagicMock()
    fake_pool._quotes = [quote_isa, quote_sub, quote_gold]
    monkeypatch.setattr(wp_mod, "kis_ws_pool", fake_pool, raising=False)

    await sched._emit_heartbeat_metrics_all_sessions()

    # 4개 세션 모두 emit_once 호출
    main_ws._heartbeat_metrics_emit_once.assert_awaited_once()
    quote_isa._heartbeat_metrics_emit_once.assert_awaited_once()
    quote_sub._heartbeat_metrics_emit_once.assert_awaited_once()
    quote_gold._heartbeat_metrics_emit_once.assert_awaited_once()


# ===========================================================================
# H-7: 한 세션 실패 → 다른 세션 계속 (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_emit_all_sessions_isolates_failure(monkeypatch):
    """한 세션 emit_once 예외 → 다른 세션 정상 진행 (graceful)."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)

    main_ws = MagicMock()
    main_ws._label = "main"
    main_ws._heartbeat_metrics_emit_once = AsyncMock(
        side_effect=RuntimeError("main 실패 시뮬")
    )
    quote_isa = MagicMock()
    quote_isa._label = "ISA"
    quote_isa._heartbeat_metrics_emit_once = AsyncMock()

    from src.realtime import websocket as ws_mod
    from src.realtime import websocket_pool as wp_mod
    monkeypatch.setattr(ws_mod, "kis_ws", main_ws, raising=False)
    fake_pool = MagicMock()
    fake_pool._quotes = [quote_isa]
    monkeypatch.setattr(wp_mod, "kis_ws_pool", fake_pool, raising=False)

    # 예외 전파 없이 완료
    await sched._emit_heartbeat_metrics_all_sessions()

    # main 실패해도 ISA 진행
    quote_isa._heartbeat_metrics_emit_once.assert_awaited_once()


# ===========================================================================
# H-8: _session_health_loop asyncio.CancelledError graceful
# ===========================================================================
@pytest.mark.asyncio
async def test_session_health_loop_cancellable():
    """`_session_health_loop` task cancel 시 graceful 종료."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    async def _fake_emit_all():
        pass

    sched._emit_heartbeat_metrics_all_sessions = _fake_emit_all

    task = asyncio.create_task(sched._session_health_loop())
    # 짧게 대기 후 cancel
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # graceful
