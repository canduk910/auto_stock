"""사이클 29-R3 (2026-05-21) — K stale watcher 우선순위 분리 (메인 편중 해소).

배경 (사이클 28 실측 — 2026-05-21 13:21~13:29):
- 메인 25 vs 보조 합 9 — 편중률 73% (메인)
- [tick_coverage_session] main=25 quote-1=3 quote-2=4 quote-3=2

원인 진단 (Phase 1):
- 사이클 25-B 가 `_resubscribe_stale_priority` (5분 주기) 만 분리 완료
- **K stale watcher (`_check_and_resubscribe_stale`, 120s 주기)** 는 여전히 모든 stale
  종목을 `priority="HIGH", bypass_limit=True` 로 메인 강제 재등록
- 120s 주기가 5분 주기보다 빈번 → 후보 종목이 stale 될 때마다 메인 강제 누적
- 사이클 29 R1 force_retry 분기도 동일 결함 (line 2790)

본 사이클 (R3) 변경:
- `_check_and_resubscribe_stale` 양쪽 분기 (1~5회 + R1 force_retry) 에 우선순위 분리 적용
- positions / _pending_next_day_clear → HIGH+bypass_limit=True (메인 절대 보장)
- 그 외 후보 → LOW+bypass_limit=False (보조 라운드로빈 분산)
- 사이클 25-B `_resubscribe_stale_priority` 와 동일 패턴

매매 안전성 (domain-consult 자체 평가):
- 보유/익일청산 영향 0 (HIGH 분류 그대로)
- 후보 매수 신호 race 영향 0 (보조 세션도 동일 H0STCNT0 시세 수신)
- 메인 부하 감소 → silent inactive 발화 빈도 자연 감소 → 안전성 향상

회귀 가드:
- S-1: 1~5회 분기에서 보유 종목 stale → HIGH 유지
- S-2: 1~5회 분기에서 후보 종목 stale → LOW 분산
- S-3: 1~5회 분기에서 익일청산 종목 stale → HIGH 유지
- S-4: R1 force_retry 분기에서 보유 종목 stale → HIGH 유지
- S-5: R1 force_retry 분기에서 후보 종목 stale → LOW 분산
- S-6: positions + 후보 혼합 시나리오 — 각각 올바른 priority 분기
- S-7: bypass_limit 정합성 (HIGH → True, LOW → False)
- S-8: 보조 세션 0개 환경 호환 (LOW 도 메인 fallback)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _setup_env(monkeypatch, *, tickers: list[str], stale_age_secs: int = 300):
    """공통: kis_ws / kis_ws_pool / scanner.ticker_last_tick / write_log mock."""
    from src.engine import scheduler as sch_mod
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod

    subscribed_set = set(tickers)
    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: set(subscribed_set))
    )

    old = datetime.now(KST) - timedelta(seconds=stale_age_secs)
    last_tick = {t: old for t in tickers}
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", last_tick)

    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: list(subscribed_set)
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(level, msg, *a, **kw):
        return None

    monkeypatch.setattr(sch_mod, "write_log", _wl)

    return pool_mock


def _make_sched_with_positions(positions_tickers: list[str] = None,
                                next_day_clear: set[tuple[str, str]] = None):
    """positions / pending_next_day_clear 가 세팅된 minimal scheduler."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_registry import StrategyRegistry

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = next_day_clear or set()
    sched._running = True

    # 가짜 registry — positions 가 있는 전략 1개 시뮬레이션
    fake_strategy = MagicMock()
    fake_state = MagicMock()
    fake_state.positions = {t: MagicMock() for t in (positions_tickers or [])}
    fake_strategy.state = fake_state

    fake_registry = MagicMock()
    fake_registry.all = MagicMock(return_value=[fake_strategy])
    sched.registry = fake_registry
    return sched


# ===========================================================================
# S-1: 1~5회 분기에서 보유 종목 stale → HIGH 유지
# ===========================================================================
@pytest.mark.asyncio
async def test_held_ticker_stale_within_5_retries_uses_high(monkeypatch):
    """보유 종목이 r=1~5 stale → priority=HIGH + bypass_limit=True (메인 절대 보장)."""
    pool_mock = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched_with_positions(positions_tickers=["005935"])
    # r=1 (첫 stale)
    sched._stale_retry_count = {}

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "HIGH", (
        "보유 종목 (positions) 은 stale 시에도 HIGH 메인 강제 보장 — 손절·트레일링 race 차단"
    )
    assert kwargs.get("bypass_limit") is True, "HIGH 는 bypass_limit=True (한도 검사 skip)"


# ===========================================================================
# S-2: 1~5회 분기에서 후보 종목 stale → LOW 분산
# ===========================================================================
@pytest.mark.asyncio
async def test_candidate_ticker_stale_within_5_retries_uses_low(monkeypatch):
    """후보 종목 (positions/next_day_clear 미포함) stale → priority=LOW + bypass_limit=False (보조 분산)."""
    pool_mock = _setup_env(monkeypatch, tickers=["006340"])
    # positions / next_day_clear 모두 비어있음 — 후보 종목
    sched = _make_sched_with_positions(positions_tickers=[])

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "LOW", (
        "후보 종목은 stale 시 LOW 로 보조 세션 분산 — 메인 부하 분산 (사이클 25-B 패턴)"
    )
    assert kwargs.get("bypass_limit") is False, (
        "LOW 는 bypass_limit=False (한도 검사 적용, 보조 가득 시 메인 fallback)"
    )


