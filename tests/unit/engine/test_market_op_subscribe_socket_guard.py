"""market_op 재구독 훅 — 닫힌 소켓 send 레이스 가드 회귀 가드 (2026-08-07).

## 라이브 실증 (2026-08-07 11:24:57)

    11:24:49 WS 연결 닫힘 → 재연결 성공
    11:24:57 WS 연결 닫힘        ← 재연결 직후 다시 끊김
    11:24:57 HIGH 7종목 전부 [market_op_subscribe] HIGH 구독 실패
             ConnectionClosedError: no close frame received or sent

`_subscribe_market_operation_tickers` 진입 가드(`not getattr(kis_ws, "_ws", None)`)
는 `_ws` 가 **None 인지만** 검사한다. 재연결 레이스로 `_ws` 가 "존재하지만
닫힌"(state != OPEN) 상태이면 가드를 통과해 `self._ws.send()` 에서
`ConnectionClosedError` 가 터진다 — HIGH 종목마다 ERROR + traceback 폭주.

## 성격

H0UNMKO0(장운영정보)는 VI·거래정지 이벤트 채널 — 시세(TICK)·손절 평가와 무관.
일회성(재연결 튐 순간)이고 다음 5분 사이클에 자동 복구된다. 손실 0, 순수 로그
노이즈 + 몇 분 VI 감지 공백. 근본(realtime `_send_subscribe` 가드)은 시세·
체결통보 구독까지 공유하는 8영역 hot path라 이 심각도로 건드리지 않는다.

## 시정 (사용자 결정: 재구독 훅에 소켓 상태 가드)

- 진입 가드 강화 — `_ws` 존재 + **open 상태**(`state == State.OPEN`)까지 확인.
  닫혀 있으면 이번 사이클 전체 skip(return 0) + INFO 1행(다음 사이클 자동 복구).
- 루프 중 `ConnectionClosedError` — 그 순간 소켓이 닫힌 것이므로 남은 종목도
  전부 실패한다. 즉시 break + **WARNING 1행**(종목별 ERROR 폭주 대신, 재연결
  중 예상 상태이므로 ERROR 아님).
- realtime 미접촉 — scheduler 이 duck-typing 으로 `_ws.state` 만 읽는다.

## cycle221 (2026-08-20) 픽스처 적응 — 계약은 그대로

VI(H0UNMKO0) 라우팅이 "메인 직접(bypass) + 풀 LOW" 2루프 → **보조 세션 직접 배치 1루프**
로 바뀌었다(08-19 OPSP0008 시세 7건 = 보유 종목 tick blind 시정). 정정(F2)으로 대상은
**보유 + 익일청산(HIGH) 뿐** — 후보 VI 는 `_ticker_to_session` 단일키 중복 분기 때문에
실질 noop 이었으므로 되살리지 않는다. 이 파일이 지키는
**소켓 OPEN 진입 가드 / ConnectionClosedError break+WARNING 1행 / ERROR 0 / 기타 예외
종목별 graceful** 계약은 **동일**하고, 단언 대상만 메인 세션 → 보조 세션으로 이동한다.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.protocol import State

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


def _make_scheduler(*, positions: set[str], pending: set[str] = frozenset()):
    sched = TradingScheduler.__new__(TradingScheduler)
    strat = SimpleNamespace(
        state=SimpleNamespace(positions={t: object() for t in positions})
    )
    registry = MagicMock()
    registry.all.return_value = [strat]
    sched.registry = registry
    sched._pending_next_day_clear = {(t, "s") for t in pending}
    # cycle221 — `__init__` 이 선언하는 VI 구독 추적 맵 (델타 해제 + 중복 SEND 억제)
    sched._market_op_subs = {}
    return sched


class _FakeSocket:
    """`ClientConnection` 상태만 흉내낸다 (`.state`)."""

    def __init__(self, state: State):
        self.state = state


def _make_quote_session(label: str):
    """cycle221 — VI 가 실제로 붙는 보조 세션 mock."""
    ws = MagicMock()
    ws._label = label
    ws._subscriptions = set()

    async def _sub(tr_id, tr_key, *, bypass_limit=False):
        ws._subscriptions.add((tr_id, tr_key))

    async def _unsub(tr_id, tr_key):
        ws._subscriptions.discard((tr_id, tr_key))

    ws.subscribe = AsyncMock(side_effect=_sub)
    ws.unsubscribe = AsyncMock(side_effect=_unsub)
    return ws


def _patch_ws(monkeypatch, *, main_socket, pool_ok: bool = True, quotes=None):
    """kis_ws._ws 를 임의 소켓 상태로, 보조 세션(_quotes) 을 배치 대상으로."""
    fake_ws = MagicMock()
    fake_ws._ws = main_socket
    fake_ws.subscribe = AsyncMock(return_value=None)
    fake_ws._subscriptions = set()
    fake_ws.get_subscribed_tickers = MagicMock(return_value=set())

    fake_pool = MagicMock()
    fake_pool.subscribe = AsyncMock(return_value="quote-1" if pool_ok else None)
    fake_pool.unsubscribe = AsyncMock(return_value=None)
    fake_pool._quotes = (
        list(quotes) if quotes is not None else [_make_quote_session("quote-1")]
    )

    monkeypatch.setattr("src.realtime.websocket.kis_ws", fake_ws, raising=False)
    monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool", fake_pool, raising=False
    )
    return fake_ws, fake_pool


# ---------------------------------------------------------------------------
# G-1 — 닫힌 소켓: 진입 가드가 전체 사이클을 skip (send 시도 0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state", [State.CLOSING, State.CLOSED, State.CONNECTING],
    ids=["closing", "closed", "connecting"],
)
@pytest.mark.asyncio
async def test_non_open_socket_skips_without_sending(state, monkeypatch, caplog):
    import logging

    fake_ws, fake_pool = _patch_ws(monkeypatch, main_socket=_FakeSocket(state))
    sched = _make_scheduler(positions={"051905", "073240"})

    with caplog.at_level(logging.INFO):
        n = await sched._subscribe_market_operation_tickers({"111111"})

    assert n == 0, "닫힌/전이 소켓에서는 구독 시도 자체를 하지 않는다"
    fake_ws.subscribe.assert_not_awaited()
    fake_pool.subscribe.assert_not_awaited()
    for q in fake_pool._quotes:
        q.subscribe.assert_not_awaited()
    # ERROR/traceback 폭주가 아니라 관측 로그 (skip 사유)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_none_socket_still_skips():
    """기존 `_ws is None` 가드 회귀 보존."""
    sched = _make_scheduler(positions={"005930"})
    # kis_ws 자체가 없으면(_ws None) 0 반환 — 기존 계약
    import src.realtime.websocket as ws_mod

    orig = getattr(ws_mod, "kis_ws", None)
    try:
        ws_mod.kis_ws = MagicMock()
        ws_mod.kis_ws._ws = None
        n = await sched._subscribe_market_operation_tickers({"111111"})
        assert n == 0
    finally:
        ws_mod.kis_ws = orig


# ---------------------------------------------------------------------------
# G-2 — 열린 소켓: 기존 정상 경로 그대로 (회귀 보존)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_socket_subscribes_normally(monkeypatch):
    """[cycle221 의미 전환] 열린 소켓 정상 경로 — 배치처가 메인 → 보조 세션.

    원래: `fake_ws.subscribe.await_count == 2` + `bypass_limit is True` (HIGH 메인 직접).
    전환: 메인 SEND **0건**, `bypass_limit=True` **부재**, 전량 보조 세션 직접 배치.
    (08-19 OPSP0008 — VI 가 메인 41 슬롯을 tick 과 경쟁해 보유 종목 시세가 밀렸다.)

    cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2).
    따라서 정상 경로 SEND 는 HIGH 2건(보유+익일청산)뿐이고 후보 111111 은 0건이다.
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch, main_socket=_FakeSocket(State.OPEN))
    sched = _make_scheduler(positions={"005930"}, pending={"000660"})

    n = await sched._subscribe_market_operation_tickers({"111111"})

    assert fake_ws.subscribe.await_count == 0, "VI 메인 직접 구독 금지"
    assert fake_pool.subscribe.await_count == 0, "풀 API 경유 금지 (라우팅 맵 오염)"

    calls = [c for q in fake_pool._quotes for c in q.subscribe.await_args_list]
    assert sorted(c.args[1] for c in calls) == ["000660", "005930"], (
        "HIGH 2(보유+익일청산)만 배치 — 후보는 SEND 0건"
    )
    assert n == 2
    for call in calls:
        assert call.kwargs.get("bypass_limit", False) is False, (
            "bypass_limit=True 는 로컬 가드만 우회 — 서버 한도 41 초과 시 OPSP0008"
        )


