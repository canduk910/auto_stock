"""cycle371 Red — K stale watcher(`check_and_resubscribe_stale`) 동시호가 LOW-scoped skip.

> 배경 = `_workspace/00_URGENT_WORKLIST.md` 「남은 일」 C 절 cycle368 후속(a):
> "per-ticker 프레임에 110/121 이 오면 K watcher 의 동시호가 조기 반환이 보유 종목도
> 건너뛴다(HIGH 면제 검토)". cycle216 이 `resubscribe_stale_priority`(5분 우선 재구독)에
> 이미 준 LOW-scoped skip 을 K watcher(120초 주기)에도 미러한다.

## 시정 전(Red 기준) 행위
`check_and_resubscribe_stale` 는 `is_call_auction_now()` 가 True 면 HIGH/LOW 구분 없이
*전체* stale 판정을 지연하고 즉시 return 한다 — 보유 종목(HIGH)도 그 120초 사이클엔
재구독되지 않는다. 09:00 갭개장·15:20 마감 직전처럼 보유 종목 손절이 특히 중요한
바로 그 시간대에 HIGH 재구독이 8분(동시호가 창 길이)까지 밀릴 수 있다(005935 사고와
같은 패턴 — 사이클 29 주석 참조).

## 시정 후(Green 기준) 행위
- HIGH(보유·`_pending_next_day_clear`) stale 종목은 동시호가 중에도 그대로
  `unsubscribe_in_pool` → `subscribe(priority="HIGH", bypass_limit=True)` 강제 재등록.
- LOW stale 종목은 SEND 0 · retry 카운터 무변경(그 사이클에 아예 손대지 않는다 —
  cycle252 no_feed skip 과 달리 "이번엔 아직 보지도 않았다"는 뜻이라 +1 도 하지 않는다).
- `[stale_skip_call_auction]` WARNING 은 계속 발화(기존 grep 연속성) + `low=`/`high=`
  카운트 필드 추가.
- HIGH stale 이 없으면(LOW 뿐이거나 아무것도 stale 이 아니면) 기존 「전체 skip」과
  동일하게 조기 반환 + 누적 retry 카운터 보존(cycle162 원 계약, 회귀 가드
  `test_cycle162_call_auction_stale_skip.py::test_G_162_E_10` 와
  `test_cycle252_stale_watcher_no_feed.py::test_w9_...` 로 이미 봉인).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _core():
    from src.engine import stale_watcher_core as core

    return core


@pytest.fixture(autouse=True)
def _reset_no_feed_held_cap():
    """모듈 전역 `[no_feed_held]` cap 을 테스트마다 초기화(cycle252 답습 — 날짜 의존 차단)."""
    from src.engine import stale_watcher_core as core
    from src.engine.daily_emit_cap import KstDailyEmitCap

    saved = core._no_feed_held_logged
    core._no_feed_held_logged = KstDailyEmitCap()
    yield
    core._no_feed_held_logged = saved


class _SleepSpy:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def sleep(self, secs: float) -> None:
        self.sleeps.append(secs)


def _patch_no_sleep(monkeypatch, mod) -> _SleepSpy:
    spy = _SleepSpy()
    monkeypatch.setattr(mod, "asyncio", spy)
    return spy


def _make_pool(monkeypatch, subscribed):
    import src.realtime.websocket_pool as wp_mod

    pool = MagicMock()
    pool.get_subscribed_tickers = lambda: set(subscribed)
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock()
    pool.get_subscriptions_by_session = MagicMock(return_value={})
    pool._subscribed_at = {}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    return pool


def _setup_ticks(monkeypatch, *, stale=(), now=None):
    import src.engine.scanner as scanner_mod

    base = now or datetime.now(KST)
    last_tick = {t: base - timedelta(seconds=120) for t in stale}
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", last_tick)
    return last_tick


def _make_sched(*, positions=(), next_day_clear=(), retry=None, last_at=None):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = dict(retry or {})
    sched._stale_last_resubscribe_at = dict(last_at or {})
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = set(next_day_clear)
    sched._running = True
    sched._STALE_DETAIL_TICKER_CAP = 20

    fake_state = MagicMock()
    fake_state.positions = {t: MagicMock() for t in positions}
    fake_strategy = MagicMock()
    fake_strategy.state = fake_state
    fake_registry = MagicMock()
    fake_registry.all = MagicMock(return_value=[fake_strategy])
    sched.registry = fake_registry
    return sched


def _patch_no_feed_registry(monkeypatch):
    """no_feed 판정은 이 사이클의 관심사가 아니다 — 전부 「미분류/무송출 아님」으로 고정."""
    from src.engine import no_feed_registry as reg

    monkeypatch.setattr(reg, "ensure_fresh", AsyncMock(return_value=None))
    monkeypatch.setattr(reg, "is_no_feed", lambda t: False)


def _capture_scheduler_warnings():
    """stale_watcher_core 는 `logging.getLogger("src.engine.scheduler")` 바인딩(사이클 60 I1)."""
    logger = logging.getLogger("src.engine.scheduler")
    handler = logging.Handler()
    handler.setLevel(logging.WARNING)
    records: list[logging.LogRecord] = []
    handler.emit = records.append  # type: ignore[assignment]
    return logger, handler, records


# ===========================================================================
# T1 (핵심 Red) — 동시호가 중 HIGH 는 재구독, LOW 는 skip
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 15:25:00", tz_offset=-9)
async def test_t1_call_auction_high_resubscribed_low_skipped(monkeypatch):
    from src.engine.session import session_tracker

    core = _core()
    pool = _make_pool(monkeypatch, ["005930", "035420", "035720"])
    _setup_ticks(monkeypatch, stale=["005930", "035420", "035720"])
    _patch_no_sleep(monkeypatch, core)
    _patch_no_feed_registry(monkeypatch)
    monkeypatch.setattr(
        session_tracker, "is_call_auction_now", lambda now=None: True, raising=False,
    )
    sched = _make_sched(positions=["005930"])  # HIGH 1 + LOW 2

    logger, handler, records = _capture_scheduler_warnings()
    logger.addHandler(handler)
    try:
        await core.check_and_resubscribe_stale(sched)
    finally:
        logger.removeHandler(handler)

    # HIGH 종목은 동시호가 중에도 강제 재등록(bypass=True)
    high_calls = [c for c in pool.subscribe.await_args_list if c.args[1] == "005930"]
    assert len(high_calls) == 1, (
        "동시호가 중에도 HIGH(보유) 종목은 재구독 의무 — 사이클 216 미러. "
        f"실제 subscribe 호출: {pool.subscribe.await_args_list!r}"
    )
    assert high_calls[0].kwargs.get("priority") == "HIGH"
    assert high_calls[0].kwargs.get("bypass_limit") is True
    assert sched._stale_retry_count.get("005930") == 1

    # LOW 종목은 완전 skip — subscribe 미호출 + retry 카운터 무변경(키 자체가 없어야 함)
    low_calls = [
        c for c in pool.subscribe.await_args_list if c.args[1] in ("035420", "035720")
    ]
    assert low_calls == [], (
        f"동시호가 중 LOW 는 재구독 금지 의무. 실제: {low_calls!r}"
    )
    assert "035420" not in sched._stale_retry_count
    assert "035720" not in sched._stale_retry_count

    # `[stale_skip_call_auction]` 은 계속 발화 + low=2 high=1 카운트 병기
    warns = [r.getMessage() for r in records if "[stale_skip_call_auction]" in r.getMessage()]
    assert len(warns) == 1, f"동시호가 WARNING 1행 의무. 실제: {warns!r}"
    assert "low=2" in warns[0] and "high=1" in warns[0], (
        f"low/high 카운트 병기 의무. 실제: {warns[0]!r}"
    )


# ===========================================================================
# T2 (불변 회귀) — 동시호가 중 LOW 뿐이면 기존 전체 skip 과 동일(retry 카운터 보존)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 15:25:00", tz_offset=-9)
async def test_t2_call_auction_all_low_preserves_full_skip_contract(monkeypatch):
    from src.engine.session import session_tracker

    core = _core()
    pool = _make_pool(monkeypatch, ["035420", "035720"])
    _setup_ticks(monkeypatch, stale=["035420", "035720"])
    _patch_no_sleep(monkeypatch, core)
    _patch_no_feed_registry(monkeypatch)
    monkeypatch.setattr(
        session_tracker, "is_call_auction_now", lambda now=None: True, raising=False,
    )
    sched = _make_sched(retry={"035420": 3})  # HIGH 0

    await core.check_and_resubscribe_stale(sched)

    pool.subscribe.assert_not_awaited()
    pool.unsubscribe_in_pool.assert_not_awaited()
    # 기존 계약 그대로 — clear() 도 겪지 않고, 있던 값도 그대로
    assert sched._stale_retry_count == {"035420": 3}


# ===========================================================================
# T3 (불변 회귀) — 동시호가가 아니면 회귀 0(HIGH+LOW 모두 기존대로 처리)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 11:00:00", tz_offset=-9)
async def test_t3_not_call_auction_no_regression(monkeypatch):
    from src.engine.session import session_tracker

    core = _core()
    pool = _make_pool(monkeypatch, ["005930", "035420"])
    _setup_ticks(monkeypatch, stale=["005930", "035420"])
    _patch_no_sleep(monkeypatch, core)
    _patch_no_feed_registry(monkeypatch)
    monkeypatch.setattr(
        session_tracker, "is_call_auction_now", lambda now=None: False, raising=False,
    )
    sched = _make_sched(positions=["005930"])

    await core.check_and_resubscribe_stale(sched)

    tickers_subscribed = {c.args[1] for c in pool.subscribe.await_args_list}
    assert tickers_subscribed == {"005930", "035420"}, (
        f"비-동시호가: HIGH+LOW 모두 재구독 (회귀 0). 실제: {tickers_subscribed!r}"
    )
