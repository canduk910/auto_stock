"""사이클 42 (2026-05-22) — PINGPONG echo-back 가시성 + 5분 주기 [ws_heartbeat] 통계.

배경:
- ping-pong 메커니즘 자체는 정상 동작 (Layer 1/2/3 검증 완료, 5/22 08:57 Layer 3 발화).
- 다만 송수신 명시 로그 부재 → 운영 실시간 검증 도구 부재.
- Option L1 (DEBUG 추적) + Option L2 (5분 주기 통계 INFO) 통합 추가.

본 사이클 (42) 변경:
- `KisWebSocket.__init__` 에 신규 필드 4개:
  - `self._label: str` (메인 = "main", 보조 = "quote-1"/"quote-2"/... — pool 주입)
  - `self._pingpong_recv_count: int`
  - `self._pingpong_last_at: datetime | None`
  - `self._pingpong_window_start_at: datetime`
  - `self._heartbeat_timeout_count: int`
  - `self._heartbeat_metrics_task: asyncio.Task | None`
- `_handle_raw` PINGPONG 분기에 L1 DEBUG + 카운터/시각 갱신
- `_heartbeat_metrics_loop` 신규 — 5분 주기 [ws_heartbeat] INFO + system_logs + 카운터 reset
- `connect()` 진입 직후 metrics task 생성 / `disconnect()` 에서 cancel

사양 (P-1 ~ P-7):
- P-1: 신규 필드 4개 + label 초기화
- P-2: PINGPONG 수신 시 _pingpong_recv_count += 1 + _pingpong_last_at 갱신
- P-3: PINGPONG echo-back DEBUG 로그 + send 호출
- P-4: heartbeat timeout 발생 시 _heartbeat_timeout_count += 1 카운트
- P-5: _heartbeat_metrics_loop 5분 후 [ws_heartbeat] INFO emit + 카운터 reset
- P-6: 로그 포맷 (label/window/recv/avg/last_age/timeout)
- P-7: disconnect 시 metrics task cancel (좀비 task 방지)
- P-8: 메인 + 보조 세션 인스턴스별 독립 카운터 (label 분리)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ===========================================================================
# P-1: 신규 필드 초기화
# ===========================================================================
def test_kis_websocket_init_has_pingpong_metrics_fields():
    """KisWebSocket.__init__ 가 사이클 42 신규 필드 4개 초기화."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    assert hasattr(ws, "_label"), "_label 필드 누락 (사이클 42)"
    assert hasattr(ws, "_pingpong_recv_count")
    assert hasattr(ws, "_pingpong_last_at")
    assert hasattr(ws, "_pingpong_window_start_at")
    assert hasattr(ws, "_heartbeat_timeout_count")
    # 초기값
    assert ws._pingpong_recv_count == 0
    assert ws._pingpong_last_at is None
    assert ws._heartbeat_timeout_count == 0


def test_kis_websocket_label_default_main():
    """메인 세션 (is_main=True) label 기본값 = 'main'."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    assert ws._label == "main"


def test_kis_websocket_label_for_secondary():
    """보조 세션 (is_main=False) label = 'quote-N' (pool 주입)."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket(is_main=False, label="quote-1")
    assert ws._label == "quote-1"
    assert ws.is_main is False


def test_kis_websocket_label_optional_kwarg():
    """label 미지정 + is_main=False → 기본값 'quote-?' 또는 빈 문자열 (graceful)."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket(is_main=False)
    # is_main=False + label 미지정 → 기본 label 보존 (메인 미지정도 호환)
    assert isinstance(ws._label, str)


# ===========================================================================
# P-2: PINGPONG 수신 카운터 + 시각 갱신
# ===========================================================================
@pytest.mark.asyncio
async def test_pingpong_increments_recv_count(monkeypatch):
    """PINGPONG 메시지 수신 → _pingpong_recv_count += 1 + _pingpong_last_at 갱신."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    pingpong_msg = json.dumps({
        "header": {"tr_id": "PINGPONG", "tr_key": ""},
        "body": {},
    })

    before_recv = ws._pingpong_recv_count
    before_last = ws._pingpong_last_at

    await ws._handle_raw(pingpong_msg)

    assert ws._pingpong_recv_count == before_recv + 1
    assert ws._pingpong_last_at is not None
    if before_last is not None:
        assert ws._pingpong_last_at >= before_last


# ===========================================================================
# P-3: PINGPONG echo-back send + DEBUG 로그
# ===========================================================================
@pytest.mark.asyncio
async def test_pingpong_echo_back_sends_and_logs_debug(monkeypatch, caplog):
    """PINGPONG 수신 → echo-back send + [ws_pingpong_echo] DEBUG 로그."""
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    pingpong_msg = json.dumps({
        "header": {"tr_id": "PINGPONG"},
        "body": {},
    })

    caplog.set_level(logging.DEBUG, logger="src.realtime.websocket")
    await ws._handle_raw(pingpong_msg)

    # echo-back 호출 (원본 raw 메시지 그대로 send)
    ws._ws.send.assert_awaited_once_with(pingpong_msg)
    # DEBUG 로그 (운영 INFO 미노출, 폭주 방지)
    debug_msgs = [
        r.message for r in caplog.records
        if "[ws_pingpong_echo]" in r.message
    ]
    assert len(debug_msgs) >= 1
    assert "main" in debug_msgs[0]  # 메인 세션 label


