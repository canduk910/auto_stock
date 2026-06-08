"""사이클 28 Red (2026-05-21) — `_check_and_resubscribe_stale` 로그 포맷 강화.

배경 (`_workspace/cycle28_stale_subscription_tracing_spec.md` §4.1):
- 기존 `[stale_watcher]` 1행은 *바이트 단위 동일* 보존 (G1 외부 모니터링 grep 호환)
- 신규 `[stale_watcher_detail]` 별도 행 추가 (세션별 분포 + 종목 cap 20)

검증 사양:
B3-1. 기존 `[stale_watcher] subscribed=N stale=M force_reregistered=K skipped=S` 정확히 1회 출력
B3-2. 신규 `[stale_watcher_detail] session=... sub=N/41 fresh=F stale=S ratio=...` 1행 출력
B3-3. stale 종목 리스트가 `(ticker,r=retries,@HH:MM:SS)` 포맷
B3-4. stale_count==0 인 세션은 detail 행 생략 (로그 폭주 차단)
B3-5. stale 종목 20개 초과 시 cap 적용 + `...+N` 표시
B3-6. last_resub 미존재 종목은 `@-` 표시
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _setup_pool_mock(monkeypatch, *, subscribed: set[str], session_groups: dict[str, set[str]]):
    """공통 풀 mock — get_subscribed_tickers + get_subscriptions_by_session."""
    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: set(subscribed)
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.get_subscriptions_by_session = MagicMock(return_value=session_groups)
    # 세션 객체 모킹 — `_subscriptions` 길이 기반 capacity 계산 위해
    main_mock = MagicMock(name="main-session")
    main_mock._subscriptions = {("H0STCNT0", t) for t in session_groups.get("main", set())}
    pool_mock._main = main_mock
    quote_mocks = []
    for label, tickers in session_groups.items():
        if label == "main" or label == "unknown":
            continue
        q = MagicMock(name=label)
        q._subscriptions = {("H0STCNT0", t) for t in tickers}
        quote_mocks.append(q)
    pool_mock._quotes = quote_mocks
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)
    return pool_mock


@pytest.mark.asyncio
async def test_stale_watcher_emits_legacy_and_detail_lines(monkeypatch, caplog):
    """단일 메인 세션 + 5종목 (3 fresh + 2 stale) — 기존 1행 + detail 1행."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {"A": 1, "B": 2}  # 사전 누적
    # 사전 last_resub 는 의도적으로 비움 — 강제 재등록 직후 _check_and_resubscribe_stale 가
    # 현재 시각으로 갱신하므로 사전 값은 덮어쓰여 의미 없음. detail 행은 *현재* 시각 포맷
    # `@HH:MM:SS` 만 포함되는지 확인.
    sched._stale_last_resubscribe_at = {}
    sched._running = True

    # _setup_pool_mock 보다 ticker_last_tick 을 *호출 시점에 임박* 한 시각으로 설정해
    # 픽스처 시각과 detail 행 시각의 분 단위 일치 검증.
    setup_now = datetime.now(KST)
    expected_hhmm = setup_now.strftime("%H:%M")

    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {
            "F1": setup_now - timedelta(seconds=5),
            "F2": setup_now - timedelta(seconds=10),
            "F3": setup_now - timedelta(seconds=20),
            "A": setup_now - timedelta(seconds=300),
            "B": setup_now - timedelta(seconds=400),
        },
    )

    _setup_pool_mock(
        monkeypatch,
        subscribed={"F1", "F2", "F3", "A", "B"},
        session_groups={"main": {"F1", "F2", "F3", "A", "B"}},
    )

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    await sched._check_and_resubscribe_stale()

    msgs = [r.message for r in caplog.records]
    # 사이클 74 옵션 C 조건부: [stale_watcher] 직접 INFO → collector 흡수
    # B3-1: 사이클 74 이후 직접 emit 0건 (aggregation 흡수)
    legacy = [m for m in msgs if m.startswith("[stale_watcher] subscribed=")]
    assert len(legacy) == 0, (
        f"사이클 74 옵션 C: [stale_watcher] 직접 INFO 0건 의무 — actual={len(legacy)}: {legacy}"
    )
    detail = [m for m in msgs if m.startswith("[stale_watcher_detail] ")]

    # B3-2: detail 1행
    assert len(detail) == 1, f"[stale_watcher_detail] 1행 필요 — main 세션 stale>0: {detail}"
    line = detail[0]
    assert "session=main" in line
    assert "sub=5/41" in line  # MAX_SUBSCRIPTIONS=41
    assert "fresh=3" in line
    assert "stale=2" in line
    assert "ratio=" in line

    # B3-3: 종목 포맷 (A=retry=2 갱신 후, B=retry=3 갱신 후 — _check_and_resubscribe_stale 이 +1 함)
    assert "A,r=2," in line, f"A 종목 포맷: {line}"
    assert "B,r=3," in line, f"B 종목 포맷: {line}"
    # 강제 재등록 직후 갱신된 시각 — `@HH:MM` (분 단위) 매칭
    assert f"@{expected_hhmm}" in line, f"last_resub HH:MM 형식 미포함: {line}"


