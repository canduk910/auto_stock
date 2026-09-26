"""cycle369 Red — 킬스위치 2키 **실 Postgres** 왕복 + `jsonb_typeof`.

자매(단위) = `tests/unit/db/test_cycle369_status_mode_config.py`

- `set_status_exit_mode("off")` → `get_status_exit_mode_raw() == "off"` (JSONB codec 왕복)
- 저장 형태 = `{"value": "<mode>"}`, `jsonb_typeof(value->'value') == 'string'`
- 키 없음 → `None` (leaf 가 enforce 로 읽는다)

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_PAIRS = (
    ("set_status_exit_mode", "get_status_exit_mode_raw", "status_exit_mode"),
    ("set_status_buy_block_mode", "get_status_buy_block_mode_raw", "status_buy_block_mode"),
)


def _fns(setter, getter):
    from src.db import system_config

    s = getattr(system_config, setter, None)
    g = getattr(system_config, getter, None)
    assert s is not None and g is not None, f"[Red] system_config.{setter}/{getter} 미존재"
    return s, g


@pytest.mark.asyncio
@pytest.mark.parametrize("setter,getter,key", _PAIRS)
async def test_missing_key_reads_none(clean_system_config, setter, getter, key):
    _s, g = _fns(setter, getter)
    assert await g() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("setter,getter,key", _PAIRS)
@pytest.mark.parametrize("mode", ["enforce", "observe", "off"])
async def test_roundtrip_and_jsonb_shape(clean_system_config, pg_pool, setter, getter, key, mode):
    s, g = _fns(setter, getter)
    await s(mode)
    assert await g() == mode
    typ = await pg_pool.fetchval(
        "SELECT jsonb_typeof(value->'value') FROM system_config WHERE key = $1", key,
    )
    assert typ == "string"
