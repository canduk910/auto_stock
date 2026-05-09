"""체결통보 선행 race 가드 — WS 가 REST 응답보다 먼저 도착하는 시나리오."""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position, Signal
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_buy_chegyeol_race_when_ws_first_then_completed_direct_insert(order_env):
    """체결통보가 execute_buy 의 PENDING INSERT 보다 먼저 도착해도
    update_trade_status 가 0건 반환하면 COMPLETED 행을 직접 INSERT 하고
    뒤에 도착하는 execute_buy 응답에서는 PENDING INSERT 를 생략한다.
    """
    env = order_env

    # update_trade_status 가 항상 0 반환 (PENDING row 없음 → race 시뮬레이션)
    env.state.update_status_affected = 0

    # _completed_orders 사전 등록 — order_no 가 매핑 등록 직후에 set 에 있을 때
    # PENDING INSERT 생략됨을 검증
    # 실제로는 _handle_buy_fill 이 먼저 실행되어 set 에 추가되지만,
    # 여기서는 양방향 검증 — 직접 set 에 미리 넣고 execute_buy 가 그것을 발견하는지

    # 1. 체결통보가 먼저 들어오는 시나리오: order_no 모름 → 종목코드 기반 처리 시도
    # 실제 운영에서는 같은 order_no 로 _handle_buy_fill 이 먼저 → COMPLETED INSERT → set 등록
    # 그 후 execute_buy 가 응답 받아서 그 set 을 보고 PENDING 생략

    # 단순화: execute_buy 가 응답 직전에 _completed_orders 에 이미 같은 order_no 가 있으면
    # PENDING INSERT 생략됨을 검증한다.
    # → 첫 매수를 일반 실행해 order_no 를 알아내고, 다음 매수에서 그 order_no 가 _completed_orders 에 있도록 조작.
    # 실제 race 는 _handle_buy_fill 의 affected==0 분기에서 set 에 추가되므로 그쪽 경로가 더 정확.

    # 2. _handle_buy_fill 의 race 가드 검증 (운영에서 더 빈번한 케이스)
    momentum = env.momentum
    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)
    pending_record = env.calls.insert_trade[0]
    order_no = pending_record.order_no
    qty = env.engine._order_qty[order_no]

    # 체결통보 도착 → _handle_buy_fill 진입 → update_trade_status 호출 → affected=0 → race 가드
    await env.engine.handle_execution_notice(
        ticker="005930", order_no=order_no, side="BUY", price=90000, quantity=qty,
    )

    # 보정 INSERT — COMPLETED 행이 직접 INSERT 됨
    completed_inserts = [
        r for r in env.calls.insert_trade
        if r.trade_type == TradeType.BUY and r.status == TradeStatus.COMPLETED
    ]
    assert len(completed_inserts) == 1
    assert completed_inserts[0].strategy == "momentum"
    assert completed_inserts[0].order_no == order_no

    # _completed_orders set 에 등록되어, 만일 같은 order_no 의 응답이 뒤늦게 도착해도
    # PENDING INSERT 를 생략한다 — 다만 이 시나리오에서는 응답이 먼저 와서 PENDING 도 1건 있음.
    # → 운영에서 진짜 race 는 응답이 더 늦게 와서 _completed_orders 검사로 PENDING 생략.
    # 그것은 별도 테스트로 분리한다 (아래 케이스).

    # 매핑은 정리됨
    assert order_no not in env.engine._order_strategy


@pytest.mark.asyncio
async def test_buy_pending_insert_skipped_when_order_no_in_completed_orders(order_env):
    """이미 _completed_orders 에 등록된 order_no 면 execute_buy 응답 직후 PENDING INSERT 생략.

    운영 시나리오: 시장가 즉시체결 → 체결통보(WS) 가 REST 응답보다 먼저 도착 →
    _handle_buy_fill 이 affected=0 보고 COMPLETED 직접 INSERT + set 에 order_no 등록 →
    뒤늦게 execute_buy 가 응답 받아서 set 검사 → PENDING INSERT 생략.
    """
    env = order_env
    momentum = env.momentum

    # next_buy_seq 가 1부터 시작 → place_order 가 BUY-000001 발급
    expected_order_no = "BUY-000001"
    env.engine._completed_orders.add(expected_order_no)

    await env.engine.execute_buy("005930", current_price=90000, strategy=momentum)

    # PENDING INSERT 생략됨을 검증
    pending_inserts = [
        r for r in env.calls.insert_trade if r.status == TradeStatus.PENDING
    ]
    assert pending_inserts == []  # 어떤 PENDING 도 INSERT 되지 않음

    # _completed_orders 에서는 제거되어야 한다 (소비됨)
    assert expected_order_no not in env.engine._completed_orders

    # 그러나 매핑(_order_strategy/_order_ticker/_order_qty)은 정상 등록 — 이후 도착할 추가 체결 통보 처리 위해
    assert env.engine._order_strategy[expected_order_no] == "momentum"
    assert env.engine._order_ticker[expected_order_no] == "005930"
