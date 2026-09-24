"""cycle357 N1 — `[no_feed_held]` 판정을 KRX 연속체결 창(09:00~)으로 제한한다.

## 사실 (팀장 지시서 인용)

운영 09-22·09-23 08:00:1x 에 `[no_feed_held] tickers=[...]` 가 하루 1회 뜬다.
NXT 프리장(08:00~09:00) 동안 `nxt_tradable=False` 종목은 채널 리졸버가 전환
횟수를 아끼려고 **KRX 전용 채널**에 미리 둔다(`src/engine/CLAUDE.md` 「시세
채널」절) — 그런데 그 시간 KRX 는 시가 단일가라 **어느 채널이든** 연속체결
프레임이 정의상 0 이다. `[no_feed_held]` 판정을 그 구간에 돌리면 이 정의상
공백을 「무송출」로 오판한다 — **08:00 판정은 거짓 경보다.**

## 이 사이클이 바꾸는 것 / 바꾸지 않는 것

바꾸는 것 = `_maybe_emit_no_feed_held` 에 **KRX 연속체결 시작(09:00, K3
REGULAR) 이전이면 판정을 억제**하는 게이트 하나뿐이다. cap 을 소비하지 않고
그냥 돌아간다 — 09:00 이후 같은 날 진짜 무송출이면 그때 1회/일 cap 이 정상
소비된다(§T2).

바꾸지 않는 것:
- HIGH 재등록(SEND/스탬프)·구독 행위 — 이 파일의 게이트는 `_maybe_emit_no_feed_held`
  안에만 있고, `check_and_resubscribe_stale` 의 재등록 경로(`pool.subscribe` 등)는
  손대지 않는다.
- **09:00 이후 진짜 무송출은 여전히 뜬다**(§T4·§T7 — 「진짜 경보 보존」).
- 경계 판정 실패(표 조회 예외)는 **억제하지 않는 방향**으로 fail-open 한다(§T5)
  — 관찰 마커를 죽이는 fail-open 은 관찰 자체를 무력화한다.

| ID | 검사 |
|----|------|
| T1 | 08:00:15(프리장) — `_is_before_krx_continuous_open` True |
| T2 | 09:05:00 — False, cap 비소비(프리장 호출은 cap 을 건드리지 않음) |
| T3 | 09:00:00 정각 — 경계 포함(= 창 이전 아님) |
| T4 | 08:00:15 — `_maybe_emit_no_feed_held` 무로그 + cap 미소비(같은 날 09:00+ 재호출 시 정상 발화) |
| T5 | `tick_channel_clock` 조회 실패 — 프리장이어도 억제하지 않는다(fail-open) |
| T6 | 09:05:00 — `_maybe_emit_no_feed_held` 정상 발화, 메시지에 `H0UNCNT0` 잔재 없음 |
| T7 | `check_and_resubscribe_stale` 전체 사이클, 08:00:15 프리장 — `[no_feed_held]` 0행 |
| T8 | `check_and_resubscribe_stale` 전체 사이클, 09:05:00 — `[no_feed_held]` 1행(진짜 경보 보존) |
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


@pytest.fixture(autouse=True)
def _reset_held_cap():
    """모듈 전역 `[no_feed_held]` cap 을 테스트마다 새 인스턴스로 교체한다.

    cycle252 W7 선재 결함(실제 KST 날짜와 freeze_time 날짜 충돌)을 답습하지
    않기 위해 `test_cycle252_stale_watcher_no_feed.py` 의 관례를 그대로 쓴다.
    """
    from src.engine.daily_emit_cap import KstDailyEmitCap

    core = _core()
    saved = core._no_feed_held_logged
    core._no_feed_held_logged = KstDailyEmitCap()
    yield
    core._no_feed_held_logged = saved


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


# ===========================================================================
# T1~T3 — 판정 함수 `_is_before_krx_continuous_open` 직접 검사
# ===========================================================================
def test_t1_pre_market_time_is_before_krx_open():
    core = _core()
    now = datetime(2026, 9, 23, 8, 0, 15, tzinfo=KST)
    assert core._is_before_krx_continuous_open(now) is True


def test_t2_post_open_time_is_not_before_krx_open():
    core = _core()
    now = datetime(2026, 9, 23, 9, 5, 0, tzinfo=KST)
    assert core._is_before_krx_continuous_open(now) is False


def test_t3_boundary_exactly_at_open_is_not_before():
    """09:00:00 정각은 「창 이전」이 아니다 — 경계 포함."""
    core = _core()
    now = datetime(2026, 9, 23, 9, 0, 0, tzinfo=KST)
    assert core._is_before_krx_continuous_open(now) is False


# ===========================================================================
# T4 — 프리장 호출은 무로그 + cap 미소비
# ===========================================================================
def test_t4_pre_market_call_is_silent_and_does_not_consume_cap(caplog):
    core = _core()
    now = datetime(2026, 9, 23, 8, 0, 15, tzinfo=KST)
    caplog.set_level(logging.DEBUG)

    core._maybe_emit_no_feed_held({"003490"}, now)

    held = [r for r in caplog.records if _HELD in r.getMessage()]
    assert held == [], f"프리장 호출은 무로그여야 한다 — actual={[r.getMessage() for r in held]}"
    assert core._no_feed_held_logged.should_emit(core._NO_FEED_HELD_KEY, now=now) is True, (
        "프리장 억제는 cap 을 건드리지 않는다 — 09:00 이후 같은 날 재호출이 여전히 발화해야 한다"
    )


# ===========================================================================
# T5 — 시계 조회 실패는 억제하지 않는 방향으로 fail-open
# ===========================================================================
def test_t5_gate_fails_open_when_clock_lookup_raises(monkeypatch, caplog):
    core = _core()
    now = datetime(2026, 9, 23, 8, 0, 15, tzinfo=KST)
    caplog.set_level(logging.DEBUG)

    import src.engine.tick_channel_clock as clock_mod

    def _boom(_on_date):
        raise RuntimeError("market_state lookup failed")

    monkeypatch.setattr(clock_mod, "_windows", _boom)

    core._maybe_emit_no_feed_held({"003490"}, now)

    held = [r for r in caplog.records if _HELD in r.getMessage() and r.levelno >= logging.WARNING]
    assert len(held) == 1, (
        f"시계 조회 실패는 판정을 억제하지 않는 방향으로 fail-open 해야 한다 — "
        f"actual={[r.getMessage() for r in caplog.records]}"
    )


# ===========================================================================
# T6 — 09:00 이후 정상 발화 + 메시지 문구에 H0UNCNT0 잔재 없음
# ===========================================================================
def test_t6_post_open_emits_without_unified_channel_wording(caplog):
    core = _core()
    now = datetime(2026, 9, 23, 9, 5, 0, tzinfo=KST)
    caplog.set_level(logging.DEBUG)

    core._maybe_emit_no_feed_held({"003490"}, now)

    held = [r for r in caplog.records if _HELD in r.getMessage() and r.levelno >= logging.WARNING]
    assert len(held) == 1, f"09:00 이후는 정상 발화 — actual={[r.getMessage() for r in caplog.records]}"
    msg = held[0].getMessage()
    assert "H0UNCNT0" not in msg, f"통합 채널(H0UNCNT0) 잔재 문구 — {msg!r}"
    assert "003490" in msg


# ===========================================================================
# T7~T8 — 전체 사이클 (`check_and_resubscribe_stale`) 관통 검증
# ===========================================================================
async def test_t7_full_cycle_pre_market_no_false_alarm(monkeypatch, caplog):
    """09-22/09-23 실측 재현 — 08:00:1x 전체 사이클에서 `[no_feed_held]` 0행."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    with freeze_time("2026-09-23 08:00:15+09:00"):
        now = datetime(2026, 9, 23, 8, 0, 15, tzinfo=KST)
        _make_pool(monkeypatch, ["003490", "006340"])
        _setup_ticks(monkeypatch, fresh=["006340"], now=now)
        monkeypatch.setattr(core, "asyncio", _SleepSpy())
        _patch_registry(monkeypatch, no_feed={"003490"})
        sched = _make_sched(positions=["003490"])

        await core.check_and_resubscribe_stale(sched)

    held = [r for r in caplog.records if _HELD in r.getMessage()]
    assert held == [], (
        f"08:00:1x 프리장 — 거짓 경보 재현 방지, actual={[r.getMessage() for r in held]}"
    )


async def test_t8_full_cycle_post_open_genuine_alarm_preserved(monkeypatch, caplog):
    """09:00 이후 — HIGH∩no_feed 종목이 있으면 여전히 1행 발화(진짜 경보 보존)."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    with freeze_time("2026-09-23 09:05:00+09:00"):
        now = datetime(2026, 9, 23, 9, 5, 0, tzinfo=KST)
        _make_pool(monkeypatch, ["003490", "006340"])
        _setup_ticks(monkeypatch, fresh=["006340"], now=now)
        monkeypatch.setattr(core, "asyncio", _SleepSpy())
        _patch_registry(monkeypatch, no_feed={"003490"})
        sched = _make_sched(positions=["003490"])

        await core.check_and_resubscribe_stale(sched)

    held = [r for r in caplog.records if _HELD in r.getMessage() and r.levelno >= logging.WARNING]
    assert len(held) == 1, (
        f"09:00 이후 진짜 무송출 보유는 여전히 발화 — actual={[r.getMessage() for r in caplog.records]}"
    )
    assert "003490" in held[0].getMessage()
