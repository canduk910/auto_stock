"""사이클 202 — 동시호가 게이트 시간 flakiness 차단 conftest fixture 가드.

배경: stale_watcher 테스트(~20 파일)가 `is_call_auction_now()` 를 mock/freeze 하지
않아, CI 가 동시호가 시간창(08:30~09:00 / 15:20~15:30 KST)에 실행되면
`[stale_skip_call_auction]` 발화로 stale 감지가 skip → flaky 실패(사이클 201 push 가
15:2x 창에 걸려 CI red 실발현). conftest `_neutralize_call_auction_gate` autouse fixture
가 `session_tracker.is_call_auction_now` 를 전역 False 로 중립화(시계 독립화).

이 파일명에 "call_auction" 미포함 → fixture 활성 (제외 대상 아님).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_KST = timezone(timedelta(hours=9))


def test_fixture_neutralizes_call_auction_gate_default():
    """비-call_auction 테스트에서 is_call_auction_now() 는 fixture 로 항상 False."""
    from src.engine.session import session_tracker

    assert session_tracker.is_call_auction_now() is False


def test_fixture_forces_false_even_inside_window():
    """동시호가 창 한복판(15:25) 시각을 넘겨도 False — 실제 로직이면 True 일 시각.

    이 단언이 통과하면 fixture 가 시계 의존을 완전히 제거했음이 증명된다
    (15:20~15:30 = 사이클 162 장후 동시호가 time-fallback 창).
    """
    from src.engine.session import session_tracker

    in_window = datetime(2026, 7, 10, 15, 25, 0, tzinfo=_KST)
    assert session_tracker.is_call_auction_now(in_window) is False

    morning_window = datetime(2026, 7, 10, 8, 45, 0, tzinfo=_KST)
    assert session_tracker.is_call_auction_now(morning_window) is False
