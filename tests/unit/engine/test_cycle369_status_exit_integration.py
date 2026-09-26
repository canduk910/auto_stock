"""cycle369 Red — G. 통합 청산: 실제 `OrderEngine.execute_sell` + `place_order` 모의.

leaf 는 「언제 부를지」만 정한다(자문 §6). 부른 뒤의 규약 — `_selling` 중복 차단 ·
거래소 결정 · APBK1943 지정가 5호가 폴백 · APBK0918 포지션 보존 — 은 전부 기존
`execute_sell` 안의 것이다. 이 파일은 `Signal.STATUS_EXIT` 발사가 그 규약을 **그대로**
타는지를 실제 엔진으로 잰다(8영역 무수정).

픽스처 = `tests/unit/engine/test_cycle229_sell_fallback_e2e.py` 패턴 재사용.
"""
from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.util.tick_size import step_down
from src.models.order import OrderDivision, OrderResult, OrderSide
from tests.unit.engine._cycle369_support import (
    LIVE,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    dblog,  # noqa: F401
    fetch,  # noqa: F401
    field,
    hold,
    holder,
    leaf,
    lines,
    open_info,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.real_status_watch,
    pytest.mark.usefixtures("no_real_kis"),
]

_T = "005160"
_PRICE = 12000


@pytest.fixture(autouse=True)
def _info(caplog, db_modes):
    open_info(caplog)


@pytest.fixture
def rig(monkeypatch):
    import src.engine.order_engine as _oe
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    s = holder("bull_flag_breakout")
    hold(s, _T, qty=3, buy_date=date(2026, 9, 25))
    reg = StrategyRegistry()
    reg.register(s)
    engine = OrderEngine(reg)

    place = AsyncMock()
    monkeypatch.setattr(_oe, "place_order", place)
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "SELL_RETRY_DELAY", 0)

    async def _krx(self, strategy_id, *, ticker=None, side="sell"):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(OrderEngine, "_strategy_exchange_async", _krx)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))
    monkeypatch.setitem(scanner.ticker_prices, _T, {"current_price": _PRICE})
    return SimpleNamespace(
        strategy=s, engine=engine, place=place,
        sched=SimpleNamespace(registry=reg, order_engine=engine, _running=True),
    )


def _ok(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="100530", krx_org_no="")


@pytest.mark.asyncio
async def test_g1_status_exit_goes_out_as_krx_market_sell(rig, clock, fetch, dblog):
    rig.place.side_effect = [_ok("ORD-369-1")]
    fetch.table[_T] = LIVE[_T]
    clock.set(10, 5, 30)
    await leaf().run_sell_pass(rig.sched)

    assert rig.place.await_count == 1
    kw = rig.place.await_args.kwargs
    assert kw["side"] == OrderSide.SELL
    assert kw["order_division"] == OrderDivision.MARKET, "ORD_DVSN=01 시장가"
    assert kw["price"] == 0
    assert kw["exchange"] == "KRX"
    assert kw["quantity"] == 3
    assert _T in rig.engine._selling, "체결 전 — `_selling` 이 중복 발사를 막는다"

    clock.set(10, 10, 30)
    await leaf().run_sell_pass(rig.sched)
    assert rig.place.await_count == 1, "체결 대기 중 재발사(D4 — 실제 엔진의 `_selling`)"


@pytest.mark.asyncio
async def test_g2_market_disallowed_falls_back_to_limit_5_ticks(rig, clock, fetch, dblog):
    rig.place.side_effect = [
        KisApiError(rt_cd="1", msg_cd="APBK1943", msg1="시장가매매불가 종목입니다"),
        _ok("ORD-369-2"),
    ]
    fetch.table[_T] = LIVE[_T]
    clock.set(10, 5, 30)
    await leaf().run_sell_pass(rig.sched)
    assert rig.place.await_count == 2
    second = rig.place.await_args_list[1].kwargs
    assert second["order_division"] == OrderDivision.LIMIT
    assert second["price"] == step_down(_PRICE, steps=5)


@pytest.mark.asyncio
async def test_g3_market_closed_rejection_keeps_position_and_refires_next_pass(
    rig, clock, fetch, dblog, caplog,
):
    rig.place.side_effect = [
        KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다."),
    ] + [_ok("ORD-369-3")] * 3
    fetch.table[_T] = LIVE[_T]
    clock.set(10, 5, 30)
    await leaf().run_sell_pass(rig.sched)
    assert _T in rig.strategy.state.positions, "청산 의무 — 거부 시 포지션 보존"
    assert _T not in rig.engine._selling, "`_selling` 좀비 = 손절 마비"

    clock.set(10, 10, 30)
    await leaf().run_sell_pass(rig.sched)
    attempts = [field(m, "attempt") for m in lines(caplog, "[status_exit_fire]", min_level=logging.WARNING)]
    assert attempts[:2] == ["1", "2"], "다음 패스에서 다시 쏴야 한다(상한 3 안)"
