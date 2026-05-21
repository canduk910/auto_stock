"""사이클 17 보강 (2026-05-19) Red — K stale watcher 의 풀 통합 + KIS 답변 반영.

`_check_and_resubscribe_stale` 가 단일 세션 직접 호출 대신 풀 인터페이스 사용.

사이클 7-C: 풀의 `_ticker_to_session` 활용해 정확한 세션 분배.
사이클 13-E (2026-05-18): 진입점 `get_subscribed_tickers` 도 풀 전체로 갱신 —
메인 비어있어도 보조 종목 stale 처리되도록.
사이클 17 보강 (2026-05-19): KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영.
1~5회 `pool.resend_subscribe_for_ticker` 분기 폐기. 첫 stale 즉시 `pool.unsubscribe_in_pool`
+ `pool.subscribe(priority='HIGH', bypass_limit=True)` 강제 재등록. 6회 이상 skip.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def reset_stale_state():
    """매 테스트 시작 시 scanner.ticker_last_tick 초기화."""
    from src.engine import scanner

    saved = dict(scanner.ticker_last_tick)
    scanner.ticker_last_tick.clear()
    yield
    scanner.ticker_last_tick.clear()
    scanner.ticker_last_tick.update(saved)


# ---------------------------------------------------------------------------
# D-1. 첫 stale 즉시 강제 재등록 (KIS 답변 반영, 재SEND 0건)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_calls_pool_resend(monkeypatch, reset_stale_state):
    """사이클 17 보강: 첫 stale 즉시 unsubscribe_in_pool + subscribe(HIGH) 호출.

    재SEND (`pool.resend_subscribe_for_ticker`) 호출 0건 — KIS 답변 반영.
    """
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod

    # subscribed 1개, stale 상태
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: ["005930"], raising=False,
    )
    # 60초 이전 마지막 tick → stale
    from src.engine.scanner import KST_TZ
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    # 강제 재등록 spy
    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )
    # 재SEND 미호출 보증 spy
    pool_resend_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "resend_subscribe_for_ticker", pool_resend_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    await sched._check_and_resubscribe_stale()

    # 사이클 17 보강 정책: 첫 stale 즉시 강제 재등록 (재SEND 0건)
    assert pool_unsub_spy.await_count >= 1, (
        f"첫 stale 즉시 unsubscribe_in_pool 호출 필요, 실제={pool_unsub_spy.await_count}"
    )
    assert pool_sub_spy.await_count >= 1, (
        f"첫 stale 즉시 subscribe(HIGH) 호출 필요, 실제={pool_sub_spy.await_count}"
    )
    assert pool_resend_spy.await_count == 0, (
        f"재SEND 0건 (KIS 답변 반영), 실제={pool_resend_spy.await_count}"
    )


# ---------------------------------------------------------------------------
# D-2. 강제 재등록은 priority=HIGH, bypass_limit=True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_uses_ticker_to_session_routing(monkeypatch, reset_stale_state):
    """사이클 17 보강: pool.subscribe 호출 시 priority=HIGH, bypass_limit=True 보장.

    분배 추적 dict(`_ticker_to_session`) 정합성 유지는 `pool.unsubscribe_in_pool`
    + `pool.subscribe` 가 모두 책임 — 라운드로빈 재선택 가능.
    """
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: ["005930"], raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    await sched._check_and_resubscribe_stale()

    # 강제 재등록 호출 확인 (재SEND 0건은 사이클 17 보강 보존)
    assert pool_unsub_spy.await_count >= 1
    assert pool_sub_spy.await_count >= 1
    # 사이클 29-R3 (2026-05-21) 의미 갱신:
    # 005930 은 positions/next_day_clear 미포함 (후보 종목) → LOW + bypass_limit=False
    # (보조 세션 분산 — 메인 편중 73% 해소). 보유 종목 시나리오는 신규 priority_split 테스트 참조.
    kwargs = pool_sub_spy.await_args.kwargs
    assert kwargs.get("priority") == "LOW", (
        f"후보 종목 stale 재등록은 LOW 보조 분산, 실제 kwargs={kwargs}"
    )
    assert kwargs.get("bypass_limit") is False, (
        f"LOW 는 bypass_limit=False (보조 가득 시 메인 fallback), 실제 kwargs={kwargs}"
    )


# ---------------------------------------------------------------------------
# D-3. 5회 retry 시에도 매 사이클 강제 재등록 (1~5회 동일 분기)
# 사이클 17 보강 (2026-05-19): KIS 답변 반영 — 1~5회 모두 즉시 강제 재등록
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_force_reregister_via_pool(monkeypatch, reset_stale_state):
    """5회 누적 stale (retry 4 → 5) 에도 강제 재등록 호출.

    사이클 17 보강: 1~5회 모두 같은 분기. retry=5 도 unsubscribe+subscribe 호출.
    재SEND 0건 보장.
    """
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: ["005930"], raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    pool_resend_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "resend_subscribe_for_ticker", pool_resend_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    # retry 4 → 5 (MAX_STALE_RETRIES=5, 5 이하면 강제 재등록)
    sched._stale_retry_count["005930"] = 4
    await sched._check_and_resubscribe_stale()

    assert pool_unsub_spy.await_count >= 1
    assert pool_sub_spy.await_count >= 1
    # 재SEND 0건 (KIS 답변 반영)
    assert pool_resend_spy.await_count == 0


# ---------------------------------------------------------------------------
# D-4. retry > MAX_STALE_RETRIES → skip
# 사이클 17 보강 (2026-05-19): 6회 이상 stale 시 skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_skips_when_retry_exceeds_6(monkeypatch, reset_stale_state):
    """retry > MAX_STALE_RETRIES (=5) 시 skip — 모든 풀 호출 0.

    사이클 17 보강: 6회 이상 stale (영구 stale 의심) → skip + 다음 _scan_loop 위임.
    """
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.realtime import websocket_pool as wp_mod
    from src.engine.scanner import KST_TZ

    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: ["005930"], raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    pool_resend_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "resend_subscribe_for_ticker", pool_resend_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    sched._stale_retry_count["005930"] = 6  # >5 — skip
    # 사이클 29 (2026-05-21): r>5 분기는 시간 기반 — cooldown 미경과 시 기존 skip 동작 보존
    # last_resub_age=100s (< STALE_FORCE_RETRY_AFTER_SECS=300s) → skip 보존
    sched._stale_last_resubscribe_at["005930"] = datetime.now(KST_TZ) - timedelta(seconds=100)
    await sched._check_and_resubscribe_stale()

    # 모든 풀 호출이 0 (cooldown 미경과로 skip)
    assert pool_unsub_spy.await_count == 0
    assert pool_sub_spy.await_count == 0
    assert pool_resend_spy.await_count == 0


# ---------------------------------------------------------------------------
# D-5. 전체 fresh — _stale_retry_count.clear()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_clears_retry_when_all_fresh(monkeypatch, reset_stale_state):
    """전체 fresh 일 때 누적 retry 카운터 자동 리셋."""
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.engine.scanner import KST_TZ
    from src.realtime import websocket_pool as wp_mod

    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: ["005930", "000660"], raising=False,
    )
    # 모두 fresh (방금 tick)
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ)
    scanner.ticker_last_tick["000660"] = datetime.now(KST_TZ)

    sched = sched_mod.TradingScheduler()
    sched._stale_retry_count = {"005930": 2, "000660": 1}

    await sched._check_and_resubscribe_stale()

    assert sched._stale_retry_count == {}, (
        f"전체 fresh 시 retry 카운터 clear, 실제={sched._stale_retry_count}"
    )


# ---------------------------------------------------------------------------
# D-6 (사이클 13-E, 2026-05-18) — 메인 비어있어도 풀 종목 stale 처리
# 사이클 17 보강 (2026-05-19): 첫 stale 즉시 강제 재등록 정책 반영
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_watcher_processes_quote_session_when_main_empty(monkeypatch, reset_stale_state):
    """진입점이 풀(`kis_ws_pool.get_subscribed_tickers`) 사용 — 메인 비어있어도
    보조 세션 stale 종목 처리. 사이클 7-C 풀 통합 시 진입점 갱신 누락 결함 회귀 가드.

    운영 상황(2026-05-18 14:00): 메인 0, 보조 quote-1 26 종목, stale 18.
    fix 전: `kis_ws.get_subscribed_tickers()` 가 메인 만 반환 → empty → 즉시 return.
    fix 후: `kis_ws_pool.get_subscribed_tickers()` 풀 전체 반환 → stale 처리 진입.

    사이클 17 보강: 첫 stale 즉시 강제 재등록 (재SEND 0건). 정책 변경 후에도
    "메인 empty 시 보조 종목 처리됨" 가드는 보존.
    """
    from src.engine import scheduler as sched_mod
    from src.engine import scanner
    from src.engine.scanner import KST_TZ
    from src.realtime import websocket_pool as wp_mod

    # 메인 직접 호출은 empty 반환 (현 운영 상황 재현)
    monkeypatch.setattr(
        sched_mod.kis_ws, "get_subscribed_tickers",
        lambda: set(), raising=False,
    )
    # 풀은 보조 세션 종목 반환
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: ["005930"], raising=False,
    )
    scanner.ticker_last_tick["005930"] = datetime.now(KST_TZ) - timedelta(seconds=120)

    pool_unsub_spy = AsyncMock()
    pool_sub_spy = AsyncMock()
    pool_resend_spy = AsyncMock()
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "unsubscribe_in_pool", pool_unsub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "subscribe", pool_sub_spy, raising=False,
    )
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "resend_subscribe_for_ticker", pool_resend_spy, raising=False,
    )

    sched = sched_mod.TradingScheduler()
    await sched._check_and_resubscribe_stale()

    # 메인 비어있어도 보조 종목 stale 처리됨 — 강제 재등록 1회 호출 보장 (재SEND 0건)
    assert pool_unsub_spy.await_count >= 1, (
        f"메인 비어있어도 풀 종목 stale 처리되어야 함, 실제={pool_unsub_spy.await_count}"
    )
    assert pool_sub_spy.await_count >= 1, (
        f"메인 비어있어도 풀 종목 stale 처리되어야 함, 실제={pool_sub_spy.await_count}"
    )
    assert pool_resend_spy.await_count == 0, (
        f"재SEND 0건 (KIS 답변 반영), 실제={pool_resend_spy.await_count}"
    )
