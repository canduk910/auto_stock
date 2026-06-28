"""사이클 162 회귀 가드 — 동시호가 시간대 stale 회피 (의제 E).

대상:
- `src/engine/session.py::SessionTracker.is_call_auction_now`
- `src/engine/stale_watcher_core.py::check_and_resubscribe_stale` _call_auction_skip hook

domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`.
"""

from __future__ import annotations

from datetime import datetime, time

import pytest
from freezegun import freeze_time

from src.engine.session import SessionTracker


# ───────── G-162-E-1 ~ G-162-E-5: SessionTracker.is_call_auction_now ─────────


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 182 의미 전환 (사이클 66 K-2 패턴) — code=110 @ 14:00(MAIN) 은 110 유효창"
        "(08:25~09:05) 밖 고착(stuck-110-during-MAIN) → 시간창 게이트 도입 후 False 가 정답. "
        "본 케이스는 사이클 162 시점 결함('시간 무관 코드 즉시 True')을 정상으로 박제한 것. "
        "Green(시간창 게이트) 완료 시 단언 실패 → 자동 XFAIL 전환. 정답(False) 단언은 "
        "test_cycle182_call_auction_time_gate.py::G-182-STUCK 가 보유."
    ),
)
def test_G_162_E_1_call_auction_code_110_장전동시호가():
    """G-162-E-1 (HIGH → 사이클 182 의미 전환): MKOP_CLS_CODE=110 @ 14:00(MAIN).

    사이클 162 원본 단언 = '시간 무관 코드 즉시 True' = stuck-110-during-MAIN 결함 박제.
    사이클 182: 14:00 은 110 유효창 밖 → 고착 코드 무시 → 시간 폴백도 False → False 정답.
    """
    tracker = SessionTracker()
    tracker._last_nxt_mkop_code = "110"
    now = datetime(2026, 6, 18, 14, 0)  # 14:00 = 정규장(MAIN), 110 유효창 밖
    assert tracker.is_call_auction_now(now) is True


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 182 의미 전환 (사이클 66 K-2 패턴) — code=121 @ 10:00(MAIN) 은 121 유효창"
        "(15:15~15:35) 밖 고착(stuck-121-during-MAIN) → 시간창 게이트 도입 후 False 가 정답. "
        "사이클 162 결함 박제 → Green 완료 시 자동 XFAIL 전환. 정답(False) 단언은 "
        "test_cycle182_call_auction_time_gate.py::G-182-STUCK 가 보유."
    ),
)
def test_G_162_E_2_call_auction_code_121_장후동시호가():
    """G-162-E-2 (HIGH → 사이클 182 의미 전환): MKOP_CLS_CODE=121 @ 10:00(MAIN).

    사이클 162 원본 단언 = 코드 즉시 True = stuck-121-during-MAIN 결함 박제.
    사이클 182: 10:00 은 121 유효창 밖 → 고착 코드 무시 → 시간 폴백도 False → False 정답.
    """
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
    """G-162-E-10 (HIGH → 사이클 182 의미 전환): 동시호가 유효창 내 code 기반 skip + WARNING.

    사용자 사고 영역 시정: 6/17 15:21:48 KST stale=10 → 5분 주기 재구독 시도 반복 차단.

    사이클 182 의미 전환: `check_and_resubscribe_stale` 가 `is_call_auction_now(now=실제현재KST)`
    를 넘기므로, 시간창 게이트(사이클 182) 도입 후 `code="121"` 단독으론 더 이상 시간 무관 True 가
    아니다 → 실행 시각 의존(flaky, 사이클 176 교훈 위반). E-10 의 *정당한* 의도("진짜 동시호가
    시간대엔 code 기반 skip 발생")는 보존하되, freezegun 으로 121 유효창(15:15~15:35) 내 KST 시각
    (15:25)으로 고정 → 게이트 도입 후에도 True → skip 발생 → 단언 그대로 PASS. 날짜는 고정 연도 사용.
    """
    from src.engine import stale_watcher_core as swc
    from src.engine.session import session_tracker

    # 동시호가 유효창(15:20~15:30) 내 code 기반 skip (사이클 182 시간창 게이트 정합)
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
        # 사이클 182 — freezegun UTC 06:25 = KST 15:25 (장후 동시호가 121 유효창 내).
        # stale_watcher_core 내부 `now = datetime.now(KST_TZ)` 가 15:25 KST 로 고정 →
        # 시간창 게이트(Green) 도입 후에도 code=121 @ 15:25 → True → skip 발생.
        with freeze_time("2024-06-20 15:25:00+09:00"):
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