@pytest.mark.asyncio
async def test_stale_watcher_detail_skips_session_with_zero_stale(monkeypatch, caplog):
    """stale_count==0 인 세션은 detail 행 생략 (B3-4 로그 폭주 차단)."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._running = True

    import src.engine.scanner as scanner_mod
    now = datetime.now(KST)
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {
            "F1": now - timedelta(seconds=5),
            "F2": now - timedelta(seconds=5),
            "A": now - timedelta(seconds=300),
        },
    )

    # main 에 F1+A, quote-1 에 F2 만 → quote-1 stale=0
    _setup_pool_mock(
        monkeypatch,
        subscribed={"F1", "F2", "A"},
        session_groups={"main": {"F1", "A"}, "quote-1": {"F2"}},
    )

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    await sched._check_and_resubscribe_stale()

    detail_lines = [
        r.message for r in caplog.records if r.message.startswith("[stale_watcher_detail] ")
    ]
    # main 세션 1행, quote-1 세션 0행
    assert len(detail_lines) == 1, (
        f"stale_count>0 인 세션만 detail 행 출력 (quote-1 skip): {detail_lines}"
    )
    assert "session=main" in detail_lines[0]
    assert "session=quote-1" not in detail_lines[0]


@pytest.mark.asyncio
async def test_stale_watcher_detail_caps_at_20_tickers(monkeypatch, caplog):
    """stale 종목 20개 초과 시 cap + `...+N` 표시 (B3-5)."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    # 25개 종목을 stale, retry=1 로 시작
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._running = True

    tickers = [f"T{i:02d}" for i in range(25)]

    import src.engine.scanner as scanner_mod
    now = datetime.now(KST)
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {t: now - timedelta(seconds=300) for t in tickers},
    )

    _setup_pool_mock(
        monkeypatch,
        subscribed=set(tickers),
        session_groups={"main": set(tickers)},
    )

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    await sched._check_and_resubscribe_stale()

    detail_lines = [
        r.message for r in caplog.records if r.message.startswith("[stale_watcher_detail] ")
    ]
    assert len(detail_lines) == 1
    line = detail_lines[0]
    # cap 적용 — `...+5` 또는 `...+N=5` 등 표시 (5 = 25-20)
    assert "+5" in line, f"20개 cap 후 잔여 5개 표시 누락: {line}"


@pytest.mark.asyncio
async def test_stale_watcher_detail_last_resub_dash_when_missing(monkeypatch, caplog):
    """`last_resub` 가 미존재한 stale → `@-` 표시 (B3-6).

    사이클 29 (2026-05-21) — 의미 갱신: r>5 분기는 시간 기반 강제 재시도로 last_resub_at
    갱신됨. 본 케이스는 *시간당 cap 도달로 차단된 영구 stale* 종목이 last_resub_at 미갱신
    상태로 detail 에 들어가는 시나리오 — `@-` 표시 폴백 검증.
    """
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    # retry 가 이미 6회 누적 (다음 호출에서 7)
    sched._stale_retry_count = {"Z": 6}
    sched._stale_last_resubscribe_at = {}  # 부재 — 영구 stale 사전 진입
    # 사이클 29: 시간당 cap 도달 시나리오 — force_retry 발화 차단 → last_resub_at 미갱신
    now_dt = datetime.now(KST)
    sched._stale_force_retry_history = {
        "Z": [now_dt - timedelta(minutes=50 - i * 4) for i in range(12)]
    }
    sched._running = True

    import src.engine.scanner as scanner_mod
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {"Z": now_dt - timedelta(seconds=300)},
    )

    _setup_pool_mock(
        monkeypatch,
        subscribed={"Z"},
        session_groups={"main": {"Z"}},
    )

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    await sched._check_and_resubscribe_stale()

    detail_lines = [
        r.message for r in caplog.records if r.message.startswith("[stale_watcher_detail] ")
    ]
    assert len(detail_lines) == 1
    line = detail_lines[0]
    assert "@-" in line, f"last_resub 미존재 종목 `@-` 표시 누락: {line}"
