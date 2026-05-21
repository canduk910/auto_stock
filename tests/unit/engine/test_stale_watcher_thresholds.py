"""사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영: K stale watcher 단순화.

배경:
- KIS 공식 답변 (2026-05-19): "기 요청된 목록을 관리하여 기등록한 사항을 재등록하지 않도록
  부탁드립니다. (당사 서버 부담 시 LMS + 앱정보 이용중지 처리)"
- 사이클 9 의 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기는 KIS 답변
  위반 → 무한 루프 위험.
- 사이클 17 보강: 1~5회 재SEND 분기 완전 폐기. 첫 stale 즉시 `pool.unsubscribe_in_pool`
  + `pool.subscribe(HIGH, bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴).
- retry > 5회는 skip (영구 stale 의심) — 다음 `_scan_loop` 위임.
- 5/12 silent inactive 사고 안전망 보존 (unsubscribe+subscribe 는 정상 신규 등록).

본 사이클(17 보강) 변경:
- ``STALE_WATCHER_INTERVAL_SECS`` 120 보존 (사이클 9)
- ``STALE_FORCE_REREGISTER_AFTER`` 5 보존 (회귀 가드 의미만, 분기 임계 아님)
- 신: ``MAX_STALE_RETRIES`` = 5 (6회 이상 skip)
- ``STALE_FRESHNESS_SECS`` 60 보존

회귀 가드 (의미 갱신 — 1~5회 즉시 강제 재등록):
- A: ``STALE_WATCHER_INTERVAL_SECS == 120`` 상수
- B: ``STALE_FORCE_REREGISTER_AFTER == 5`` 상수 (회귀 가드)
- B2: ``MAX_STALE_RETRIES == 5`` 신규 상수
- 신: ``STALE_FRESHNESS_SECS == 60``
- C: 첫 stale (retry=1) 즉시 ``unsubscribe_in_pool`` + ``subscribe(HIGH, bypass)`` 강제 재등록
- D: 5회 stale (retry=5) 도 동일하게 강제 재등록 (resend_subscribe_for_ticker 호출 0건)
- E: 6회 stale (retry=6) → skip (재등록 호출 0건)
- F: fresh 회복 시 ``_stale_retry_count`` 전체 reset
- G: 분당 강제 재등록 트래픽 < 250 (사이클 9 ~ 17 보강 보존)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 사양 A/B/B2 — 상수 회귀
# ---------------------------------------------------------------------------
def test_stale_watcher_interval_secs_is_120():
    """``STALE_WATCHER_INTERVAL_SECS`` 가 120 초로 완화됨 (사이클 9)."""
    from src.engine import scheduler

    assert scheduler.STALE_WATCHER_INTERVAL_SECS == 120, (
        "KIS 차단 회피: 30s → 120s (보조 세션 5개 × 40 종목 × 강제 재등록 "
        "트래픽 6배 → 1.5배 수준 회복)"
    )


def test_stale_force_reregister_after_is_5():
    """``STALE_FORCE_REREGISTER_AFTER`` 가 5 회 보존 (사이클 17 보강 회귀 가드).

    사이클 9: 3 → 10 (KIS 차단 회피)
    사이클 13: 10 → 5 (단발 silent inactive 회복 강화)
    사이클 17 보강: 분기 임계가 아닌 회귀 가드 의미만 보존 (실제 동작은 MAX_STALE_RETRIES).
    """
    from src.engine import scheduler

    assert scheduler.STALE_FORCE_REREGISTER_AFTER == 5, (
        "사이클 13: 10 → 5; 사이클 17 보강: 호환 보존 (회귀 가드 의미)"
    )


def test_max_stale_retries_is_5():
    """``MAX_STALE_RETRIES`` 가 5 회 (사이클 17 보강 신규 상수).

    6회 이상 stale 시 skip (영구 stale 의심) — 다음 `_scan_loop` 위임.
    KIS 답변 반영: 무한 재등록 방지.
    """
    from src.engine import scheduler

    assert scheduler.MAX_STALE_RETRIES == 5, (
        "사이클 17 보강: 6회 이상 stale → skip (KIS 답변 반영)"
    )


def test_stale_freshness_secs_preserved_at_60():
    """``STALE_FRESHNESS_SECS`` 는 60 초 그대로 — 5/12 운영 사고 대응 의도 보존."""
    from src.engine import scheduler

    assert scheduler.STALE_FRESHNESS_SECS == 60


# ---------------------------------------------------------------------------
# 사양 C/D/E — retry 누적 동작 + 즉시 강제 재등록 + skip 임계
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reregister_fires_on_first_stale(monkeypatch):
    """첫 stale (retry=1) 시 즉시 ``unsubscribe_in_pool`` + ``subscribe(HIGH)`` 호출.

    사이클 17 보강: KIS 답변 반영. 1~5회 재SEND 분기 폐기 → 첫 stale 즉시 강제 재등록
    (KIS 정상 "신규 등록" 패턴, 재SEND 0건).
    """
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}  # 첫 사이클
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
    pool_mock.get_subscribed_tickers = lambda: list(sch_mod.kis_ws.get_subscribed_tickers())
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

    assert sched._stale_retry_count["005930"] == 1
    # 첫 stale (retry=1) 즉시 강제 재등록 분기
    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # 사이클 29-R3 (2026-05-21) 의미 갱신: 005930 은 __new__ scheduler 라 positions/next_day_clear
    # 미포함 → 후보 종목 → LOW+bypass_limit=False (보조 분산). 보유 종목 HIGH 보장은
    # 신규 test_stale_watcher_priority_split.py 가 검증.
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "LOW"
    assert kwargs.get("bypass_limit") is False
    # resend_subscribe_for_ticker 미호출 (KIS 답변 반영: 재SEND 0건) — 사이클 17 보강 보존
    pool_mock.resend_subscribe_for_ticker.assert_not_called()


@pytest.mark.asyncio
async def test_force_reregister_continues_until_max_retries(monkeypatch):
    """retry 1~5 회 까지는 매 사이클 즉시 강제 재등록 호출됨 (재SEND 0건).

    사이클 17 보강: KIS 답변 반영. 1~5회 모두 unsubscribe+subscribe 강제 재등록 패턴.
    이 케이스는 retry = 5 (5번째 사이클) — MAX_STALE_RETRIES 직전.
    사이클 29-R3 (2026-05-21): priority 분기 의미 갱신 — 후보 종목 LOW 분산.
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
    pool_mock.get_subscribed_tickers = lambda: list(sch_mod.kis_ws.get_subscribed_tickers())
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
    # 5회 stale 도 동일하게 강제 재등록 (사이클 17 보강)
    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # 사이클 29-R3: 후보 종목 LOW 분산
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "LOW"
    assert kwargs.get("bypass_limit") is False
    # 재SEND 0건 보장 (KIS 답변 반영)
    pool_mock.resend_subscribe_for_ticker.assert_not_called()


