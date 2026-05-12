"""WebSocket 재연결 후 자동 시세 검증 (F1, 2026-05-12).

결함 배경: 오늘(2026-05-12) 운영 로그상 WebSocket 재연결이 하루 3~4회 발생.
재연결 후 `connect()` 가 `_subscriptions` 를 순회해 `_send_subscribe` 만 호출하고
KIS 응답을 검증하지 않음. KIS 가 SUBSCRIBE 응답도 안 주고 시세도 안 보내는
**silent inactive** 케이스에서 E2 의 거절 감지가 무력화되어 다음 5분 `_scan_loop`
까지 시세 결손이 누적된다.

본 테스트는 다음 사양을 검증한다 (F1 범위만):

1. 재연결 성공 직후 `_verify_subscriptions_after_reconnect()` task 1회 발화
   - **`_reconnect_count > 0`** 인 경우만 (첫 연결은 발화 안 함)
   - `VERIFY_AFTER_SECS=60` 대기 후 검증

2. 검증 동작
   - `scanner.ticker_last_tick` 와 비교하여 `VERIFY_FRESHNESS_SECS=60` 내 tick 없는
     TICK 구독만 stale 분류
   - stale 종목에 대해 `_send_subscribe(TICK_TR_ID, ticker, subscribe=True)` 1회 재전송
   - INFO 또는 WARNING 로그 1행 노출 (stale 유무에 따라)
   - WARNING 케이스는 `write_log("WARNING", "[ws_reverify] ...")` fire-and-forget

3. 안전 가드
   - `self._reverify_in_progress` 플래그로 동시 task 중첩 방지
   - 검증 도중 `self._ws is None` / `self._running is False` 면 조용히 종료
   - 검증 중 예외 발생 → ERROR 로그 + 플래그 해제 (다음 재연결 정상 발화)
   - stale 종목 10개 초과 시 로그에 처음 10개만 표시 + 전체 카운트 명시
   - `_subscriptions` set 직접 수정 금지 — `_send_subscribe` 만 호출
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.realtime import websocket as websocket_module
from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 사양 1: 상수 정의
# ---------------------------------------------------------------------------
def test_verify_after_secs_constant_is_60():
    """재연결 후 검증까지 대기 — 60초."""
    assert websocket_module.VERIFY_AFTER_SECS == 60


def test_verify_freshness_secs_constant_is_60():
    """검증 기준 — 60초 내 tick 없으면 stale."""
    assert websocket_module.VERIFY_FRESHNESS_SECS == 60


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def patched_write_log(monkeypatch):
    """websocket 모듈 write_log 를 AsyncMock 으로 대체."""
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(websocket_module, "write_log", mock, raising=False)
    return mock


@pytest.fixture
def patched_sleep(monkeypatch):
    """asyncio.sleep 을 즉시 반환하는 AsyncMock 으로 대체 — 60s 대기 단축."""
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(websocket_module.asyncio, "sleep", mock)
    return mock


@pytest.fixture
def patched_ticker_last_tick(monkeypatch):
    """scanner.ticker_last_tick 를 테스트 격리된 dict 로 대체."""
    from src.engine import scanner as scanner_module
    fresh: dict[str, datetime] = {}
    monkeypatch.setattr(scanner_module, "ticker_last_tick", fresh)
    return fresh


def _make_ws_after_reconnect() -> KisWebSocket:
    """재연결이 1회 발생한 상태의 KisWebSocket 인스턴스."""
    ws = KisWebSocket()
    ws._reconnect_count = 1
    ws._running = True
    ws._ws = AsyncMock()  # _send_subscribe 의 self._ws 가드 통과
    return ws


# ---------------------------------------------------------------------------
# Case A: 모든 종목 fresh — 재구독 0회, INFO 로그 1행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_a_all_fresh_no_resubscribe(
    patched_write_log, patched_sleep, patched_ticker_last_tick, caplog
):
    ws = _make_ws_after_reconnect()
    # TICK 구독 3종목 등록 — _send_subscribe 만 spy
    ws._subscriptions = {
        ("H0UNCNT0", "005930"),
        ("H0UNCNT0", "000660"),
        ("H0UNCNT0", "035420"),
    }
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    # 모두 fresh — 5초 전 tick
    now = datetime.now(KST_TZ)
    for t in ["005930", "000660", "035420"]:
        patched_ticker_last_tick[t] = now - timedelta(seconds=5)

    with caplog.at_level(logging.INFO, logger="src.realtime.websocket"):
        await ws._verify_subscriptions_after_reconnect()

    # _send_subscribe 호출 없음
    assert send_spy.await_count == 0, "fresh 종목만 있으면 재구독 0회"
    # write_log 호출 없음 (WARNING 미발생)
    assert patched_write_log.await_count == 0
    # INFO 로그 1행
    info_logs = [r for r in caplog.records if r.levelno == logging.INFO and "ws_reverify" in r.getMessage()]
    assert info_logs, "fresh 종목만이면 INFO 로그 1행 노출 (미수신 없음)"
    # 플래그 해제
    assert ws._reverify_in_progress is False


# ---------------------------------------------------------------------------
# Case B: 3종목 stale + 5종목 fresh → stale 3종목만 재구독, WARNING 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_b_partial_stale_resubscribes_only_stale(
    patched_write_log, patched_sleep, patched_ticker_last_tick, caplog
):
    ws = _make_ws_after_reconnect()
    stale_tickers = ["111111", "222222", "333333"]
    fresh_tickers = ["005930", "000660", "035420", "035720", "012330"]
    ws._subscriptions = {("H0UNCNT0", t) for t in stale_tickers + fresh_tickers}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    now = datetime.now(KST_TZ)
    # fresh: 5초 전
    for t in fresh_tickers:
        patched_ticker_last_tick[t] = now - timedelta(seconds=5)
    # stale: 90초 전 (60초 임계 초과)
    for t in stale_tickers:
        patched_ticker_last_tick[t] = now - timedelta(seconds=90)

    with caplog.at_level(logging.WARNING, logger="src.realtime.websocket"):
        await ws._verify_subscriptions_after_reconnect()

    # _send_subscribe — stale 3개만 호출 (subscribe=True)
    assert send_spy.await_count == 3
    called_keys = {call.args[1] for call in send_spy.await_args_list}
    assert called_keys == set(stale_tickers)
    for call in send_spy.await_args_list:
        assert call.args[0] == "H0UNCNT0"  # TICK_TR_ID
        assert call.kwargs.get("subscribe") is True

    # WARNING 로그
    warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING and "ws_reverify" in r.getMessage()]
    assert warning_logs, "stale 발생 시 WARNING 로그 1행 필수"

    # write_log fire-and-forget
    assert patched_write_log.await_count == 1
    args, _ = patched_write_log.await_args
    assert args[0] == "WARNING"
    assert "[ws_reverify]" in args[1]
    assert "reconnect_count=1" in args[1]
    assert "stale=3" in args[1]

    # _subscriptions set 직접 수정 금지 — 그대로 유지
    assert ws._subscriptions == {("H0UNCNT0", t) for t in stale_tickers + fresh_tickers}


# ---------------------------------------------------------------------------
# Case C: ticker_last_tick 에 키 없는 종목 (구독 후 tick 한 번도 안 옴) → stale
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_c_missing_key_treated_as_stale(
    patched_write_log, patched_sleep, patched_ticker_last_tick
):
    ws = _make_ws_after_reconnect()
    ws._subscriptions = {("H0UNCNT0", "999999")}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    # ticker_last_tick 에 999999 키 없음

    await ws._verify_subscriptions_after_reconnect()

    # 누락 키도 stale 로 분류 → 재구독
    assert send_spy.await_count == 1
    assert send_spy.await_args.args == ("H0UNCNT0", "999999")
    assert send_spy.await_args.kwargs.get("subscribe") is True


# ---------------------------------------------------------------------------
# Case D: 첫 연결(_reconnect_count == 0) → verify 발화 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_d_first_connect_does_not_verify(
    patched_write_log, patched_sleep, patched_ticker_last_tick
):
    ws = KisWebSocket()
    ws._reconnect_count = 0
    ws._running = True
    ws._ws = AsyncMock()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    # 호출하더라도 reconnect_count==0 가드로 즉시 종료되어야 함
    await ws._verify_subscriptions_after_reconnect()

    assert send_spy.await_count == 0, "_reconnect_count==0 이면 검증 발화 안 함"
    # asyncio.sleep 도 호출 안 됨 (가드가 sleep 이전에 동작)
    assert patched_sleep.await_count == 0
    # 플래그도 set 되지 않음
    assert ws._reverify_in_progress is False


# ---------------------------------------------------------------------------
# Case E: 동시 task 중첩 — 두 번째 호출은 즉시 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_e_concurrent_verify_is_blocked(
    patched_write_log, patched_sleep, patched_ticker_last_tick
):
    ws = _make_ws_after_reconnect()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    # 첫 번째 task 가 진행 중인 상태 시뮬레이션
    ws._reverify_in_progress = True

    await ws._verify_subscriptions_after_reconnect()

    # 새 task 는 즉시 종료 — sleep / send 호출 없음
    assert patched_sleep.await_count == 0
    assert send_spy.await_count == 0
    # 플래그는 여전히 True (다른 task 가 들고 있음)
    assert ws._reverify_in_progress is True


# ---------------------------------------------------------------------------
# Case F: 검증 도중 WebSocket 연결 닫힘 (_ws is None) → 재구독 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_f_ws_closed_during_verify_skips_resubscribe(
    patched_write_log, patched_sleep, patched_ticker_last_tick
):
    ws = _make_ws_after_reconnect()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    # sleep 콜백 — 60s 대기 끝나는 시점에 _ws=None 으로 시뮬
    async def _close_ws_after_sleep(*args, **kwargs):
        ws._ws = None
        return None

    patched_sleep.side_effect = _close_ws_after_sleep

    await ws._verify_subscriptions_after_reconnect()

    assert send_spy.await_count == 0, "_ws is None 이면 재구독 스킵"
    # 플래그 해제 — finally 가드
    assert ws._reverify_in_progress is False


@pytest.mark.asyncio
async def test_case_f2_running_false_during_verify_skips_resubscribe(
    patched_write_log, patched_sleep, patched_ticker_last_tick
):
    """_running=False 분기도 동일하게 skip."""
    ws = _make_ws_after_reconnect()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    async def _stop_after_sleep(*args, **kwargs):
        ws._running = False
        return None

    patched_sleep.side_effect = _stop_after_sleep

    await ws._verify_subscriptions_after_reconnect()

    assert send_spy.await_count == 0
    assert ws._reverify_in_progress is False


# ---------------------------------------------------------------------------
# Case G: stale 종목 10개 초과 → 로그에 처음 10개만 표시 + 전체 카운트 명시
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_g_log_truncates_to_first_ten(
    patched_write_log, patched_sleep, patched_ticker_last_tick, caplog
):
    ws = _make_ws_after_reconnect()
    # 15종목 모두 stale (ticker_last_tick 키 없음)
    tickers = [f"{i:06d}" for i in range(100000, 100015)]
    ws._subscriptions = {("H0UNCNT0", t) for t in tickers}
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    with caplog.at_level(logging.WARNING, logger="src.realtime.websocket"):
        await ws._verify_subscriptions_after_reconnect()

    # 모든 15개 재구독 호출
    assert send_spy.await_count == 15

    # WARNING 로그에 전체 카운트(15) 포함, 처음 10개만 표시
    warning_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "ws_reverify" in r.getMessage()
    ]
    assert warning_msgs
    msg = warning_msgs[0]
    # 전체 카운트 15 노출
    assert "15" in msg, "전체 stale 카운트 노출 필수"
    # 11번째 이후 종목은 메시지에 없어야 함 (처음 10개만 표시)
    # 마지막 ticker 100014 가 메시지에 없음으로 truncate 검증
    # (slice 가 처음 10개만 가져오므로 100010 ~ 100014 는 없어야 함)
    assert "100014" not in msg, "10개 초과분은 로그에서 truncate"


# ---------------------------------------------------------------------------
# Case H: 검증 중 예외 발생 → ERROR 로그 + 플래그 해제
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_h_exception_logs_error_and_clears_flag(
    patched_write_log, patched_sleep, patched_ticker_last_tick, caplog
):
    ws = _make_ws_after_reconnect()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    # _send_subscribe 가 예외를 던짐
    ws._send_subscribe = AsyncMock(side_effect=RuntimeError("send failed"))

    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws._verify_subscriptions_after_reconnect()

    # 예외 흡수 — 호출자에게 전파 안 됨 (여기까지 도달했다는 것 자체로 확인)
    # ERROR 로그 발생
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_logs, "검증 중 예외 시 ERROR 로그 발생 필수"
    # 플래그 해제 — 다음 재연결 정상 발화 가능
    assert ws._reverify_in_progress is False, (
        "예외 후에도 _reverify_in_progress 플래그가 해제되어야 다음 재연결 가능"
    )


# ---------------------------------------------------------------------------
# Case I: TICK 외 구독(체결통보 등)은 검증 대상에서 제외
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_i_non_tick_subscriptions_excluded(
    patched_write_log, patched_sleep, patched_ticker_last_tick
):
    ws = _make_ws_after_reconnect()
    # TICK 1종목 + 체결통보 + 장운영정보
    ws._subscriptions = {
        ("H0UNCNT0", "005930"),    # TICK — 검증 대상
        ("H0STCNI0", "HTSID01"),   # 체결통보 — 검증 대상 아님
        ("H0UNMKO0", "005930"),    # 장운영정보 — 검증 대상 아님
    }
    send_spy = AsyncMock(return_value=None)
    ws._send_subscribe = send_spy

    # 005930 stale (키 없음)
    await ws._verify_subscriptions_after_reconnect()

    # TICK 1종목만 재구독 호출
    assert send_spy.await_count == 1
    assert send_spy.await_args.args[0] == "H0UNCNT0"
    assert send_spy.await_args.args[1] == "005930"
