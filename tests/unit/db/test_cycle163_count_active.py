"""사이클 163 (2026-06-18) — stock_master.count_active() 신규 회귀 가드.

의제 #5 영역 — _boot prepare 호출 *전* 가드 헬퍼.
사이클 128 count="exact" 패턴 답습 (PostgREST 1000행 silent cap 회피).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_G163_COUNT_1_count_active_returns_int():
    """G-163-COUNT-1: count_active() 정상 응답 = result.count 반환.

    Supabase mock = count=2768 → 함수 반환 2768.
    """
    from src.db import stock_master

    mock_result = MagicMock()
    mock_result.count = 2768

    with patch.object(stock_master, "supabase") as mock_sb:
        chain = (
            mock_sb.table.return_value
            .select.return_value
            .limit.return_value
        )
        chain.execute.return_value = mock_result

        cnt = await stock_master.count_active()

    assert cnt == 2768
    # count="exact" 의무 검증
    select_call = mock_sb.table.return_value.select.call_args
    assert select_call.kwargs.get("count") == "exact"


@pytest.mark.asyncio
async def test_G163_COUNT_2_count_active_exception_returns_zero():
    """G-163-COUNT-2: count_active() Supabase 예외 → 0 폴백 graceful.

    사이클 88 G-REJECT graceful 영속 답습.
    """
    from src.db import stock_master

    with patch.object(stock_master, "supabase") as mock_sb:
        mock_sb.table.side_effect = RuntimeError("supabase HTTP/2 ConnectionTerminated")

        cnt = await stock_master.count_active()

    assert cnt == 0
