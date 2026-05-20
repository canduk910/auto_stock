"""src/engine/session.py 단위 테스트.

- MarketBoard enum 값
- boards_at(time): 시각 → 활성 보드 매핑
- parse_tradable_boards / get_tradable_boards: 파라미터 파싱 + fallback
- SessionTracker.tick: 시각 기반 활성 보드 갱신 + enter/exit 콜백 발화
- SessionTracker.is_tradable: 전략 tradable_boards 와 활성 보드 교집합
"""

from __future__ import annotations

from datetime import datetime, time

import pytest

from src.engine.session import (
    MarketBoard,
    SessionTracker,
    boards_at,
    get_tradable_boards,
    parse_tradable_boards,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# MarketBoard enum
# ---------------------------------------------------------------------------
def test_market_board_values():
    assert MarketBoard.PRE_NXT == "pre_nxt"
    assert MarketBoard.KRX_OPEN == "krx_open"
    assert MarketBoard.MAIN == "main"
    assert MarketBoard.KRX_AFTER == "krx_after"
    assert MarketBoard.POST_NXT == "post_nxt"


# ---------------------------------------------------------------------------
# boards_at — 시각 기반 활성 보드 매핑
# ---------------------------------------------------------------------------
def test_boards_at_pre_nxt_window_only():
    # 08:00~08:30 — PRE_NXT 단독
    boards = boards_at(time(8, 15))
    assert boards == frozenset({MarketBoard.PRE_NXT})


def test_boards_at_krx_open_overlap_window():
    # 사이클 26: 08:30~09:00 — PRE_NXT 단독 (KRX_OPEN 구간 제거)
    boards = boards_at(time(8, 45))
    assert boards == frozenset({MarketBoard.PRE_NXT})


def test_boards_at_main_window():
    # 09:00~15:20 — MAIN 단독
    boards = boards_at(time(13, 0))
    assert boards == frozenset({MarketBoard.MAIN})


def test_boards_at_buy_stop_window_still_main():
    # 15:20~15:30 — buy_stop 구간이지만 보드는 여전히 MAIN
    boards = boards_at(time(15, 25))
    assert boards == frozenset({MarketBoard.MAIN})


def test_boards_at_krx_after_and_post_nxt_overlap():
    # 사이클 26: 15:40~ — POST_NXT 단독 (KRX_AFTER 구간 제거, POST_NXT 전환 15:30 → 15:40)
    boards = boards_at(time(16, 0))
    assert boards == frozenset({MarketBoard.POST_NXT})


def test_boards_at_post_nxt_only():
    # 18:00~20:00 — POST_NXT 단독
    boards = boards_at(time(19, 0))
    assert boards == frozenset({MarketBoard.POST_NXT})


def test_boards_at_outside_session_returns_empty():
    assert boards_at(time(7, 30)) == frozenset()
    assert boards_at(time(20, 30)) == frozenset()


# ---------------------------------------------------------------------------
# parse_tradable_boards
# ---------------------------------------------------------------------------
def test_parse_tradable_boards_string_list():
    result = parse_tradable_boards(["main", "pre_nxt"])
    assert result == frozenset({MarketBoard.MAIN, MarketBoard.PRE_NXT})


def test_parse_tradable_boards_with_unknown_value_warns_and_skips():
    result = parse_tradable_boards(["main", "unknown_board"])
    assert result == frozenset({MarketBoard.MAIN})


def test_parse_tradable_boards_empty_returns_empty():
    assert parse_tradable_boards(None) == frozenset()
    assert parse_tradable_boards([]) == frozenset()


# ---------------------------------------------------------------------------
# get_tradable_boards — params 우선 + fallback
# ---------------------------------------------------------------------------
def test_get_tradable_boards_uses_params_when_present():
    result = get_tradable_boards("momentum", {"tradable_boards": ["main"]})
    assert result == frozenset({MarketBoard.MAIN})


def test_get_tradable_boards_falls_back_to_default_when_params_absent():
    result = get_tradable_boards("momentum", None)
    # _DEFAULT_TRADABLE_BOARDS["momentum"] = {KRX_OPEN, MAIN}
    assert MarketBoard.MAIN in result
    assert MarketBoard.KRX_OPEN in result


def test_get_tradable_boards_unknown_strategy_returns_empty():
    assert get_tradable_boards("ghost_strategy", None) == frozenset()


# ---------------------------------------------------------------------------
# SessionTracker — 활성 보드 추적 + 콜백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tracker_tick_updates_active_boards():
    tracker = SessionTracker()
    # 시각 13:00 — MAIN
    await tracker.tick(now=datetime(2026, 5, 8, 13, 0))
    assert tracker.active == frozenset({MarketBoard.MAIN})
    assert tracker.is_active(MarketBoard.MAIN)


@pytest.mark.asyncio
async def test_tracker_enter_exit_callbacks_fire_on_transition():
    tracker = SessionTracker()
    entered: list[MarketBoard] = []
    exited: list[MarketBoard] = []

    async def on_enter(b):
        entered.append(b)

    async def on_exit(b):
        exited.append(b)

    tracker.register_on_enter(on_enter)
    tracker.register_on_exit(on_exit)

    # MAIN 진입
    await tracker.tick(now=datetime(2026, 5, 8, 13, 0))
    assert MarketBoard.MAIN in entered
    assert exited == []

    # 사이클 26: 16:00 → POST_NXT 단독 진입, MAIN 종료 (KRX_AFTER 제거)
    await tracker.tick(now=datetime(2026, 5, 8, 16, 0))
    assert MarketBoard.MAIN in exited
    assert MarketBoard.POST_NXT in entered
    # 사이클 26: KRX_AFTER 는 더 이상 활성화되지 않음
    assert MarketBoard.KRX_AFTER not in entered


@pytest.mark.asyncio
async def test_tracker_is_tradable_when_strategy_board_overlaps_active():
    tracker = SessionTracker()
    await tracker.tick(now=datetime(2026, 5, 8, 13, 0))  # MAIN
    # momentum tradable_boards 에 main 포함 → True
    assert tracker.is_tradable("momentum", {"tradable_boards": ["main"]}) is True


@pytest.mark.asyncio
async def test_tracker_is_tradable_false_when_no_overlap():
    tracker = SessionTracker()
    await tracker.tick(now=datetime(2026, 5, 8, 13, 0))  # MAIN
    # post_nxt 만 허용한 전략 → MAIN 활성 시 False
    assert tracker.is_tradable("foo", {"tradable_boards": ["post_nxt"]}) is False


@pytest.mark.asyncio
async def test_tracker_is_tradable_false_when_no_active():
    tracker = SessionTracker()
    # 장 외 시간 — 활성 보드 비어있음
    await tracker.tick(now=datetime(2026, 5, 8, 7, 0))
    assert tracker.is_tradable("momentum", {"tradable_boards": ["main"]}) is False


@pytest.mark.asyncio
async def test_tracker_on_h0nxmko0_records_last_code():
    tracker = SessionTracker()
    await tracker.on_h0nxmko0(tr_key="005930", mkop_cls_code="129", payload="raw")
    assert tracker.last_nxt_mkop_code == "129"


@pytest.mark.asyncio
async def test_tracker_callback_exception_does_not_break_tick():
    """등록된 콜백이 예외를 던져도 tick 자체는 성공해야 한다."""
    tracker = SessionTracker()

    async def boom(_b):
        raise RuntimeError("intentional")

    tracker.register_on_enter(boom)
    # 예외가 propagate 되지 않아야 함
    await tracker.tick(now=datetime(2026, 5, 8, 13, 0))
    assert MarketBoard.MAIN in tracker.active
