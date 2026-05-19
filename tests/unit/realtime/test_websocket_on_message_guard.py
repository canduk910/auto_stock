from __future__ import annotations

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_handle_raw_on_message_exception_is_swallowed():
    ws = KisWebSocket()

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    ws._on_message = _boom

    # 예외가 외부로 전파되지 않아 receive loop가 끊기지 않아야 함
    await ws._handle_raw("0|H0UNCNT0|001|005930^090001^70000^2^0^0^0^70000^71000^69000")