# ===========================================================================
# P-4: heartbeat timeout 카운터
# ===========================================================================
def test_heartbeat_timeout_count_field_initialized():
    """_heartbeat_timeout_count 필드 초기화 + Green 후 receive_loop 에서 증가."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    assert ws._heartbeat_timeout_count == 0


# ===========================================================================
# P-5: _heartbeat_metrics_loop 5분 주기 emit + 카운터 reset
# ===========================================================================
@pytest.mark.asyncio
async def test_heartbeat_metrics_loop_emits_and_resets(monkeypatch, caplog):
    """_heartbeat_metrics_loop 1회 사이클 → [ws_heartbeat] INFO emit + 카운터 reset."""
    import logging
    from src.realtime import websocket as ws_mod
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._running = True
    ws._label = "main"
    ws._pingpong_recv_count = 10
    ws._pingpong_last_at = datetime.now(KST) - timedelta(seconds=15)
    ws._pingpong_window_start_at = datetime.now(KST) - timedelta(seconds=300)
    ws._heartbeat_timeout_count = 0

    # write_log mock
    async def _fake_wl(level, msg, *a, **kw):
        return None
    monkeypatch.setattr(ws_mod, "write_log", _fake_wl, raising=False)

    # 5분 sleep 우회 — 첫 sleep 직후 _running=False 로 강제 종료 (1회 emit 확인)
    sleep_calls = {"n": 0}
    real_sleep = asyncio.sleep

    async def _fake_sleep(secs):
        sleep_calls["n"] += 1
        if sleep_calls["n"] == 1:
            return
        # 2번째 sleep 진입 — emit 후 다음 사이클 진입 직전
        ws._running = False
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    await ws._heartbeat_metrics_loop()

    # [ws_heartbeat] INFO 로그
    info_msgs = [r.message for r in caplog.records if "[ws_heartbeat]" in r.message]
    assert len(info_msgs) >= 1, f"INFO emit 누락 — records={[r.message for r in caplog.records]}"
    msg = info_msgs[0]
    assert "label=main" in msg
    assert "pingpong_recv=10" in msg
    assert "heartbeat_timeout=0" in msg

    # 카운터 reset
    assert ws._pingpong_recv_count == 0, "emit 후 카운터 reset 안 됨"
    assert ws._heartbeat_timeout_count == 0


# ===========================================================================
# P-6: 로그 포맷 검증 (label/window/recv/avg/last_age/timeout)
# ===========================================================================
@pytest.mark.asyncio
async def test_heartbeat_metrics_log_format(monkeypatch, caplog):
    """[ws_heartbeat] 로그 포맷: label/window/pingpong_recv/avg_interval/last_age/heartbeat_timeout 모두 포함."""
    import logging
    from src.realtime import websocket as ws_mod
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._running = True
    ws._label = "quote-1"
    ws._pingpong_recv_count = 5
    ws._pingpong_last_at = datetime.now(KST) - timedelta(seconds=20)
    ws._pingpong_window_start_at = datetime.now(KST) - timedelta(seconds=150)
    ws._heartbeat_timeout_count = 2

    async def _fake_wl(level, msg, *a, **kw):
        return None
    monkeypatch.setattr(ws_mod, "write_log", _fake_wl, raising=False)

    real_sleep = asyncio.sleep
    call_n = {"n": 0}

    async def _fake_sleep(secs):
        call_n["n"] += 1
        # 첫 sleep 후 정상 emit 진입 (running=True 유지) → 두번째 sleep 직전 종료
        if call_n["n"] >= 2:
            ws._running = False
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    await ws._heartbeat_metrics_loop()

    info_msgs = [r.message for r in caplog.records if "[ws_heartbeat]" in r.message]
    assert len(info_msgs) >= 1
    msg = info_msgs[0]
    # 필수 필드
    for keyword in ("label=", "window=", "pingpong_recv=", "avg_interval=",
                    "last_age=", "heartbeat_timeout="):
        assert keyword in msg, f"필수 필드 누락: {keyword}\nactual: {msg}"


# ===========================================================================
# P-7: disconnect 시 metrics task cancel
# ===========================================================================
@pytest.mark.asyncio
async def test_disconnect_cancels_metrics_task():
    """disconnect() 호출 시 _heartbeat_metrics_task cancel — 좀비 task 방지."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._running = True

    # 영원히 sleep 하는 fake task
    async def _idle():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise

    ws._heartbeat_metrics_task = asyncio.create_task(_idle())

    # disconnect 호출 후 task cancel 확인
    await ws.disconnect()

    # task 가 cancel 됨
    assert ws._heartbeat_metrics_task is None or ws._heartbeat_metrics_task.cancelled() or ws._heartbeat_metrics_task.done()


# ===========================================================================
# P-8: 메인 + 보조 세션 인스턴스별 독립 카운터
# ===========================================================================
@pytest.mark.asyncio
async def test_main_and_secondary_have_independent_counters():
    """메인 + 보조 세션은 인스턴스별 독립 카운터 (label 분리)."""
    from src.realtime.websocket import KisWebSocket

    main = KisWebSocket()
    quote1 = KisWebSocket(is_main=False, label="quote-1")
    quote2 = KisWebSocket(is_main=False, label="quote-2")

    # 메인에 ping 5회, quote-1 에 3회, quote-2 에 7회 시뮬레이션
    for ws_inst, n in [(main, 5), (quote1, 3), (quote2, 7)]:
        ws_inst._ws = MagicMock()
        ws_inst._ws.send = AsyncMock()
        ws_inst._running = True
        for _ in range(n):
            await ws_inst._handle_raw(json.dumps({
                "header": {"tr_id": "PINGPONG"},
                "body": {},
            }))

    assert main._pingpong_recv_count == 5
    assert quote1._pingpong_recv_count == 3
    assert quote2._pingpong_recv_count == 7
    # label 분리
    assert main._label == "main"
    assert quote1._label == "quote-1"
    assert quote2._label == "quote-2"
