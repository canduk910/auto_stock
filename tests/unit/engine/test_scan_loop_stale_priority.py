"""_scan_loop stale 우선 재구독 가드 (사이클 13-D, 2026-05-18).

배경: K stale watcher 는 120s 주기로 발화한다(사이클 9 — KIS 차단 회피).
`_scan_loop` 는 5분(300s) 주기. WS silent inactive 가 발생하면 회복 시간이
최대 120s ~ 600s 까지 늘어진다. 사이클 13-A/B 는 watcher 임계 단축 + UI 가시화로
대응했지만, `_scan_loop` 통합 구독 직후 stale 우선 재구독을 1행 추가하면
**5분 주기의 자연 회복 경로**가 새로 생긴다.

명세 (`_resubscribe_stale_priority(cap=10)`):
- `scanner.ticker_last_tick` 풀 전체 합집합 사용
- 현재시각 - last_tick > `STALE_FRESHNESS_SECS`(=60s) 종목만 수집
- 최대 `cap` 건 (기본 10) — KIS Rate Limit 보호
- 각 종목에 `kis_ws_pool.subscribe(TICK_TR_ID, ticker, priority='HIGH', bypass_limit=True)` 호출
- 종목 간 50ms sleep
- 종목별 예외 격리 (continue, ERROR 로그)
- 반환: 재구독한 ticker 리스트
- INFO 로그 `[stale_priority_resubscribe] count=N tickers=[...]`

사이클 72 hotfix: write_log 제거 → logger.info 단독 → 로그 검증은 caplog 로 전환.

세 케이스로 의미체계 고정:
- Case A: stale 5 / fresh 3 → stale 5만 subscribe 호출됨
- Case B: 전체 fresh → subscribe 0회 (skip)
- Case C: stale 15 → cap=10 적용으로 10건만 처리
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공용 헬퍼: scheduler 인스턴스 + scanner ticker_last_tick 시드
# ---------------------------------------------------------------------------
async def _run_helper(
    fresh_tickers: list[str],
    stale_tickers: list[str],
    cap: int = 10,
) -> tuple[list, list]:
    """`_resubscribe_stale_priority(cap)` 호출 + subscribe 콜 추적.

    반환: (subscribe_calls, write_log_calls)
    - subscribe_calls: kis_ws_pool.subscribe 호출 인자 dict 리스트
    - write_log_calls: 하위 호환 빈 리스트 (사이클 72: write_log 제거 → caplog 전환)
    """
    from src.engine import scheduler as scheduler_module
    from src.engine.scheduler import STALE_FRESHNESS_SECS, TradingScheduler
    from src.engine.scanner import KST_TZ, ticker_last_tick

    # last_tick 시드 — fresh 는 now, stale 은 now - (FRESHNESS+30)s
    ticker_last_tick.clear()
    now = datetime.now(KST_TZ)
    fresh_dt = now
    stale_dt = now - timedelta(seconds=STALE_FRESHNESS_SECS + 30)
    for t in fresh_tickers:
        ticker_last_tick[t] = fresh_dt
    for t in stale_tickers:
        ticker_last_tick[t] = stale_dt

    sched = TradingScheduler.__new__(TradingScheduler)
    # 사이클 25-B: _resubscribe_stale_priority 가 registry + _pending_next_day_clear 를 참조.
    # 이 헬퍼는 positions/ndc 없는 "후보만 stale" 시나리오를 시뮬레이션하므로 빈 상태로 세팅.
    sched._pending_next_day_clear = set()

    class _EmptyRegistry:
        def all(self):
            return []

    sched.registry = _EmptyRegistry()

    # kis_ws_pool.subscribe AsyncMock spy
    subscribe_calls: list[dict] = []

    async def fake_subscribe(tr_id: str, tr_key: str, *, priority: str = "LOW", bypass_limit: bool = False):
        subscribe_calls.append(
            {"tr_id": tr_id, "tr_key": tr_key, "priority": priority, "bypass_limit": bypass_limit}
        )
        return "main"

    from src.realtime import websocket_pool as wp_module
    original_subscribe = wp_module.kis_ws_pool.subscribe
    wp_module.kis_ws_pool.subscribe = fake_subscribe

    try:
        await sched._resubscribe_stale_priority(cap=cap)
    finally:
        wp_module.kis_ws_pool.subscribe = original_subscribe
        ticker_last_tick.clear()

    # 사이클 72: write_log 제거 → 빈 리스트 반환 (하위 호환, 로그 검증은 caplog 로 전환)
    return subscribe_calls, []


# ---------------------------------------------------------------------------
# Case A: stale 5 + fresh 3 → stale 5만 subscribe 호출 (fresh skip)
# 사이클 25-B: positions/ndc 없는 후보 stale → LOW+bypass_limit=False 재구독
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_only_resubscribed_fresh_skipped(caplog):
    import logging
    fresh = ["100001", "100002", "100003"]
    stale = ["200001", "200002", "200003", "200004", "200005"]

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    subscribe_calls, _ = await _run_helper(fresh, stale, cap=10)

    # stale 5건만 subscribe 호출
    assert len(subscribe_calls) == 5, (
        f"stale 5 종목만 재구독되어야 함 (fresh skip), got={len(subscribe_calls)}"
    )

    called_tickers = {c["tr_key"] for c in subscribe_calls}
    assert called_tickers == set(stale), (
        f"호출된 종목이 stale set 과 일치해야 함, got={called_tickers}"
    )

    # fresh 는 1건도 호출 안 됨
    for f in fresh:
        assert f not in called_tickers, f"fresh 종목 {f} 가 호출됨 — 결함"

    # 사이클 25-B: positions/ndc 없는 후보 → LOW+bypass_limit=False
    # (_run_helper 의 _EmptyRegistry 로 positions/ndc 모두 빈 상태)
    for call in subscribe_calls:
        assert call["priority"] == "LOW", (
            f"후보 stale 종목 {call['tr_key']} 는 LOW (사이클 25-B), got={call['priority']}"
        )
        assert call["bypass_limit"] is False, (
            f"후보 stale 종목 {call['tr_key']} 는 bypass_limit=False (사이클 25-B), got={call['bypass_limit']}"
        )

    # INFO 로그 검증 — 사이클 72: write_log 제거 → caplog 로 전환
    log_text = "\n".join(r.message for r in caplog.records)
    assert "stale_priority_resubscribe" in log_text, (
        f"`[stale_priority_resubscribe]` INFO 로그 누락. caplog={log_text!r}"
    )


# ---------------------------------------------------------------------------
# Case B: 전체 fresh → subscribe 호출 0건 (skip 정상)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_fresh_skipped():
    fresh = ["100001", "100002", "100003", "100004", "100005"]
    stale: list[str] = []

    subscribe_calls, write_log_calls = await _run_helper(fresh, stale, cap=10)

    assert len(subscribe_calls) == 0, (
        f"전체 fresh 일 때 subscribe 호출이 없어야 함, got={subscribe_calls}"
    )

    # 0건이면 INFO 로그는 남지 않아도 OK (`[stale_priority_resubscribe]` 매칭 없음 허용)
    matched = [c for c in write_log_calls if "stale_priority_resubscribe" in c["message"]]
    if matched:
        # 만약 로그를 남긴다면 count=0 명시여야 한다
        assert any("count=0" in c["message"] for c in matched), (
            f"전체 fresh 시 로그가 있다면 count=0 명시 필요, got={matched}"
        )


# ---------------------------------------------------------------------------
# Case C: stale 15 → cap=10 적용으로 10건만 처리, 11~15 는 다음 사이클 위임
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_capped_at_ten(caplog):
    import logging
    fresh: list[str] = []
    # stale 15개 (정렬 안정성 위해 sortable id)
    stale = [f"30000{i:02d}" for i in range(15)]

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    subscribe_calls, _ = await _run_helper(fresh, stale, cap=10)

    assert len(subscribe_calls) == 10, (
        f"cap=10 적용으로 10건만 처리되어야 함, got={len(subscribe_calls)}"
    )

    # 호출된 종목은 stale set 의 부분집합
    called_tickers = {c["tr_key"] for c in subscribe_calls}
    assert called_tickers.issubset(set(stale)), (
        f"호출 종목이 stale set 부분집합이어야 함, got={called_tickers}"
    )

    # INFO 로그에 count=10 명시 — 사이클 72: write_log 제거 → caplog 로 전환
    log_text = "\n".join(r.message for r in caplog.records)
    assert "stale_priority_resubscribe" in log_text, (
        f"`[stale_priority_resubscribe]` INFO 로그 누락. caplog={log_text!r}"
    )
    assert "count=10" in log_text, (
        f"cap 적용 시 count=10 명시 필요. caplog={log_text!r}"
    )
