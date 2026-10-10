"""cycle436 카드 E — `StrategyState` 의 `pending_buy_amounts` 키 `(ticker, order_no)`.

사용자 지시(2026-10-10): "pending_buy_amounts 의 넣기·빼기를 한 곳으로 모으고,
키를 (ticker, order_no) 로 바꾼다". 여기는 `StrategyState.reserve_buy`/`release_buy`/
`clear_buy_reservations`/`total_pending_buy_amount` 의 순수 행위 계약을 직접 검증한다.
발사 창 J-4 시나리오(place_order 응답을 기다리는 동안 그 주문이 이미 체결됐을 때
되살리지 않기)는 `test_order_engine_buy.py::test_j4_3_*` 가 담당한다.
"""
from __future__ import annotations

import pytest

from src.engine.strategy_base import StrategyState

pytestmark = pytest.mark.unit


def _state() -> StrategyState:
    return StrategyState(strategy_id="momentum")


def test_two_orders_same_ticker_are_reserved_independently():
    """같은 종목에 주문이 둘 있으면 둘 다 독립적으로 예약된다(피라미딩 선결)."""
    s = _state()
    s.reserve_buy("005930", "ORD-A", 100_000)
    s.reserve_buy("005930", "ORD-B", 200_000)

    assert s.pending_buy_amounts[("005930", "ORD-A")] == 100_000
    assert s.pending_buy_amounts[("005930", "ORD-B")] == 200_000
    assert s.total_pending_buy_amount() == 300_000


def test_releasing_first_order_does_not_clear_second_reservation():
    """첫 주문 체결·취소(해제)가 두 번째 예약을 지우지 않는다."""
    s = _state()
    s.reserve_buy("005930", "ORD-A", 100_000)
    s.reserve_buy("005930", "ORD-B", 200_000)

    released = s.release_buy("005930", "ORD-A")

    assert released == 100_000
    assert ("005930", "ORD-A") not in s.pending_buy_amounts
    assert s.pending_buy_amounts[("005930", "ORD-B")] == 200_000
    assert s.total_pending_buy_amount() == 200_000


def test_release_buy_unknown_order_no_is_noop():
    """모르는 (ticker, order_no) 해제는 조용히 `None` — 다른 예약은 무변경."""
    s = _state()
    s.reserve_buy("005930", "ORD-A", 100_000)

    assert s.release_buy("005930", "NOPE") is None
    assert s.pending_buy_amounts[("005930", "ORD-A")] == 100_000


def test_release_buy_without_order_no_releases_whole_ticker():
    """`order_no=None` 은 그 종목의 예약 전체를 지운다(정산·종목 차단 해제 등에 남겨 둔
    종목 단위 해제) — 다른 종목은 무변경."""
    s = _state()
    s.reserve_buy("005930", "ORD-A", 100_000)
    s.reserve_buy("005930", "ORD-B", 200_000)
    s.reserve_buy("000660", "ORD-C", 50_000)

    released = s.release_buy("005930")

    assert released == 300_000
    assert not [k for k in s.pending_buy_amounts if k[0] == "005930"]
    assert s.pending_buy_amounts[("000660", "ORD-C")] == 50_000


def test_release_buy_without_order_no_on_empty_ticker_returns_none():
    s = _state()
    assert s.release_buy("005930") is None


def test_clear_buy_reservations_wipes_every_ticker():
    """정산(`_reset_daily_state`) — 전체 비우기는 종목·주문 구분 없이 전부."""
    s = _state()
    s.reserve_buy("005930", "ORD-A", 100_000)
    s.reserve_buy("000660", "ORD-B", 50_000)

    s.clear_buy_reservations()

    assert s.pending_buy_amounts == {}
    assert s.total_pending_buy_amount() == 0


def test_total_pending_buy_amount_sums_across_tickers_and_orders():
    s = _state()
    assert s.total_pending_buy_amount() == 0
    s.reserve_buy("005930", "ORD-A", 100_000)
    s.reserve_buy("005930", "ORD-B", 50_000)
    s.reserve_buy("000660", "ORD-C", 20_000)
    assert s.total_pending_buy_amount() == 170_000