# ---------------------------------------------------------------------------
# G-3 — 루프 중 ConnectionClosedError: break + WARNING (ERROR 폭주 금지)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mid_loop_connection_closed_breaks_with_warning(monkeypatch, caplog):
    """[cycle221 픽스처 적응] 루프 구조 2루프 → 1루프. **계약(1행 WARNING·ERROR 0) 동일.**"""
    import logging

    q1 = _make_quote_session("quote-1")
    calls = {"n": 0}

    async def _sub(tr_id, ticker, *, bypass_limit=False):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise ConnectionClosedError(None, None)

    q1.subscribe = AsyncMock(side_effect=_sub)
    fake_ws, fake_pool = _patch_ws(
        monkeypatch, main_socket=_FakeSocket(State.OPEN), quotes=[q1]
    )
    sched = _make_scheduler(positions={"051905", "073240", "079160", "103140"})

    with caplog.at_level(logging.INFO):
        await sched._subscribe_market_operation_tickers(set())

    # 닫힘 감지 후 남은 종목은 시도하지 않는다 (4종목 ERROR 폭주 → break)
    assert calls["n"] == 2, "ConnectionClosedError 후 즉시 break"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    warns = [r for r in caplog.records
             if r.levelno == logging.WARNING and "market_op" in r.getMessage()]
    assert not errors, "재연결 중 예상 상태 — ERROR/traceback 금지"
    assert len(warns) == 1, "1행 WARNING 으로 집약"


