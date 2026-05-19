"""사이클 15-A (2026-05-19) — `_scan_loop` delta-only 재구독 + scanner LOW skip.

배경 (KIS 공지 2026-05-18):
> 2) 데이터 구독 후 데이터 수신여부 검증 없이 무한 등록/해제 반복 처리

기존 _scan_loop 가 매 5분마다 `unsubscribe_all() + subscribe_filtered_stocks()` 로
모든 종목 전체 해제 + 재구독 → KIS "비정상 케이스 2" 패턴.

fix:
- scheduler._scan_loop: `unsubscribe_all()` 제거 + delta_remove (빠진 종목만 unsubscribe)
- scanner.subscribe_filtered_stocks LOW 분기: 이미 풀에 있는 종목 SEND skip
  (HIGH 종목 = positions/next_day_clear 는 promote 가능성 보존 — always 호출)

5 케이스:
- A: 동일 합집합 재호출 시 LOW 종목 SEND 0건 (이미 풀에 있음)
- B: 새 LOW 종목 추가 시 그 종목만 subscribe SEND
- C: 빠진 종목만 unsubscribe (delta_remove)
- D: HIGH 종목(positions) 은 always subscribe 호출 (풀 promote 보존)
- E: HIGH 새 종목은 subscribe 호출 (메인 등록)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def patched_pool(monkeypatch):
    """`kis_ws_pool` 의 subscribe/unsubscribe/get_subscribed_tickers mock."""
    from src.engine import scanner as scanner_mod
    from src.realtime import websocket_pool as wp_mod

    sub_calls: list[tuple[str, str, str]] = []
    unsub_calls: list[tuple[str, str]] = []

    async def _sub(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        sub_calls.append((tr_id, tr_key, priority))
        return "main"

    async def _unsub(tr_id, tr_key):
        unsub_calls.append((tr_id, tr_key))

    monkeypatch.setattr(wp_mod.kis_ws_pool, "subscribe", _sub, raising=False)
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", _unsub, raising=False)

    # MAX_SUBSCRIPTIONS=41 가정으로 _subscriptions 크기 직접 mock
    fake_main_subscriptions: set[tuple[str, str]] = set()
    monkeypatch.setattr(scanner_mod.kis_ws, "_subscriptions", fake_main_subscriptions, raising=False)

    return {
        "sub_calls": sub_calls,
        "unsub_calls": unsub_calls,
        "fake_subscriptions": fake_main_subscriptions,
    }


# ===========================================================================
# Case A: 동일 합집합 재호출 시 LOW 종목 SEND 0건
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_filtered_stocks_skips_low_already_in_pool(monkeypatch, patched_pool):
    """이미 풀에 구독 중인 LOW 종목은 SEND skip (KIS 정상 패턴)."""
    from src.engine.scanner import TICK_TR_ID, subscribe_filtered_stocks
    from src.realtime import websocket_pool as wp_mod

    # 풀에 이미 LOW 종목 3개 구독 중
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: {"A001", "A002", "A003"}, raising=False,
    )

    # 동일 종목으로 priority_groups 호출 — momentum 그룹
    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "breakout": ["A001", "A002", "A003"],
        "momentum": [],
        "swing": [],
    }
    await subscribe_filtered_stocks(
        tickers=[], extra_tickers=[],
        priority_groups=priority_groups,
    )

    # LOW (breakout) 3 종목 모두 이미 풀에 있으므로 subscribe SEND 0건
    low_calls = [c for c in patched_pool["sub_calls"] if c[2] == "LOW"]
    assert len(low_calls) == 0, (
        f"이미 풀에 있는 LOW 종목은 SEND skip 필요. 실제 호출: {low_calls}"
    )


# ===========================================================================
# Case B: 새 LOW 종목 추가 시 그 종목만 subscribe SEND
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_filtered_stocks_sends_only_new_low(monkeypatch, patched_pool):
    """풀에 없는 신규 LOW 종목만 subscribe SEND."""
    from src.engine.scanner import TICK_TR_ID, subscribe_filtered_stocks
    from src.realtime import websocket_pool as wp_mod

    # 풀에 A001/A002 이미 있음, A003/A004 신규
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: {"A001", "A002"}, raising=False,
    )

    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "breakout": ["A001", "A002", "A003", "A004"],
        "momentum": [],
        "swing": [],
    }
    await subscribe_filtered_stocks(
        tickers=[], extra_tickers=[],
        priority_groups=priority_groups,
    )

    low_calls = [c for c in patched_pool["sub_calls"] if c[2] == "LOW"]
    low_tickers_sent = {c[1] for c in low_calls}
    assert low_tickers_sent == {"A003", "A004"}, (
        f"신규 LOW 종목만 SEND. 기대=A003/A004, 실제={low_tickers_sent}"
    )


# ===========================================================================
# Case C: 빠진 종목만 unsubscribe (scheduler._scan_loop 영역)
# ===========================================================================
@pytest.mark.asyncio
async def test_scan_loop_delta_remove_only_dropped_tickers(monkeypatch, patched_pool):
    """scheduler._scan_loop 가 빠진 종목만 unsubscribe (delta_remove).

    fix 후: 현재 풀 - 새 합집합 = delta_remove → 그 종목만 unsubscribe.
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.scanner import TICK_TR_ID
    from src.realtime import websocket_pool as wp_mod

    # 현재 풀: A001/A002/A003/A004/A005
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: {"A001", "A002", "A003", "A004", "A005"}, raising=False,
    )

    sched = TradingScheduler()
    # 새 합집합: A002/A003/A006 (A001/A004/A005 빠짐, A006 신규)
    new_set = {"A002", "A003", "A006"}

    await sched._delta_unsubscribe_dropped(new_set)

    # delta_remove = {A001, A004, A005} 만 unsubscribe
    unsub_tickers = {c[1] for c in patched_pool["unsub_calls"]}
    assert unsub_tickers == {"A001", "A004", "A005"}, (
        f"빠진 종목만 unsubscribe. 기대={'A001','A004','A005'}, 실제={unsub_tickers}"
    )


