"""cycle424 B4-3 관문 3 보강 B — 폴백 결과를 모르면 멈춘다(재발사 0).

`execute_sell` 은 `_handle_sell_market_disallowed` 가 돌려준 `SellFallbackOutcome` 으로
다음 동작을 정한다. `NO_PRICE`(현재가 미확보 — 폴백을 시도조차 못함)만 일반 재시도로
떨어지고, 그 밖의 값은 전부 `return` 이어야 한다.

이유(관문 2 domain-expert LOW) — 호출부가 「SENT·REJECTED 면 return, 나머지는 낙하」
꼴이면 메서드에 enum 이 아닌 경로(`None` — 분기 하나에서 `return` 을 빠뜨린 경우)나 새
enum 값이 생겼을 때 그 값이 **재시도 = 재발사** 쪽으로 떨어진다. 폴백 주문이 이미 나간
뒤라면 「주문이 나간 뒤의 실패로 재발사 금지」(cycle327)를 깬다. 모르는 값은 멈추는 쪽
(`_selling` 은 `selling_reconcile` 이 푼다)이 안전하다.

지금 메서드의 모든 경로는 enum 을 돌려주므로 실제 행위는 같다 — 이 파일은 그 기울기를
핀한다. 리그는 선행 그물 `test_cycle422_sell_fallback_net.py` 를 그대로 쓴다.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import SELL_MAX_RETRIES, SELL_RETRY_DELAY, SellFallbackOutcome
from src.models.order import OrderDivision
from tests.unit.engine.test_cycle422_sell_fallback_net import (
    _OE,
    _QTY,
    _T,
    _build,
    _disallowed,
    _recs,
    _sell,
)

pytestmark = pytest.mark.unit


class _NewOutcome:
    """enum 에 새 값이 생긴 경우의 대역 — `SellFallbackOutcome` 어느 멤버와도 `is` 가 아니다."""

    value = "future_value"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [None, "no_price", _NewOutcome()],
    ids=["none_missing_return", "raw_string_not_enum", "unknown_new_value"],
)
async def test_u01_unknown_fallback_outcome_when_returned_then_stop_without_refire(
    monkeypatch, caplog, outcome,
):
    """폴백 결과가 `NO_PRICE` 가 아니면(모르는 값 포함) — 재발사 0 · backoff 0 · 최종 실패 CRITICAL 0."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    handler = AsyncMock(return_value=outcome)
    monkeypatch.setattr(r.eng, "_handle_sell_market_disallowed", handler)
    r.place.side_effect = [_disallowed(), _disallowed(), _disallowed()]
    await _sell(r)

    assert handler.await_count == 1
    assert r.place.await_count == 1, "모르는 폴백 결과가 일반 재시도로 떨어져 다시 발사했다"
    assert r.aio.sleeps == []
    assert _recs(caplog, logging.WARNING, "매도 주문 실패 (시도 ") == []
    assert _recs(caplog, logging.CRITICAL) == []
    assert r.strat.state.positions[_T].quantity == _QTY


@pytest.mark.asyncio
async def test_u02_no_price_outcome_still_falls_through_to_plain_retry(monkeypatch, caplog):
    """대조 — `NO_PRICE` 는 지금처럼 일반 재시도(로그 + backoff)로 떨어진다(매도 의무 보존)."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    handler = AsyncMock(return_value=SellFallbackOutcome.NO_PRICE)
    monkeypatch.setattr(r.eng, "_handle_sell_market_disallowed", handler)
    r.place.side_effect = [_disallowed(), _disallowed(), _disallowed()]
    await _sell(r)

    assert handler.await_count == SELL_MAX_RETRIES
    assert r.place.await_count == SELL_MAX_RETRIES
    assert all(c.kwargs["order_division"] is OrderDivision.MARKET for c in r.place.await_args_list)
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    assert len(_recs(caplog, logging.WARNING, "매도 주문 실패 (시도 ")) == SELL_MAX_RETRIES
    assert len(_recs(caplog, logging.CRITICAL)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [SellFallbackOutcome.SENT, SellFallbackOutcome.REJECTED])
async def test_u03_known_terminal_outcomes_stop_without_refire(monkeypatch, outcome):
    """대조 — `SENT`·`REJECTED` 는 지금처럼 멈춘다."""
    r = _build(monkeypatch)
    handler = AsyncMock(return_value=outcome)
    monkeypatch.setattr(r.eng, "_handle_sell_market_disallowed", handler)
    r.place.side_effect = [_disallowed(), _disallowed(), _disallowed()]
    await _sell(r)

    assert handler.await_count == 1
    assert r.place.await_count == 1
    assert r.aio.sleeps == []