@pytest.mark.asyncio
async def test_other_exception_still_graceful_per_ticker(monkeypatch, caplog):
    """[cycle221 픽스처 적응] ConnectionClosedError 외 예외는 종목별 격리 + 계속 진행."""
    import logging

    q1 = _make_quote_session("quote-1")

    async def _sub(tr_id, ticker, *, bypass_limit=False):
        if ticker == "073240":
            raise RuntimeError("일시 오류")

    q1.subscribe = AsyncMock(side_effect=_sub)
    fake_ws, fake_pool = _patch_ws(
        monkeypatch, main_socket=_FakeSocket(State.OPEN), quotes=[q1]
    )
    sched = _make_scheduler(positions={"051905", "073240", "079160"})

    with caplog.at_level(logging.INFO):
        n = await sched._subscribe_market_operation_tickers(set())

    # 073240 만 실패, 나머지 2종목 정상 (break 아님 — ConnectionClosed 아니므로)
    assert n == 2


# ---------------------------------------------------------------------------
# G-4 — realtime 미접촉 (사용자 결정: scheduler 만 수정)
# ---------------------------------------------------------------------------

def test_realtime_send_subscribe_unchanged():
    """근본 수정(`_send_subscribe` 가드 강화)은 이번 범위 밖 — realtime 미접촉."""
    from src.realtime import websocket as ws_mod

    src = inspect.getsource(ws_mod.KisWebSocket._send_subscribe)
    # 소켓 state 판정을 _send_subscribe 에 넣지 않았다 (scheduler 훅에서만 가드)
    assert "State.OPEN" not in src


def test_guard_reads_socket_state_in_scheduler():
    """가드가 scheduler 훅에 있다 — 소켓 open 상태를 읽는다."""
    src = inspect.getsource(
        TradingScheduler._subscribe_market_operation_tickers
    )
    assert "State" in src or "state" in src