# ===========================================================================
# Case D: HIGH 종목 (positions) 은 always subscribe 호출 (promote 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_filtered_stocks_high_always_calls(monkeypatch, patched_pool):
    """HIGH 종목 (positions/next_day_clear) 은 이미 풀에 있어도 always subscribe.

    풀의 _select_session 이 promote (보조→메인) 또는 noop 판단.
    scanner 가 사전에 skip 하면 안 됨.
    """
    from src.engine.scanner import TICK_TR_ID, subscribe_filtered_stocks
    from src.realtime import websocket_pool as wp_mod

    # 풀에 H001 이미 있음 (예: 보조 세션에 LOW 로 있었던 종목)
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: {"H001"}, raising=False,
    )

    priority_groups = {
        "positions": ["H001"],  # HIGH — 이미 풀에 있어도 always 호출
        "next_day_clear": [],
        "breakout": [],
        "momentum": [],
        "swing": [],
    }
    await subscribe_filtered_stocks(
        tickers=[], extra_tickers=[],
        priority_groups=priority_groups,
    )

    high_calls = [c for c in patched_pool["sub_calls"] if c[2] == "HIGH"]
    high_tickers = {c[1] for c in high_calls}
    assert "H001" in high_tickers, (
        f"HIGH positions 종목은 always SEND (promote 보존). 실제={high_tickers}"
    )


# ===========================================================================
# Case E: HIGH 새 종목은 subscribe 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_filtered_stocks_high_new_subscribes(monkeypatch, patched_pool):
    """HIGH 신규 종목 (positions / next_day_clear) 은 subscribe SEND."""
    from src.engine.scanner import TICK_TR_ID, subscribe_filtered_stocks
    from src.realtime import websocket_pool as wp_mod

    # 풀 빈 상태
    monkeypatch.setattr(
        wp_mod.kis_ws_pool, "get_subscribed_tickers",
        lambda: set(), raising=False,
    )

    priority_groups = {
        "positions": ["P001"],
        "next_day_clear": ["N001"],
        "breakout": [],
        "momentum": [],
        "swing": [],
    }
    await subscribe_filtered_stocks(
        tickers=[], extra_tickers=[],
        priority_groups=priority_groups,
    )

    high_calls = [c for c in patched_pool["sub_calls"] if c[2] == "HIGH"]
    high_tickers = {c[1] for c in high_calls}
    assert high_tickers == {"P001", "N001"}, (
        f"HIGH 신규 종목 모두 SEND. 기대=P001/N001, 실제={high_tickers}"
    )
