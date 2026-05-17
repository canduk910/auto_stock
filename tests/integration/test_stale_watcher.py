"""K — WebSocket 시세 silent inactive 자동 복구 (stale_watcher).

KIS WebSocket 구독은 됐으나 시세가 silent 하게 안 들어오는 종목을
30s 주기로 감시한다. 60s 미수신이면 `_send_subscribe` 재발송,
3회 연속 stale이면 unsubscribe + subscribe 강제 재등록.
6회 누적 stale이면 skip (다음 `_scan_loop` 사이클에 위임).

F1(재연결 1회) + `_scan_loop`(5분) + K(30s) 3중 안전망.

2026-05-12 결함 증거 (운영 로그):
- 11:48 [tick_coverage] subscribed=27 fresh=1 stale=26 (96% silent inactive)
- KIS 한도(41) 미만 → 한도 초과 아님. F1 1회 + _scan_loop 5분으로는 미회복
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.integration


_KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼 — stale_watcher 검증용 kis_ws 더블 (subscribe/unsubscribe/_send_subscribe 호출 추적)
# ---------------------------------------------------------------------------
def _make_kis_ws_double(subscribed: set[str]):
    """conftest 의 scheduler_env 가 kis_ws 를 통째로 SimpleNamespace 로 대체하므로
    추가 메서드(unsubscribe/_send_subscribe/get_subscribed_tickers) 를 보강한다."""

    calls = SimpleNamespace(
        subscribe=[],          # (tr_id, tr_key, bypass_limit)
        unsubscribe=[],        # (tr_id, tr_key)
        send_subscribe=[],     # (tr_id, tr_key, subscribe)
    )

    async def fake_subscribe(tr_id, tr_key, *, bypass_limit: bool = False):
        calls.subscribe.append((tr_id, tr_key, bypass_limit))
        subscribed.add(tr_key)

    async def fake_unsubscribe(tr_id, tr_key):
        calls.unsubscribe.append((tr_id, tr_key))
        subscribed.discard(tr_key)

    async def fake_send_subscribe(tr_id, tr_key, *, subscribe: bool = True):
        calls.send_subscribe.append((tr_id, tr_key, subscribe))

    def fake_get_subscribed_tickers() -> set[str]:
        return set(subscribed)

    return SimpleNamespace(
        subscribe=fake_subscribe,
        unsubscribe=fake_unsubscribe,
        _send_subscribe=fake_send_subscribe,
        get_subscribed_tickers=fake_get_subscribed_tickers,
    ), calls


def _patch_kis_ws(scheduler_env, subscribed: set[str]):
    """사이클 7-C — stale watcher 가 풀(`kis_ws_pool`) 헬퍼를 사용하므로 풀도 패치.

    풀의 `resend_subscribe_for_ticker` / `unsubscribe_in_pool` / `subscribe` 가
    fake double 의 `_send_subscribe` / `unsubscribe` / `subscribe` 호출을 그대로 기록하도록
    위임한다.
    """
    double, calls = _make_kis_ws_double(subscribed)
    scheduler_env.monkeypatch.setattr("src.engine.scheduler.kis_ws", double)

    # 사이클 7-C — 풀 헬퍼도 동일 calls 객체에 위임
    async def fake_resend(tr_id, tr_key):
        await double._send_subscribe(tr_id, tr_key, subscribe=True)

    async def fake_unsub_in_pool(tr_id, tr_key):
        await double.unsubscribe(tr_id, tr_key)

    async def fake_subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        await double.subscribe(tr_id, tr_key, bypass_limit=bypass_limit)

    scheduler_env.monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool.resend_subscribe_for_ticker",
        fake_resend,
    )
    scheduler_env.monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool.unsubscribe_in_pool",
        fake_unsub_in_pool,
    )
    scheduler_env.monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool.subscribe",
        fake_subscribe,
    )
    return calls


def _set_last_tick(monkeypatch, *, fresh: list[str], stale: list[str]):
    """scanner.ticker_last_tick 을 격리해 fresh/stale ticker 를 설정한다.

    fresh: now 직전(10s 전) — STALE_FRESHNESS_SECS(60s) 임계 내
    stale: 120s 전 — 임계 초과
    """
    from src.engine import scanner

    now = datetime.now(_KST)
    last_tick: dict[str, datetime] = {}
    for t in fresh:
        last_tick[t] = now - timedelta(seconds=10)
    for t in stale:
        last_tick[t] = now - timedelta(seconds=120)
    monkeypatch.setattr(scanner, "ticker_last_tick", last_tick)
    return last_tick


# ---------------------------------------------------------------------------
# K-1: 전체 fresh → noop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_fresh_noop(scheduler_env):
    sched = scheduler_env.scheduler
    subscribed = {"005930", "000660", "035720"}
    calls = _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(scheduler_env.monkeypatch, fresh=list(subscribed), stale=[])

    # 사전 진입 카운트 비어있어야 함
    sched._stale_retry_count = {"005930": 2}  # 이전 사이클 잔존 — fresh 회복 시 clear 검증

    await sched._check_and_resubscribe_stale()

    assert calls.send_subscribe == []
    assert calls.subscribe == []
    assert calls.unsubscribe == []
    # fresh 회복 시 자동 리셋
    assert sched._stale_retry_count == {}


# ---------------------------------------------------------------------------
# K-2: 1종목 stale, retry=1 → _send_subscribe 1회
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_single_stale_resends(scheduler_env):
    from src.engine.scanner import TICK_TR_ID

    sched = scheduler_env.scheduler
    subscribed = {"005930", "000660", "035720"}
    calls = _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(scheduler_env.monkeypatch, fresh=["000660", "035720"], stale=["005930"])

    sched._stale_retry_count = {}

    await sched._check_and_resubscribe_stale()

    # _send_subscribe 1회 (subscribe=True), unsubscribe 미발생
    assert len(calls.send_subscribe) == 1
    assert calls.send_subscribe[0] == (TICK_TR_ID, "005930", True)
    assert calls.unsubscribe == []
    assert calls.subscribe == []
    assert sched._stale_retry_count == {"005930": 1}


# ---------------------------------------------------------------------------
# K-3: 3종목 stale, retry 이미 10 → 11회 진입 → 강제 재등록
# 사이클 9 (2026-05-18): 임계 STALE_FORCE_REREGISTER_AFTER 3 → 10 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reregister_after_3(scheduler_env):
    from src.engine.scanner import TICK_TR_ID

    sched = scheduler_env.scheduler
    subscribed = {"A00001", "A00002", "A00003", "B11111"}
    calls = _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(
        scheduler_env.monkeypatch,
        fresh=["B11111"],
        stale=["A00001", "A00002", "A00003"],
    )
    # 사이클 9: 임계 10 → 진입 시 retry=11 이 되어 force 분기
    sched._stale_retry_count = {"A00001": 10, "A00002": 10, "A00003": 10}

    await sched._check_and_resubscribe_stale()

    # retry=11 진입 → unsubscribe + subscribe(bypass_limit=True) 각 3회, _send_subscribe 0회
    assert len(calls.unsubscribe) == 3
    assert len(calls.subscribe) == 3
    assert calls.send_subscribe == []
    # 모든 unsubscribe 는 TICK_TR_ID + stale ticker
    unsub_keys = {tr_key for (tr_id, tr_key) in calls.unsubscribe}
    sub_keys = {tr_key for (tr_id, tr_key, _b) in calls.subscribe}
    assert unsub_keys == {"A00001", "A00002", "A00003"}
    assert sub_keys == {"A00001", "A00002", "A00003"}
    # subscribe 는 bypass_limit=True
    assert all(bypass for (_id, _k, bypass) in calls.subscribe)
    # 모든 TR_ID 는 TICK_TR_ID
    assert all(tr_id == TICK_TR_ID for (tr_id, _k) in calls.unsubscribe)
    assert all(tr_id == TICK_TR_ID for (tr_id, _k, _b) in calls.subscribe)

    assert sched._stale_retry_count == {"A00001": 11, "A00002": 11, "A00003": 11}


# ---------------------------------------------------------------------------
# K-4: retry 21회 (=20 초과) → skip
# 사이클 9 (2026-05-18): 임계 *2 = 6 → 20 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_skip_after_6_giveup(scheduler_env):
    sched = scheduler_env.scheduler
    subscribed = {"A00001"}
    calls = _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(scheduler_env.monkeypatch, fresh=[], stale=["A00001"])

    # 사이클 9: 임계 *2 = 20 → 진입 시 retry=21 이 되며 STALE_FORCE_REREGISTER_AFTER*2=20 초과
    sched._stale_retry_count = {"A00001": 20}

    await sched._check_and_resubscribe_stale()

    assert calls.send_subscribe == []
    assert calls.unsubscribe == []
    assert calls.subscribe == []
    assert sched._stale_retry_count == {"A00001": 21}


# ---------------------------------------------------------------------------
# K-5: stale → fresh 회복 → 다시 stale 시 retry 1부터
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_resets_on_recovery(scheduler_env):
    sched = scheduler_env.scheduler
    subscribed = {"A00001"}
    calls = _patch_kis_ws(scheduler_env, subscribed)

    # 사이클 1: stale
    _set_last_tick(scheduler_env.monkeypatch, fresh=[], stale=["A00001"])
    sched._stale_retry_count = {}
    await sched._check_and_resubscribe_stale()
    assert sched._stale_retry_count == {"A00001": 1}

    # 사이클 2: 회복 (fresh)
    _set_last_tick(scheduler_env.monkeypatch, fresh=["A00001"], stale=[])
    await sched._check_and_resubscribe_stale()
    assert sched._stale_retry_count == {}  # clear

    # 사이클 3: 다시 stale → retry 1부터
    _set_last_tick(scheduler_env.monkeypatch, fresh=[], stale=["A00001"])
    await sched._check_and_resubscribe_stale()
    assert sched._stale_retry_count == {"A00001": 1}


# ---------------------------------------------------------------------------
# K-6: mixed — 첫 회 stale + 4회째 stale 동시 카운트
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mixed_resend_and_force(scheduler_env):
    from src.engine.scanner import TICK_TR_ID

    sched = scheduler_env.scheduler
    subscribed = {"AAAAAA", "BBBBBB"}
    calls = _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(scheduler_env.monkeypatch, fresh=[], stale=["AAAAAA", "BBBBBB"])

    # AAAAAA 첫 진입 (retry 0 → 1), BBBBBB 10 → 11 (force)
    # 사이클 9 (2026-05-18): force 임계 3 → 10 갱신
    sched._stale_retry_count = {"BBBBBB": 10}

    await sched._check_and_resubscribe_stale()

    # AAAAAA: send_subscribe 1회
    assert (TICK_TR_ID, "AAAAAA", True) in calls.send_subscribe
    assert len(calls.send_subscribe) == 1
    # BBBBBB: force (unsubscribe + subscribe)
    assert any(tr_key == "BBBBBB" for (_id, tr_key) in calls.unsubscribe)
    assert any(tr_key == "BBBBBB" for (_id, tr_key, _b) in calls.subscribe)
    assert len(calls.unsubscribe) == 1
    assert len(calls.subscribe) == 1

    assert sched._stale_retry_count == {"AAAAAA": 1, "BBBBBB": 11}


# ---------------------------------------------------------------------------
# K-7: _running=False → 루프 즉시 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_running_false_exits(scheduler_env, monkeypatch):
    """_stale_watcher_loop 가 _running=False 진입 즉시 break 하고 더 이상 check 호출 안 함."""
    sched = scheduler_env.scheduler
    subscribed = {"A00001"}
    _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(scheduler_env.monkeypatch, fresh=[], stale=["A00001"])

    check_calls = {"n": 0}

    async def fake_check(self):
        check_calls["n"] += 1

    # bound method 패치
    monkeypatch.setattr(
        type(sched), "_check_and_resubscribe_stale", fake_check, raising=True
    )

    sched._running = False  # 시작부터 False
    await sched._stale_watcher_loop()

    # _running=False 면 sleep 후 즉시 break — check 호출 0회
    assert check_calls["n"] == 0


# ---------------------------------------------------------------------------
# K-8: 예외 복원력 — _check 가 raise 해도 다음 사이클 정상
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exception_resilient(scheduler_env, monkeypatch, caplog):
    """_check_and_resubscribe_stale 가 1회 raise 해도 loop 가 죽지 않고 다음 사이클 진행."""
    import logging as _logging

    sched = scheduler_env.scheduler
    subscribed = {"A00001"}
    _patch_kis_ws(scheduler_env, subscribed)

    call_count = {"n": 0}

    async def fake_check(self):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        sched._running = False  # 2회째에 종료

    monkeypatch.setattr(
        type(sched), "_check_and_resubscribe_stale", fake_check, raising=True
    )

    sched._running = True
    caplog.set_level(_logging.ERROR, logger="src.engine.scheduler")
    await sched._stale_watcher_loop()

    assert call_count["n"] == 2
    # 첫 사이클 예외 후에도 두 번째 호출 발생 → loop 가 죽지 않음 확인
    # logger.exception 메시지 확인 (선택)
    assert any("stale_watcher" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# K-9: _reset_daily_state 가 _stale_retry_count 를 clear
# ---------------------------------------------------------------------------
def test_reset_clears_retry_count(scheduler_env):
    sched = scheduler_env.scheduler
    sched._stale_retry_count = {"A00001": 2, "B00002": 5}

    sched._reset_daily_state()

    assert sched._stale_retry_count == {}


# ---------------------------------------------------------------------------
# K-10: subscribed 가 비어있으면 noop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_subscribed_noop(scheduler_env):
    sched = scheduler_env.scheduler
    subscribed: set[str] = set()
    calls = _patch_kis_ws(scheduler_env, subscribed)
    _set_last_tick(scheduler_env.monkeypatch, fresh=[], stale=[])

    sched._stale_retry_count = {"PHANTOM": 2}

    await sched._check_and_resubscribe_stale()

    assert calls.send_subscribe == []
    assert calls.subscribe == []
    assert calls.unsubscribe == []
    # subscribed empty 면 stale 평가 자체 skip — retry_count 보존
    assert sched._stale_retry_count == {"PHANTOM": 2}
