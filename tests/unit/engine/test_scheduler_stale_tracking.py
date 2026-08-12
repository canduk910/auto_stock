"""사이클 28 Red (2026-05-21) — `_stale_last_resubscribe_at` 추적 + cleanup.

배경:
- 2026-05-21 09:13 stale 16/30 진단에서 종목별 *마지막 강제 재구독 시각* 을 알 수 없어
  무한 skip 결함 의심에 대한 즉답 불가.
- 강제 재등록 시점 추적 dict `_stale_last_resubscribe_at: dict[str, datetime]` 신규.

검증 사양 (`_workspace/cycle28_stale_subscription_tracing_spec.md` §3.B + §5.2):

B2-1. `_stale_last_resubscribe_at` 인스턴스 필드 존재 (초기값 빈 dict)
B2-2. `_check_and_resubscribe_stale` 강제 재등록 직후 KST aware datetime 으로 갱신
B2-3. `_reset_daily_state()` 호출 시 `_stale_last_resubscribe_at` 도 clear (G5)
B2-4. 모든 종목 fresh 회복 시 `_stale_retry_count.clear()` 분기에서 동행 clear
B5.   `_resubscribe_stale_priority` 강제 재구독 시에도 같은 dict 갱신
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# B2-1 — 인스턴스 필드 존재
# ---------------------------------------------------------------------------
def test_stale_last_resubscribe_at_field_initialized():
    """`TradingScheduler.__init__` 가 `_stale_last_resubscribe_at` 빈 dict 로 초기화."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    assert hasattr(sched, "_stale_last_resubscribe_at"), (
        "TradingScheduler 에 `_stale_last_resubscribe_at` 필드 미정의"
    )
    assert sched._stale_last_resubscribe_at == {}


# ---------------------------------------------------------------------------
# B2-2 — _check_and_resubscribe_stale 강제 재등록 시 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_and_resubscribe_stale_updates_last_at(monkeypatch):
    """첫 stale 시 강제 재등록 직후 `_stale_last_resubscribe_at[ticker]` 가 KST datetime."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._running = True

    # scanner.ticker_last_tick: 60s 이상 오래된 timestamp
    import src.engine.scanner as scanner_mod
    old = datetime.now(KST) - timedelta(seconds=300)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {"005930": old})

    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: {"005930"}
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.get_subscriptions_by_session = MagicMock(return_value={"main": {"005930"}})
    pool_mock._main = MagicMock()
    pool_mock._main._subscriptions = {("H0STCNT0", "005930")}
    pool_mock._quotes = []
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    before = datetime.now(KST)
    await sched._check_and_resubscribe_stale()
    after = datetime.now(KST)

    ts = sched._stale_last_resubscribe_at.get("005930")
    assert ts is not None, "강제 재등록 직후 `_stale_last_resubscribe_at[ticker]` 미갱신"
    assert isinstance(ts, datetime)
    assert ts.tzinfo is not None, "KST tzinfo 없음 (CLAUDE.md 시각 데이터 KST 강제)"
    assert before <= ts <= after, "갱신 시각이 호출 시점 범위 밖"


# ---------------------------------------------------------------------------
# B2-3 — _reset_daily_state 정리 가드 (G5)
# ---------------------------------------------------------------------------
def test_reset_daily_state_clears_last_resubscribe_at(monkeypatch):
    """`_reset_daily_state()` 가 `_stale_last_resubscribe_at` 도 clear 한다."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    sched._stale_retry_count = {"005930": 3}
    sched._stale_last_resubscribe_at = {
        "005930": datetime.now(KST),
        "000660": datetime.now(KST),
    }

    sched._reset_daily_state()

    assert sched._stale_retry_count == {}
    assert sched._stale_last_resubscribe_at == {}, (
        "G5: _stale_retry_count cleanup 시 _stale_last_resubscribe_at 동행 삭제"
    )


# ---------------------------------------------------------------------------
# B2-4 — 모든 종목 fresh 회복 시 동행 clear
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_and_resubscribe_stale_all_fresh_clears_last_at(monkeypatch):
    """모든 종목 fresh 인 사이클 — `_stale_retry_count.clear()` 분기에서 동행 clear."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {"005930": 2}
    sched._stale_last_resubscribe_at = {
        "005930": datetime.now(KST) - timedelta(minutes=2),
    }
    sched._running = True

    import src.engine.scanner as scanner_mod
    fresh = datetime.now(KST) - timedelta(seconds=5)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {"005930": fresh})

    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: {"005930"}
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.get_subscriptions_by_session = MagicMock(return_value={"main": {"005930"}})
    pool_mock._main = MagicMock()
    pool_mock._main._subscriptions = {("H0STCNT0", "005930")}
    pool_mock._quotes = []
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count == {}
    assert sched._stale_last_resubscribe_at == {}, (
        "fresh 회복 분기에서 _stale_last_resubscribe_at 동행 clear 누락"
    )


# ---------------------------------------------------------------------------
# B5 — _resubscribe_stale_priority 도 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resubscribe_stale_priority_updates_last_at(monkeypatch):
    """`_resubscribe_stale_priority` 강제 재구독 시에도 `_stale_last_resubscribe_at` 갱신."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._pending_next_day_clear = set()
    sched._running = True

    # registry mock — high_tickers 집합 비움 (후보 LOW 경로)
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=[])

    # stale 종목 1개
    import src.engine.scanner as scanner_mod
    old = datetime.now(KST) - timedelta(seconds=120)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {"035720": old})

    pool_mock = MagicMock()
    pool_mock.subscribe = AsyncMock(return_value="quote-1")
    pool_mock.unsubscribe_in_pool = AsyncMock(return_value=None)
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    before = datetime.now(KST)
    resubscribed = await sched._resubscribe_stale_priority(cap=10)
    after = datetime.now(KST)

    assert "035720" in resubscribed
    ts = sched._stale_last_resubscribe_at.get("035720")
    assert ts is not None, (
        "_resubscribe_stale_priority 도 `_stale_last_resubscribe_at` 갱신 필수 (B5)"
    )
    assert before <= ts <= after
