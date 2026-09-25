"""cycle363 F-4 — `stock_master.count_missing_kis_provenance_key()` 회귀 가드.

사용자 승인 결정 3(basics 자동 재실행)의 재료 함수. `count_active()`(cycle163)와
정반대 fail 방향이 계약이다 — `count_active` 는 예외 시 0 을 반환해 그 자체가
"행 수 하한 미달" 방향(RUN)으로 fail-safe 하지만, 이 함수의 안전 방향은 정반대다
(예외를 삼켜 0 을 반환하면 "결측 0건"으로 읽혀 SKIP 쪽으로 조용히 뒤집힌다). 그래서
이 함수는 **예외를 삼키지 않는다** — `task_loop_helper._evaluate_slot_gate` 의
force_check 예외 처리(`reason=force_check_error`, RUN)가 그 전파를 받아 흡수한다.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g363_f4_count_missing_returns_int():
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=124)
        cnt = await stock_master.count_missing_kis_provenance_key()

    assert cnt == 124
    sql = pg_mod.fetchval.await_args.args[0].lower()
    assert "count(" in sql and "stock_master" in sql and "cptt_trad_tr_psbl_yn" in sql


@pytest.mark.asyncio
async def test_g363_f4_none_result_is_zero():
    """`fetchval` 이 `None`(0건) 을 주면 0 — `int(None or 0)` graceful."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=None)
        cnt = await stock_master.count_missing_kis_provenance_key()

    assert cnt == 0


@pytest.mark.asyncio
async def test_g363_f4_query_failure_propagates_not_swallowed():
    """🔴 `count_active()` 와 정반대 — 예외를 0 으로 삼키면 안 된다(fail-safe 방향 반대)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=RuntimeError("pg ConnectionTerminated"))
        with pytest.raises(RuntimeError):
            await stock_master.count_missing_kis_provenance_key()
