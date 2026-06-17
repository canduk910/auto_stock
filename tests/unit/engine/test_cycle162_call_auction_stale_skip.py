"""사이클 162 회귀 가드 — 동시호가 시간대 stale 회피 (의제 E).

대상:
- `src/engine/session.py::SessionTracker.is_call_auction_now`
- `src/engine/stale_watcher_core.py::check_and_resubscribe_stale` _call_auction_skip hook

domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`.
"""

from __future__ import annotations

from datetime import datetime, time

import pytest

from src.engine.session import SessionTracker


# ───────── G-162-E-1 ~ G-162-E-5: SessionTracker.is_call_auction_now ─────────


def test_G_162_E_1_call_auction_code_110_장전동시호가():
    """G-162-E-1 (HIGH): MKOP_CLS_CODE=110 (장전 동시호가) → True."""
    tracker = SessionTracker()
    tracker._last_nxt_mkop_code = "110"
    # 시간 무관 — 코드 기반 즉시 True
    now = datetime(2026, 6, 18, 14, 0)  # 14:00 = 정규장
    assert tracker.is_call_auction_now(now) is True


def test_G_162_E_2_call_auction_code_121_장후동시호가():
    """G-162-E-2 (HIGH): MKOP_CLS_CODE=121 (장후 동시호가) → True."""
    tracker = SessionTracker()
    tracker._last_nxt_mkop_code = "121"
    now = datetime(2026, 6, 18, 10, 0)
    assert tracker.is_call_auction_now(now) is True


def test_G_162_E_3_regular_session_code_112_false():
    """G-162-E-3: MKOP_CLS_CODE=112 (장개시) + 정규장 시간 → False."""
    tracker = SessionTracker()
    tracker._last_nxt_mkop_code = "112"
    now = datetime(2026, 6, 18, 10, 30)
    assert tracker.is_call_auction_now(now) is False


def test_G_162_E_4_time_based_fallback_15_25_call_auction():
    """G-162-E-4 (HIGH): 코드 미수신 + 시간 15:25 → True (장후 동시호가)."""
    tracker = SessionTracker()
    # mkop_code 부재 (= "")
    now = datetime(2026, 6, 18, 15, 25)
    assert tracker.is_call_auction_now(now) is True


def test_G_162_E_5_time_based_fallback_08_45_call_auction():
    """G-162-E-5 (HIGH): 코드 미수신 + 시간 08:45 → True (장전 동시호가)."""
    tracker = SessionTracker()
    now = datetime(2026, 6, 18, 8, 45)
    assert tracker.is_call_auction_now(now) is True


def test_G_162_E_6_boundary_15_30_exit_call_auction():
    """G-162-E-6: 15:30 정각 = 동시호가 *후* → False (15:20~15:30 exclusive)."""
    tracker = SessionTracker()
    now = datetime(2026, 6, 18, 15, 30)
    assert tracker.is_call_auction_now(now) is False


def test_G_162_E_7_boundary_09_00_enter_regular():
    """G-162-E-7: 09:00 정각 = 정규장 진입 → False."""
    tracker = SessionTracker()
    now = datetime(2026, 6, 18, 9, 0)
    assert tracker.is_call_auction_now(now) is False


def test_G_162_E_8_boundary_15_19_59_before_call_auction():
    """G-162-E-8: 15:19:59 = 정규장 마지막 → False."""
    tracker = SessionTracker()
    now = datetime(2026, 6, 18, 15, 19, 59)
    assert tracker.is_call_auction_now(now) is False


def test_G_162_E_9_boundary_15_20_00_enter_call_auction():
    """G-162-E-9 (HIGH): 15:20:00 정각 = 동시호가 진입 → True (사용자 사고 영역)."""
    tracker = SessionTracker()
    now = datetime(2026, 6, 18, 15, 20, 0)
    assert tracker.is_call_auction_now(now) is True


# ───────── G-162-E-10 ~ G-162-SAFETY-1: stale_watcher_core hook ─────────


@pytest.mark.asyncio
async def test_G_162_E_10_stale_watcher_skip_during_call_auction(monkeypatch):
    """G-162-E-10 (HIGH): 동시호가 시간대 = stale 종목 *전체* skip + WARNING 1행.

    사용자 사고 영역 시정: 6/17 15:21:48 KST stale=10 → 5분 주기 재구독 시도 반복 차단.
    """
    from src.engine import stale_watcher_core as swc
    from src.engine.session import session_tracker

    # 동시호가 코드 강제 (시간 무관)
    session_tracker._last_nxt_mkop_code = "121"

    # mock scheduler
    class _MockScheduler:
        _stale_retry_count: dict = {}
        _stale_last_resubscribe_at: dict = {}
        _pending_next_day_clear: set = set()
        registry = type("R", (), {"all": lambda self: []})()

    mock_pool = type("MockPool", (), {})()
    mock_pool.get_subscribed_tickers = lambda: {"196170", "476830"}
    mock_pool._subscribed_at = {}

    import sys
    fake_websocket_pool = type(sys)("src.realtime.websocket_pool")
    fake_websocket_pool.kis_ws_pool = mock_pool
    monkeypatch.setitem(sys.modules, "src.realtime.websocket_pool", fake_websocket_pool)

    # ticker_last_tick = 빈 dict → 모두 stale 판정 가능 상태
    from src.engine import scanner as _scanner
    monkeypatch.setattr(_scanner, "ticker_last_tick", {}, raising=False)

    sched = _MockScheduler()
    import logging
    import io
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    swc.logger.addHandler(handler)
    try:
        await swc.check_and_resubscribe_stale(sched)
    finally:
        swc.logger.removeHandler(handler)
        session_tracker._last_nxt_mkop_code = ""

    log_output = log_stream.getvalue()
    assert "[stale_skip_call_auction]" in log_output, \
        f"동시호가 시간대 stale skip WARNING 미발화. 로그: {log_output!r}"


import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_G_162_SAFETY_1_no_risk_or_order_engine_import_in_session_module():
    """G-162-SAFETY-1 (HIGH): session.py 변경 영역 risk/order_engine import 0건."""
    import ast
    path = _REPO_ROOT / "src" / "engine" / "session.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad_modules = {"src.engine.risk", "src.engine.order_engine", "src.realtime.websocket", "src.auth.token"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in bad_modules, \
                f"session.py 영역 위험 import: {node.module}"


def test_G_162_SAFETY_2_no_risk_or_order_engine_import_in_pending_ndc_db():
    """G-162-SAFETY-2 (HIGH): pending_next_day_clear.py 영역 risk/order_engine import 0건."""
    import ast
    path = _REPO_ROOT / "src" / "db" / "pending_next_day_clear.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad_modules = {"src.engine.risk", "src.engine.order_engine", "src.realtime.websocket", "src.auth.token"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in bad_modules, \
                f"pending_next_day_clear.py 영역 위험 import: {node.module}"
