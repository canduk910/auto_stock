"""사이클 149 (2026-06-16) — 영역 D 회귀 가드.

`src/realtime/handler.py::_handle_market_op` 종목별 record_market_op_event 호출 검증.
- parse_market_op_payload 호출 + record 발화 (G-D1)
- `_on_board` 콜백 + record 양쪽 호출 (try/except 4중 영속, G-D2)

domain-expert 자문: `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`
"""

from __future__ import annotations

import pytest

from src.engine import market_operation_monitor as mom
from src.realtime import handler


@pytest.fixture(autouse=True)
def _reset_state_and_board_handler():
    mom.reset_market_op_state()
    saved = handler._on_board
    yield
    mom.reset_market_op_state()
    handler._on_board = saved


@pytest.mark.asyncio
async def test_G_D1_handle_market_op_calls_record_market_op_event() -> None:
    """HIGH — _handle_market_op 호출 시 record_market_op_event 발화 (parse 정합).

    VI 활성 payload 수신 → `_vi_active_tickers` add 영속 (사이클 149 영역 D 핵심).
    """
    # VI 활성 payload (10 컬럼) — vi_cls_code="1" (의제 1 truthy 매핑)
    payload = "N^^110^110^0^0^0^1^0^KRX"

    # _handle_market_op 직접 호출
    await handler._handle_market_op("H0UNMKO0", "005930", payload)

    # record_market_op_event 발화 영속 확인
    assert "005930" in mom.get_vi_active_tickers()
    assert mom.is_ticker_stale_excluded("005930") is True


@pytest.mark.asyncio
async def test_G_D2_handle_market_op_invokes_both_record_and_board_callback() -> None:
    """HIGH — record + _on_board 콜백 모두 호출 영속 (try/except 4중 영속).

    사이클 26 영속 = _on_board 콜백 (보드 전환) +
    사이클 149 신규 = record_market_op_event (종목별 state).
    """
    captured: list[tuple[str, str, str]] = []

    async def _capture(tr_key: str, mkop_cls_code: str, payload: str) -> None:
        captured.append((tr_key, mkop_cls_code, payload))

    handler.register_board_handler(_capture)

    # 거래정지 활성 payload
    payload = "Y^임시중단^110^110^0^0^0^0^0^KRX"
    await handler._handle_market_op("H0UNMKO0", "000020", payload)

    # record 발화 영속
    assert "000020" in mom.get_halt_active_tickers()
    # _on_board 콜백도 호출 영속 (사이클 26 영속)
    assert len(captured) == 1
    assert captured[0][0] == "000020"
    assert captured[0][1] == "110"
