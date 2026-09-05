"""cycle252 tester 보강 — 뮤테이션 escape 봉인 + 소비처 경계면 실증.

> 정본 명세: `spec_cycle252_no_feed_churn.md` §2(c) · §1 D2 · §5(c)(e)
> tdd-engineer 의 W1~W9 가 잡지 못한 두 escape 와 소비처 1건을 고정한다.

| ID | 검사 | 뮤테이션 표적 |
|----|------|--------------|
| T1 | 전부 fresh(stale=∅) 사이클에도 `[no_feed_held]` 1회 발화 (§2(c) "stale 여부 무관") | held 판정을 `if not stale_tickers: return` 뒤로 이동 |
| T2 | `_maybe_emit_no_feed_held` 는 peek→로그→mark — 로그 실패 시 mark 안 됨 = 다음 사이클 재발화 | mark-before-log |
| T3 | 소비처 `stale_universe_guard`: LOW no_feed 종목이 SEND 0 인 채 r=6 홀드 → 저유동이면 여전히 축출(unsubscribe) | 홀드 값 `MAX` / 홀드 삭제 |
| T4 | `_maybe_emit_no_feed_held` 는 자기 예외를 **흡수**한다 — 호출부가 stale 루프 **앞**이라 전파되면 그 사이클의 HIGH 재등록까지 빠진다 (tester F-1) | 헬퍼 try/except 삭제 |
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit
KST = timezone(timedelta(hours=9))
_HELD = "[no_feed_held]"


def _core():
    from src.engine import stale_watcher_core as core
    return core


class _SleepSpy:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def sleep(self, secs: float) -> None:
        self.sleeps.append(secs)


def _make_pool(monkeypatch, subscribed) -> MagicMock:
    import src.realtime.websocket_pool as wp_mod
    pool = MagicMock()
    pool.get_subscribed_tickers = lambda: set(subscribed)
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock()
    pool.unsubscribe = AsyncMock()
    pool.get_subscriptions_by_session = MagicMock(return_value={})
    pool._subscribed_at = {}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    return pool


def _setup_ticks(monkeypatch, *, stale=(), fresh=(), now=None):
    import src.engine.scanner as scanner_mod
    base = now or datetime.now(KST)
    lt = {}
    for t in stale:
        lt[t] = base - timedelta(seconds=120)
    for t in fresh:
        lt[t] = base - timedelta(seconds=5)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", lt)
    return lt


def _make_sched(*, positions=(), next_day_clear=(), retry=None):
    from src.engine.scheduler import TradingScheduler
    s = TradingScheduler.__new__(TradingScheduler)
    s._stale_retry_count = dict(retry or {})
    s._stale_last_resubscribe_at = {}
    s._stale_force_retry_history = {}
    s._pending_next_day_clear = set(next_day_clear)
    s._universe_excluded_today = set()
    s._running = True
    s._STALE_DETAIL_TICKER_CAP = 20
    st = MagicMock()
    st.positions = {t: MagicMock() for t in positions}
    strat = MagicMock()
    strat.state = st
    reg = MagicMock()
    reg.all = MagicMock(return_value=[strat])
    reg.is_ticker_held_by_any = MagicMock(side_effect=lambda t: t in set(positions))
    s.registry = reg
    return s


def _patch_registry(monkeypatch, no_feed):
    from src.engine import no_feed_registry as reg
    reg.reset_state_for_test()

    async def _ensure(tickers, **kw):
        return None

    monkeypatch.setattr(reg, "ensure_fresh", _ensure)
    monkeypatch.setattr(reg, "is_no_feed", lambda t: t in set(no_feed))


def _reset_held_cap(core):
    core._no_feed_held_logged.reset_daily()


# ===========================================================================
# T1 — stale=∅ 사이클에도 [no_feed_held] 발화 (§2(c) "stale 여부와 무관하게 매 사이클 계산")
# ===========================================================================
async def test_t1_no_feed_held_emits_when_all_fresh(monkeypatch, caplog):
    """보유 no_feed 종목이 REST 폴로 `ticker_last_tick` 을 갱신받아 stale 로 안 잡히는
    날(포렌식 ③ "003490 리셋은 REST 폴 때문")에도 'WS blind' 사실은 기록돼야 한다.
    held 판정을 `if not stale_tickers: return` 뒤로 옮기면 그런 날은 0행이 된다.
    """
    core = _core()
    _reset_held_cap(core)
    caplog.set_level(logging.DEBUG)
    with freeze_time("2026-09-07 10:00:00+09:00"):
        now = datetime(2026, 9, 7, 10, 0, tzinfo=KST)
        pool = _make_pool(monkeypatch, ["003490", "006340"])
        _setup_ticks(monkeypatch, fresh=["003490", "006340"], now=now)
        monkeypatch.setattr(core, "asyncio", _SleepSpy())
        _patch_registry(monkeypatch, no_feed={"003490"})
        sched = _make_sched(positions=["003490"], retry={"006340": 3})

        await core.check_and_resubscribe_stale(sched)

    held = [r for r in caplog.records if _HELD in r.getMessage()]
    assert len(held) == 1, f"전부 fresh 사이클에도 {_HELD} 1행 — actual={[r.getMessage() for r in held]}"
    assert held[0].levelno >= logging.WARNING
    # 현행 회복 분기(모두 fresh → retry clear)는 그대로
    assert sched._stale_retry_count == {}, "모두 fresh → 누적 retry 리셋(현행) 보존"
    pool.subscribe.assert_not_awaited()


# ===========================================================================
# T2 — peek→로그→mark: 로그가 실패하면 mark 되지 않아 다음 사이클 재발화
# ===========================================================================
def test_t2_no_feed_held_peek_log_mark_order(monkeypatch, caplog):
    """cycle226 D-3 순서 계약. mark 를 먼저 하면 로그 자기실패가 그날 관측을 지운다.
    전파 정책(흡수/전파)과 무관하게 'mark 미수행' 만 단언한다.
    """
    core = _core()
    _reset_held_cap(core)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=KST)

    real_logger = core.logger
    calls = {"n": 0}

    class _Boom:
        def warning(self, *a, **k):
            calls["n"] += 1
            raise RuntimeError("logger down")

        def __getattr__(self, name):
            return getattr(real_logger, name)

    monkeypatch.setattr(core, "logger", _Boom())
    try:
        core._maybe_emit_no_feed_held({"003490"}, now)
    except RuntimeError:
        pass
    assert calls["n"] == 1, "로그 시도 1회"
    assert core._no_feed_held_logged.should_emit(core._NO_FEED_HELD_KEY, now=now) is True, (
        "로그 실패 시 mark 되면 안 된다 (peek→로그→mark) — mark-before-log 회귀"
    )

    monkeypatch.setattr(core, "logger", real_logger)
    caplog.set_level(logging.DEBUG)
    core._maybe_emit_no_feed_held({"003490"}, now)
    # CI 는 루트 로거가 DEBUG 라 첫 시도의 실패 흔적(`[no_feed_held] emit 실패`, debug)도
    # 캡처된다 — 관측 계약은 WARNING 행 1회이므로 레벨로 거른다(cycle252 CI 핫픽스).
    emitted = [r for r in caplog.records if _HELD in r.getMessage() and r.levelno >= logging.WARNING]
    assert len(emitted) == 1, f"복구 후 같은 날 WARNING 1회 발화 — actual={[r.getMessage()[:60] for r in emitted]}"
    assert core._no_feed_held_logged.should_emit(core._NO_FEED_HELD_KEY, now=now) is False, (
        "성공 후 mark"
    )


# ===========================================================================
# T3 — 소비처: stale_universe_guard 축출 경로 보존 (§1 D2 홀드 6 > MAX 5)
# ===========================================================================
async def test_t3_universe_guard_still_evicts_low_volume_no_feed(monkeypatch):
    """K watcher 가 LOW no_feed 종목을 SEND 0 으로 7사이클 돌린 뒤(r=6 홀드),
    `evaluate_universe_guard` 가 `retries > MAX_STALE_RETRIES ∧ acml_vol < 1만` 으로
    여전히 축출(`_universe_excluded_today` 등록 + `kis_ws_pool.unsubscribe`)한다.
    홀드 값이 5 이거나 홀드가 빠져 r 이 다른 경로로 새면 이 경계면이 끊긴다.
    """
    from src.engine.stale_diagnostics import MAX_STALE_RETRIES
    from src.engine.stale_universe_guard import evaluate_universe_guard
    import src.api.quotation as q_mod
    import src.engine.tick_volume as tv_mod
    from src.engine.scanner import TICK_TR_ID

    core = _core()
    _reset_held_cap(core)
    pool = _make_pool(monkeypatch, ["005935"])
    _setup_ticks(monkeypatch, stale=["005935"])
    monkeypatch.setattr(core, "asyncio", _SleepSpy())
    _patch_registry(monkeypatch, no_feed={"005935"})
    sched = _make_sched()

    for _ in range(7):
        await core.check_and_resubscribe_stale(sched)

    assert sched._stale_retry_count["005935"] == MAX_STALE_RETRIES + 1, (
        f"7사이클 후 r 홀드 = MAX+1 — actual={sched._stale_retry_count}"
    )
    assert sched._stale_retry_count["005935"] > MAX_STALE_RETRIES
    pool.subscribe.assert_not_awaited()
    pool.unsubscribe_in_pool.assert_not_awaited()

    async def _ccnl(ticker, *a, **k):
        return {"today_volume": 30, "last_cntg_hour": "101500"}

    async def _acml(ticker, *a, **k):
        return 500  # < UNIVERSE_LOW_VOLUME_THRESHOLD(10,000)

    monkeypatch.setattr(q_mod, "inquire_ccnl", _ccnl)
    monkeypatch.setattr(q_mod, "inquire_acml_vol", _acml)
    monkeypatch.setattr(tv_mod, "get_observed_acml_vol", lambda t: None)
    import src.engine.stale_universe_guard as ug_mod
    monkeypatch.setattr(ug_mod, "asyncio", _SleepSpy())

    await evaluate_universe_guard(sched, ["005935"])

    assert "005935" in sched._universe_excluded_today, "저유동 no_feed 는 여전히 축출"
    pool.unsubscribe.assert_awaited_once_with(TICK_TR_ID, "005935")


async def test_t3b_universe_guard_ignores_no_feed_below_threshold(monkeypatch):
    """대조군 — r ≤ MAX(5) 인 동안은 현행대로 평가 대상 아님(KIS 호출 0)."""
    from src.engine.stale_universe_guard import evaluate_universe_guard
    import src.api.quotation as q_mod

    core = _core()
    _reset_held_cap(core)
    pool = _make_pool(monkeypatch, ["005935"])
    _setup_ticks(monkeypatch, stale=["005935"])
    monkeypatch.setattr(core, "asyncio", _SleepSpy())
    _patch_registry(monkeypatch, no_feed={"005935"})
    sched = _make_sched()
    for _ in range(3):
        await core.check_and_resubscribe_stale(sched)
    assert sched._stale_retry_count["005935"] == 3

    called = {"n": 0}

    async def _ccnl(ticker, *a, **k):
        called["n"] += 1
        return {"today_volume": 30, "last_cntg_hour": "101500"}

    monkeypatch.setattr(q_mod, "inquire_ccnl", _ccnl)
    await evaluate_universe_guard(sched, ["005935"])
    assert called["n"] == 0
    assert "005935" not in sched._universe_excluded_today
    pool.unsubscribe.assert_not_awaited()


# ===========================================================================
# T4 — 관측기 자기 예외 흡수 (tester F-1): 헬퍼는 던지지 않고, 사이클은 HIGH 재등록을 완주
# ===========================================================================
class _BoomLogger:
    """`warning` 만 폭발하는 로거 대역 — 나머지는 실제 로거로 위임."""

    def __init__(self, real, calls: dict):
        self._real = real
        self._calls = calls

    def warning(self, *a, **k):
        self._calls["n"] += 1
        raise RuntimeError("logger down")

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_t4_no_feed_held_helper_absorbs_its_own_exception(monkeypatch, caplog):
    """cycle237/242 계약 — emit 헬퍼는 예외를 흡수하고 흔적(debug)만 남긴다.

    T2 는 전파 정책에 중립(흡수/전파 양쪽 통과)이라 "try/except 삭제" 뮤테이션을 못
    죽인다. 여기서는 **던지지 않음** 자체를 단언한다 + peek→로그→mark 는 그대로
    (실패 시 mark 안 됨).
    """
    core = _core()
    _reset_held_cap(core)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=KST)
    calls = {"n": 0}
    monkeypatch.setattr(core, "logger", _BoomLogger(core.logger, calls))
    caplog.set_level(logging.DEBUG)

    core._maybe_emit_no_feed_held({"003490"}, now)  # raise 하면 즉시 FAIL

    assert calls["n"] == 1, "로그 시도 1회"
    assert core._no_feed_held_logged.should_emit(core._NO_FEED_HELD_KEY, now=now) is True, (
        "실패한 emit 은 mark 되지 않는다 (peek→로그→mark)"
    )
    # 사이클 258 카드 #5 — 흡수 흔적이 `observer_trace.trace_observer_failure` 단일
    # 정책으로 수렴하며 정확한 한글 문구가 `"%s observer_failed key=%s"` 로
    # 표준화됐다(4갈래 정책 통일이 이 리팩토링의 목적이므로 문구 자체는 byte 불변
    # 대상이 아니다 — `_HELD`/`실패` 문구가 아니라 표준 마커+`observer_failed`로 검사).
    trace = [r for r in caplog.records
             if r.levelno == logging.DEBUG and "observer_failed" in r.getMessage()
             and core._NO_FEED_HELD_KEY in r.getMessage()]
    assert len(trace) == 1, (
        f"흡수 흔적 debug 1행 — actual={[r.getMessage() for r in caplog.records]}"
    )
    assert trace[0].exc_info is not None, "스택트레이스(exc_info) 동반"


async def test_t4b_high_reregistration_survives_no_feed_held_failure(monkeypatch):
    """F-1 의 실제 피해 시나리오 — 관측 실패가 **보유 종목 HIGH 재등록**을 끊으면 안 된다.

    호출부 `if high_tickers: … _maybe_emit_no_feed_held(...)` 는 `if not stale_tickers:
    return` 과 stale 루프 **앞**에 있다. 헬퍼가 던지면 `_stale_watcher_loop` 이 예외를
    흡수해 프로세스는 살지만 그 사이클의 모든 재등록(HIGH 포함)이 생략되고, 결함이
    지속되면 120s 마다 반복 = 관측 개선이 손절 시세 복구를 막는 최악의 교환.
    """
    core = _core()
    _reset_held_cap(core)
    calls = {"n": 0}
    with freeze_time("2026-09-07 10:00:00+09:00"):
        now = datetime(2026, 9, 7, 10, 0, tzinfo=KST)
        pool = _make_pool(monkeypatch, ["003490", "006340"])
        _setup_ticks(monkeypatch, stale=["003490", "006340"], now=now)
        monkeypatch.setattr(core, "asyncio", _SleepSpy())
        _patch_registry(monkeypatch, no_feed={"003490"})
        sched = _make_sched(positions=["003490"])
        monkeypatch.setattr(core, "logger", _BoomLogger(core.logger, calls))

        await core.check_and_resubscribe_stale(sched)  # raise 하면 즉시 FAIL

    assert calls["n"] == 1, "[no_feed_held] 시도 1회 (그 외 warning 경로 미진입)"
    # HIGH(보유 003490, no_feed) — 현행 byte 동일: unsub/sub + HIGH/bypass + 스탬프 + r=1
    subs = {c.args[1]: c.kwargs for c in pool.subscribe.await_args_list}
    assert "003490" in subs, f"HIGH 재등록이 관측 실패에 끊겼다 — subscribe calls={subs!r}"
    assert subs["003490"].get("priority") == "HIGH"
    assert subs["003490"].get("bypass_limit") is True
    assert "003490" in sched._stale_last_resubscribe_at
    assert sched._stale_retry_count["003490"] == 1
    # LOW 정상 종목(006340)도 그대로 재등록
    assert subs.get("006340", {}).get("priority") == "LOW"
    assert pool.unsubscribe_in_pool.await_count == 2
    # collector 까지 도달 (사이클 완주)
    assert core._stale_watcher_collector and core._stale_watcher_collector[-1]["stale"] == 2
    core._stale_watcher_collector.clear()
