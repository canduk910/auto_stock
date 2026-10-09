"""cycle428(F-422-1, 항목 5) — 매수 쪽(`execute_buy`)은 이번 사이클에서 처리를
바꾸지 않는다. 자문 지시("매수 쪽은 처리 변경 없이 현 행위를 테스트로 핀만 한다")
를 그대로 코드로 둔다.

`execute_buy` 의 1차 주문(`place_order`)이 `KisApiError` 가 아닌 예외(전송
오류·타임아웃)를 내면 **지금도 그대로** `except Exception:` 이
`pending_buys.discard` + `pending_buy_amounts.pop` 후 `raise` 한다 — 예외가
`risk.on_tick` 으로 전파된다. `src/api/base.py` D2(주문 경로 재시도 제한)가
같은 경로의 재시도 횟수를 줄이더라도, `execute_buy` 자신의 예외 처리 분기는
무변경이다.
"""

from __future__ import annotations

import pytest

from tests.unit.engine.test_cycle271_execute_buy_fill_during_insert import (
    PRICE,
    TICKER,
    make_env,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_execute_buy_primary_generic_exception_still_discards_and_raises(monkeypatch):
    """핀 — 비-`KisApiError` 예외는 여전히 `pending_buys`/`pending_buy_amounts` 를
    풀고 그대로 전파된다(새 UNKNOWN 분기 없음 — 매도 쪽과 달리 처리 변경 0)."""
    env = make_env(monkeypatch)

    async def boom(*args, **kwargs):
        raise TimeoutError("전송 오류 — 접수됐는지 모른다")

    monkeypatch.setattr("src.engine.order_engine.place_order", boom)

    with pytest.raises(TimeoutError):
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    state = env.momentum.state
    assert TICKER not in state.pending_buys, (
        "핀 대상 현 행위 — 비-KisApiError 는 pending_buys 를 discard 하고 전파한다"
    )
    assert TICKER not in state.pending_buy_amounts
