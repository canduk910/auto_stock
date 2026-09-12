"""cycle285 — `system_config.get_task_last_success_bulk` 계약.

야간작업 현황 화면이 라벨 8개(+하트비트)를 폴링마다 개별 조회하면 쿼리가 는다.
`ANY($1)` 단일 왕복으로 묶는 헬퍼의 계약: (1) `task_last_success_` 접두 복원,
(2) JSONB `{"value": x}` dict 언랩, (3) 결측 라벨은 **키 자체가 없다**(빈 문자열
아님), (4) 쿼리 실패는 빈 dict(fail-open, 예외 전파 금지).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_bulk_unwraps_jsonb_and_strips_prefix():
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[
            {"key": "task_last_success_stock_master_daily_load",
             "value": {"value": "2026-09-14T20:32:00+09:00"}},
            {"key": "task_last_success_engine_alive_heartbeat",
             "value": {"value": "2026-09-14T18:00:00+09:00"}},
        ])
        result = await system_config.get_task_last_success_bulk(
            ["stock_master_daily_load", "engine_alive_heartbeat", "quote_token_refresh"]
        )

    assert result == {
        "stock_master_daily_load": "2026-09-14T20:32:00+09:00",
        "engine_alive_heartbeat": "2026-09-14T18:00:00+09:00",
    }
    # 마커가 없는 라벨은 키 자체가 없다 — "" 도 아니고 None 도 아니다.
    assert "quote_token_refresh" not in result


@pytest.mark.asyncio
async def test_bulk_queries_with_any_array_of_prefixed_keys():
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await system_config.get_task_last_success_bulk(["a", "b"])
        args = pg_mod.fetch.call_args.args
    assert "ANY($1" in args[0]
    assert args[1] == ["task_last_success_a", "task_last_success_b"]


@pytest.mark.asyncio
async def test_bulk_empty_labels_short_circuits_without_query():
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        result = await system_config.get_task_last_success_bulk([])
    assert result == {}
    pg_mod.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_query_failure_is_fail_open_empty_dict():
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("connection lost"))
        result = await system_config.get_task_last_success_bulk(["stock_master_daily_load"])
    assert result == {}


@pytest.mark.asyncio
async def test_bulk_tolerates_raw_scalar_value_not_dict():
    """codec 이 어떤 이유로 이미 언랩된 값을 준 경우도 문자열로 흡수한다."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[
            {"key": "task_last_success_stock_master_daily_load", "value": "2026-09-14T20:32:00+09:00"},
        ])
        result = await system_config.get_task_last_success_bulk(["stock_master_daily_load"])
    assert result == {"stock_master_daily_load": "2026-09-14T20:32:00+09:00"}
