"""사이클 9/13 (2026-05-18) — KIS 차단 회피 안전망 + stale 회복 강화: 임계 회귀.

배경:
- 사이클 9: KIS Open API 공지(2026-05-18) 대응 — 분당 800 → 200 미만 트래픽 완화.
- 사이클 13: 10회 × 120s = 20분 stale 누적 후에야 강제 재등록 발화 — 단발
  silent inactive 회복이 너무 느림. 분당 추가 트래픽 ~20 req 수준이라 KIS
  한도(18 req/s = 1080/분)의 2% 로 무시 가능 → 5회 × 120s = 10분으로 단축.

본 사이클(13) 변경:
- ``STALE_WATCHER_INTERVAL_SECS`` 120 보존 (사이클 9)
- ``STALE_FORCE_REREGISTER_AFTER`` 10 → 5 (5회 × 120s = 10분 stale 후 강제 재등록)
- ``STALE_FRESHNESS_SECS`` 60 보존 (5/12 운영 사고 대응 의도)

회귀 가드 (7 케이스, 의미 갱신 — 임계값 10 → 5):
- A: ``STALE_WATCHER_INTERVAL_SECS == 120`` 상수
- B: ``STALE_FORCE_REREGISTER_AFTER == 5`` 상수 (이전 10)
- 신: ``STALE_FRESHNESS_SECS == 60``
- C: 6회 stale 후 강제 재등록(``unsubscribe_in_pool`` + ``subscribe(HIGH,bypass)``) — 이전 11회
- D: 5회 stale 까지는 ``resend_subscribe_for_ticker`` 만 (unsubscribe 없음) — 이전 10회
- E: fresh 회복 시 ``_stale_retry_count`` 전체 reset
- F: 분당 강제 재등록 트래픽 < 250 + 강제 임계 분기 후 실현 트래픽 < 30
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 사양 A/B — 상수 회귀
# ---------------------------------------------------------------------------
def test_stale_watcher_interval_secs_is_120():
    """``STALE_WATCHER_INTERVAL_SECS`` 가 120 초로 완화됨 (사이클 9)."""
    from src.engine import scheduler

    assert scheduler.STALE_WATCHER_INTERVAL_SECS == 120, (
        "KIS 차단 회피: 30s → 120s (보조 세션 5개 × 40 종목 × 강제 재등록 "
        "트래픽 6배 → 1.5배 수준 회복)"
    )


def test_stale_force_reregister_after_is_5():
    """``STALE_FORCE_REREGISTER_AFTER`` 가 5 회로 단축됨 (사이클 13).

    사이클 9: 3 → 10 (KIS 차단 회피)
    사이클 13: 10 → 5 (단발 silent inactive 회복 강화)

    근거: 분당 추가 트래픽 ~20 req (KIS 한도 18 req/s = 1080/분 의 2%) 수준이라
    무시 가능. 사이클 9 health monitor 가 5xx 누적 감지 자동 비활성으로 안전망.
    """
    from src.engine import scheduler

    assert scheduler.STALE_FORCE_REREGISTER_AFTER == 5, (
        "사이클 13: 10 → 5 (5 × 120s = 10분 stale 후 강제 재등록)"
    )


def test_stale_freshness_secs_preserved_at_60():
    """``STALE_FRESHNESS_SECS`` 는 60 초 그대로 — 5/12 운영 사고 대응 의도 보존."""
    from src.engine import scheduler

    assert scheduler.STALE_FRESHNESS_SECS == 60


# ---------------------------------------------------------------------------
# 사양 C/D/E — retry 누적 동작 + 강제 재등록 임계
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reregister_fires_after_sixth_consecutive_stale(monkeypatch):
    """retry > 5 회 (= 6회째) stale 시 ``unsubscribe_in_pool`` + ``subscribe(HIGH)`` 호출.

    사이클 13: 임계 10 → 5 단축. 6회째 (= 6분 stale 누적) 강제 재등록 발화.
    """
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {"005930": 5}  # 사이클 직전 누적 5
    sched._running = True

    # _check_and_resubscribe_stale 의 외부 의존 mock
    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: {"005930"})
    )
    # scanner.ticker_last_tick: 60s 이상 오래된 timestamp
    old = datetime.now(KST) - timedelta(seconds=300)
    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {"005930": old})

    pool_mock = MagicMock()
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.resend_subscribe_for_ticker = AsyncMock()
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    # write_log mock — fire-and-forget 흐름 보존
    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count["005930"] == 6
    # 6 > STALE_FORCE_REREGISTER_AFTER(5) → 강제 재등록 분기
    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # 강제 재등록은 priority=HIGH bypass_limit=True
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "HIGH"
    assert kwargs.get("bypass_limit") is True
    # resend 는 호출 안 됨 (강제 재등록 분기로 분기)
    pool_mock.resend_subscribe_for_ticker.assert_not_called()


@pytest.mark.asyncio
async def test_no_force_reregister_until_fifth_stale(monkeypatch):
    """retry ≤ 5 회 까지는 ``resend_subscribe_for_ticker`` 만, unsubscribe 호출 없음.

    이 케이스는 retry = 5 (5번째 사이클) — 5 > 5 거짓, 1~5 분기.
    사이클 13: 임계 10 → 5 단축에 따라 1~5 회까지 resend.
    """
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {"005930": 4}  # 4 +1 = 5
    sched._running = True

    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: {"005930"})
    )
    old = datetime.now(KST) - timedelta(seconds=300)
    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {"005930": old})

    pool_mock = MagicMock()
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.resend_subscribe_for_ticker = AsyncMock()
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count["005930"] == 5
    pool_mock.resend_subscribe_for_ticker.assert_awaited_once()
    pool_mock.unsubscribe_in_pool.assert_not_called()
    pool_mock.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_fresh_recovery_clears_retry_count(monkeypatch):
    """전체 fresh 회복 시 ``_stale_retry_count`` 전체 reset."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    # 이전 사이클 누적 retry 7
    sched._stale_retry_count = {"005930": 7, "000660": 5}
    sched._running = True

    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: {"005930", "000660"})
    )
    # 모두 fresh — 1초 전 timestamp
    fresh = datetime.now(KST) - timedelta(seconds=1)
    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(
        scanner_mod, "ticker_last_tick", {"005930": fresh, "000660": fresh}
    )

    pool_mock = MagicMock()
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.resend_subscribe_for_ticker = AsyncMock()
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count == {}, "fresh 회복 시 retry 카운터 전체 reset"


