"""사이클 28 Red (2026-05-21) — `_report_tick_coverage` 세션별 분포 추가.

배경 (`_workspace/cycle28_stale_subscription_tracing_spec.md` §4.2):
- 기존 `[tick_coverage] subscribed=N fresh=F stale=S ratio=...` 1행 *완전 동일* 보존 (G1)
- 신규 `[tick_coverage_session]` 세션별 분포 1행 추가 (파이프 구분, stale=0 세션도 포함)

검증 사양:
B4-1. 기존 `[tick_coverage]` 1행 보존
B4-2. 신규 `[tick_coverage_session]` 1행 추가
B4-3. 세션 0개 (subscribed=0) → detail 행 생략
B4-4. 메인 + 보조 2개 세션 → 파이프(`|`) 구분으로 모두 1행
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _setup_pool_mock(monkeypatch, *, subscribed: set[str], session_groups: dict[str, set[str]]):
    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: set(subscribed)
    pool_mock.get_subscriptions_by_session = MagicMock(return_value=session_groups)
    main_mock = MagicMock(name="main-session")
    main_mock._subscriptions = {("H0STCNT0", t) for t in session_groups.get("main", set())}
    pool_mock._main = main_mock
    quote_mocks = []
    for label, tickers in session_groups.items():
        if label in ("main", "unknown"):
            continue
        q = MagicMock(name=label)
        q._subscriptions = {("H0STCNT0", t) for t in tickers}
        quote_mocks.append(q)
    pool_mock._quotes = quote_mocks
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)
    return pool_mock


@pytest.mark.asyncio
async def test_tick_coverage_emits_legacy_and_session_lines(monkeypatch, caplog):
    """단일 메인 + 5종목 (3 fresh + 2 stale)."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    import src.engine.scanner as scanner_mod
    now = datetime.now(KST)
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {
            "F1": now - timedelta(seconds=5),
            "F2": now - timedelta(seconds=10),
            "F3": now - timedelta(seconds=20),
            "S1": now - timedelta(seconds=300),
            "S2": now - timedelta(seconds=400),
        },
    )

    _setup_pool_mock(
        monkeypatch,
        subscribed={"F1", "F2", "F3", "S1", "S2"},
        session_groups={"main": {"F1", "F2", "F3", "S1", "S2"}},
    )

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    await sched._report_tick_coverage()

    legacy = [r.message for r in caplog.records if r.message.startswith("[tick_coverage] ")]
    sess = [r.message for r in caplog.records if r.message.startswith("[tick_coverage_session] ")]

    # B4-1: 기존 1행 보존
    assert len(legacy) == 1, f"기존 [tick_coverage] 1행 보존 실패: {legacy}"
    assert "subscribed=5" in legacy[0]
    assert "fresh=3" in legacy[0]
    assert "stale=2" in legacy[0]

    # B4-2: 신규 1행
    assert len(sess) == 1, f"[tick_coverage_session] 1행 추가 필수: {sess}"
    line = sess[0]
    assert "main sub=5/41 fresh=3 stale=2" in line, f"세션 분포 포맷 불일치: {line}"


@pytest.mark.asyncio
async def test_tick_coverage_session_skipped_when_subscribed_zero(monkeypatch, caplog):
    """subscribed=0 케이스 — 기존 행만, session detail 행 생략 (B4-3)."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {})

    _setup_pool_mock(monkeypatch, subscribed=set(), session_groups={})

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    await sched._report_tick_coverage()

    sess = [r.message for r in caplog.records if r.message.startswith("[tick_coverage_session] ")]
    assert sess == [], f"subscribed=0 인 경우 session detail 행 출력 안 함: {sess}"


@pytest.mark.asyncio
async def test_tick_coverage_session_includes_all_sessions_with_pipe(monkeypatch, caplog):
    """메인 + 보조 2개 → 파이프 구분으로 모두 1행 (B4-4)."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    import src.engine.scanner as scanner_mod
    now = datetime.now(KST)
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {
            "M1": now - timedelta(seconds=5),
            "M2": now - timedelta(seconds=300),
            "Q1": now - timedelta(seconds=10),
            "Q2": now - timedelta(seconds=20),
        },
    )

    _setup_pool_mock(
        monkeypatch,
        subscribed={"M1", "M2", "Q1", "Q2"},
        session_groups={"main": {"M1", "M2"}, "quote-1": {"Q1", "Q2"}},
    )

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    await sched._report_tick_coverage()

    sess = [r.message for r in caplog.records if r.message.startswith("[tick_coverage_session] ")]
    assert len(sess) == 1
    line = sess[0]
    # 두 세션 모두 1행 안에 (stale=0 세션도 포함, B4-4)
    assert "main sub=2/41" in line
    assert "quote-1 sub=2/41" in line
    assert "|" in line  # 파이프 구분