# ===========================================================================
# S-3: 1~5회 분기에서 익일청산 종목 stale → HIGH 유지
# ===========================================================================
@pytest.mark.asyncio
async def test_next_day_clear_ticker_stale_uses_high(monkeypatch):
    """익일청산 보류 종목 (_pending_next_day_clear) stale → HIGH 유지."""
    pool_mock = _setup_env(monkeypatch, tickers=["232680"])
    sched = _make_sched_with_positions(
        positions_tickers=[],
        next_day_clear={("232680", "momentum")},
    )

    await sched._check_and_resubscribe_stale()

    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "HIGH", (
        "익일청산 보류 종목은 HIGH 유지 — 시가 race 차단"
    )
    assert kwargs.get("bypass_limit") is True


# ===========================================================================
# S-4: R1 force_retry 분기에서 보유 종목 stale → HIGH 유지
# ===========================================================================
@pytest.mark.asyncio
async def test_force_retry_held_ticker_uses_high(monkeypatch):
    """R1 force_retry (r>5 + cooldown 경과) — 보유 종목은 HIGH 유지."""
    pool_mock = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched_with_positions(positions_tickers=["005935"])
    sched._stale_retry_count = {"005935": 8}  # +1 → 9, r>5
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=400)  # cooldown 경과
    }

    await sched._check_and_resubscribe_stale()

    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "HIGH", (
        "R1 force_retry 분기에서도 보유 종목은 HIGH 유지"
    )
    assert kwargs.get("bypass_limit") is True


# ===========================================================================
# S-5: R1 force_retry 분기에서 후보 종목 stale → LOW 분산
# ===========================================================================
@pytest.mark.asyncio
async def test_force_retry_candidate_ticker_uses_low(monkeypatch):
    """R1 force_retry (r>5 + cooldown 경과) — 후보 종목은 LOW 분산."""
    pool_mock = _setup_env(monkeypatch, tickers=["006340"])
    sched = _make_sched_with_positions(positions_tickers=[])  # 후보 only
    sched._stale_retry_count = {"006340": 8}  # +1 → 9, r>5
    sched._stale_last_resubscribe_at = {
        "006340": datetime.now(KST) - timedelta(seconds=400)
    }

    await sched._check_and_resubscribe_stale()

    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "LOW", (
        "R1 force_retry 분기에서도 후보 종목은 LOW 보조 분산 — 사이클 29-R3 핵심"
    )
    assert kwargs.get("bypass_limit") is False


# ===========================================================================
# S-6: positions + 후보 혼합 시나리오
# ===========================================================================
@pytest.mark.asyncio
async def test_mixed_held_and_candidate_stale(monkeypatch):
    """보유 005935 (r=1 → HIGH) + 후보 006340 (r=1 → LOW) 혼합 시나리오."""
    pool_mock = _setup_env(monkeypatch, tickers=["005935", "006340"])
    sched = _make_sched_with_positions(positions_tickers=["005935"])

    await sched._check_and_resubscribe_stale()

    # 2회 호출 (정렬: 005935 → 006340)
    assert pool_mock.subscribe.await_count == 2
    calls = pool_mock.subscribe.await_args_list
    # call by ticker order
    by_ticker = {call.args[1]: call.kwargs for call in calls}

    assert by_ticker["005935"]["priority"] == "HIGH"
    assert by_ticker["005935"]["bypass_limit"] is True

    assert by_ticker["006340"]["priority"] == "LOW"
    assert by_ticker["006340"]["bypass_limit"] is False


# ===========================================================================
# S-7: positions + 후보 + R1 force_retry 동시 발화 시나리오
# ===========================================================================
@pytest.mark.asyncio
async def test_mixed_r5_and_force_retry_priorities(monkeypatch):
    """보유 005935 (r=6 + cooldown 경과 → R1 force_retry → HIGH) +
    후보 006340 (r=1 → 1~5 분기 → LOW) 혼합."""
    pool_mock = _setup_env(monkeypatch, tickers=["005935", "006340"])
    sched = _make_sched_with_positions(positions_tickers=["005935"])
    sched._stale_retry_count = {"005935": 5}  # +1 → 6, R1 분기
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=400)
    }

    await sched._check_and_resubscribe_stale()

    assert pool_mock.subscribe.await_count == 2
    by_ticker = {call.args[1]: call.kwargs for call in pool_mock.subscribe.await_args_list}

    # 보유 005935 — R1 force_retry 분기에서 HIGH
    assert by_ticker["005935"]["priority"] == "HIGH"
    # 후보 006340 — 1~5 분기에서 LOW
    assert by_ticker["006340"]["priority"] == "LOW"


# ===========================================================================
# S-8: 보조 세션 0개 환경 호환 — LOW 도 메인 fallback (분기 자체는 LOW 유지)
# ===========================================================================
@pytest.mark.asyncio
async def test_low_priority_works_when_no_quote_sessions(monkeypatch):
    """보조 세션 0개여도 LOW 분기 자체는 작동 — websocket_pool 이 메인 fallback 처리."""
    pool_mock = _setup_env(monkeypatch, tickers=["006340"])
    sched = _make_sched_with_positions(positions_tickers=[])

    await sched._check_and_resubscribe_stale()

    # 코드는 priority=LOW 로 호출 — 보조 0개 처리는 websocket_pool 책임
    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "LOW"
    # 호출 자체는 성공 (pool 이 fallback)