@pytest.mark.asyncio
async def test_skip_after_max_stale_retries(monkeypatch):
    """retry > 5 회 (= 6회째) stale + cooldown 미경과 시 skip — 재등록 호출 0건.

    사이클 17 보강: 영구 stale 의심 종목 보호.
    사이클 29 (2026-05-21) — 의미 갱신: r>5 분기는 시간 기반 (5분 cooldown).
    본 케이스는 last_resub_age < 300s 시나리오로 기존 skip 동작 보존 검증.
    """
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {"005930": 5}  # 5 +1 = 6 (> MAX_STALE_RETRIES)
    # 사이클 29: cooldown 미경과 (100s < 300s) → skip 보존
    sched._stale_last_resubscribe_at = {"005930": datetime.now(KST) - timedelta(seconds=100)}
    sched._stale_force_retry_history = {}
    sched._running = True

    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: {"005930"})
    )
    old = datetime.now(KST) - timedelta(seconds=300)
    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {"005930": old})

    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: list(sch_mod.kis_ws.get_subscribed_tickers())
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.resend_subscribe_for_ticker = AsyncMock()
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count["005930"] == 6
    # 6회 stale + cooldown 미경과 → skip (재등록 0건)
    pool_mock.unsubscribe_in_pool.assert_not_called()
    pool_mock.subscribe.assert_not_called()
    pool_mock.resend_subscribe_for_ticker.assert_not_called()


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
    pool_mock.get_subscribed_tickers = lambda: list(sch_mod.kis_ws.get_subscribed_tickers())
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
# 사양 G — 트래픽 산정 (사이클 9 ~ 17 보강 보존)
# ---------------------------------------------------------------------------
def test_max_force_reregister_traffic_per_minute_well_below_kis_limit():
    """보조 5개 × 40 종목 분당 강제 재등록 트래픽 계산 — KIS 차단 회피 가드.

    사이클 8 까지: 30s 주기 × 강제 임계 3회 → 분당 최대 800 요청.
    사이클 9: 120s 주기 × 강제 임계 10회 → 분당 최대 200 요청 미만.
    사이클 13: 120s 주기 × 강제 임계 5회 → 분당 최대 200 요청 보존.
    사이클 17 보강: 120s 주기, 매 사이클 즉시 강제 재등록 (1~5회 분기 폐기). 같은 산술
    상한 200 보존 — KIS 답변 반영의 핵심은 *재SEND 0건* 이지 트래픽 자체는 동일.

    수식: (sessions × tickers × 2) / (interval_secs / 60)
         = 보조 5 × 40 × (unsubscribe + subscribe = 2) / (120/60)
         = 400 / 2
         = 200 (강제 재등록이 *매* 사이클 발생하는 최악 시나리오)

    임계 분기 후 실제 운영 트래픽: 한 종목당 6회 강제 재등록 후 skip → 실현 트래픽
    유한. KIS 답변 핵심은 *재SEND 0건* 보장 → 본 테스트는 트래픽 상한만 검증.
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