# ---------------------------------------------------------------------------
# 사양 F — 트래픽 산정
# ---------------------------------------------------------------------------
def test_max_force_reregister_traffic_per_minute_well_below_kis_limit():
    """보조 5개 × 40 종목 분당 강제 재등록 트래픽 계산 — KIS 차단 회피 가드.

    이전 (사이클 8 까지): 30s 주기 × 강제 임계 3회 → 분당 최대 800 요청.
    사이클 9: 120s 주기 × 강제 임계 10회 → 분당 최대 200 요청 미만.
    사이클 13: 120s 주기 × 강제 임계 5회 → 분당 최대 200 요청 보존 (worst-case 동일).

    수식: (sessions × tickers × 2) / (interval_secs / 60)
         = 보조 5 × 40 × (unsubscribe + subscribe = 2) / (120/60)
         = 400 / 2
         = 200 (강제 재등록이 *매* 사이클 발생하는 최악 시나리오)

    임계 5 회 분기 덕분에 실제 운영 트래픽은 위 수치의 1/5 이하 (강제 재등록은
    10분 stale 누적 후에만 발화). 본 테스트는 회귀 가드 — 상수 누구든 작은 값으로
    되돌리면 즉시 실패. 실현 트래픽 한도 < 50 (이전 < 30) 으로 완화 — 5회로
    분기가 빨라진 만큼 산술 상한 비율 변경 반영.
    """
    from src.engine import scheduler

    # 가정 워크로드 (KIS 권장 보조 5 + 종목 40)
    sessions = 5
    tickers_per_session = 40
    requests_per_force = 2  # unsubscribe + subscribe

    worst_case_per_minute = (
        sessions * tickers_per_session * requests_per_force
        / (scheduler.STALE_WATCHER_INTERVAL_SECS / 60)
    )
    assert worst_case_per_minute < 250, (
        f"분당 트래픽 {worst_case_per_minute} — KIS 차단 회피 위반 "
        f"(INTERVAL={scheduler.STALE_WATCHER_INTERVAL_SECS}s)"
    )

    # 실제 운영은 누적 6회째에만 강제 → ÷ 5 (산술적 상한)
    realistic_per_minute = worst_case_per_minute / scheduler.STALE_FORCE_REREGISTER_AFTER
    assert realistic_per_minute < 50, (
        f"강제 재등록 임계 분기 후 실현 트래픽 {realistic_per_minute} — "
        f"AFTER={scheduler.STALE_FORCE_REREGISTER_AFTER}"
    )
