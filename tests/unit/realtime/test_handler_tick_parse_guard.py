from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.realtime import handler

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_handle_tick_invalid_price_payload_does_not_raise_or_dispatch():
    spy = AsyncMock()
    handler.register_tick_handler(spy)

    # fields[2] 현재가가 숫자가 아닌 운영 이상치 payload
    payload = "005930^090001^ABC^2^0^0^0^70000^71000^69000"
    await handler._handle_tick(payload)

    spy.assert_not_awaited()


def test_parse_tick_prices_returns_none_for_non_numeric_values():
    fields = ["005930", "090001", "ABC", "2", "0", "0", "0", "70000", "71000", "69000"]
    assert handler._parse_tick_prices(fields) is None


def test_parse_tick_prices_parses_current_and_open_price():
    fields = ["005930", "090001", "70100", "2", "0", "0", "0", "70000", "71000", "69000"]
    assert handler._parse_tick_prices(fields) == (70100, 70000)
