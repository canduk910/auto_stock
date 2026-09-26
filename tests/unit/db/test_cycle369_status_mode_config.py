"""cycle369 Red — `system_config` 킬스위치 키 2개 (명세 §5).

| 함수 | 계약 |
|---|---|
| `get_status_exit_mode_raw()` | 키 없음 → `None` · `{"value": str}` → `str` · **DB 예외는 전파**(E8) |
| `get_status_buy_block_mode_raw()` | 〃 |
| `set_status_exit_mode(mode)` · `set_status_buy_block_mode(mode)` | JSONB `{"value": mode}` upsert. 어휘 검증은 라우트 |

🔴 getter 가 `_get_string_or_none` 을 쓰면 안 되는 이유 — 그 헬퍼는 DB 예외를 `None` 으로
삼킨다. 그러면 leaf 가 「키 없음 = enforce」 와 「DB 장애 = 직전 값 유지」 를 구분하지 못해
**장애가 운영자의 `off` 를 조용히 enforce 로 되돌린다**.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_KEYS = {
    "sell": ("get_status_exit_mode_raw", "set_status_exit_mode", "status_exit_mode"),
    "buy": ("get_status_buy_block_mode_raw", "set_status_buy_block_mode", "status_buy_block_mode"),
}


def _fn(name):
    from src.db import system_config as sc

    fn = getattr(sc, name, None)
    assert fn is not None, f"[Red] system_config.{name} 미존재"
    return fn


@pytest.fixture
def fake_pg(monkeypatch):
    import src.db.pg as pg

    state = {"rows": {}, "fetch_calls": [], "exec_calls": [], "raise": None}

    async def _fetch(sql, *args):
        state["fetch_calls"].append((sql, args))
        if state["raise"] is not None:
            raise state["raise"]
        key = args[0] if args else None
        v = state["rows"].get(key)
        return [] if v is None else [{"value": v}]

    async def _execute(sql, *args):
        state["exec_calls"].append((sql, args))
        return "INSERT 0 1"

    monkeypatch.setattr(pg, "fetch", _fetch)
    monkeypatch.setattr(pg, "execute", _execute)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["sell", "buy"])
async def test_getter_missing_key_is_none(fake_pg, axis):
    getter, _setter, key = _KEYS[axis]
    assert await _fn(getter)() is None
    assert fake_pg["fetch_calls"] and fake_pg["fetch_calls"][0][1] == (key,)


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["sell", "buy"])
async def test_getter_returns_stored_string(fake_pg, axis):
    getter, _setter, key = _KEYS[axis]
    fake_pg["rows"][key] = {"value": "observe"}
    assert await _fn(getter)() == "observe"


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["sell", "buy"])
async def test_e8_getter_propagates_db_errors(fake_pg, axis):
    getter, _setter, _key = _KEYS[axis]
    fake_pg["raise"] = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await _fn(getter)()


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["sell", "buy"])
async def test_setter_upserts_value_json(fake_pg, axis):
    _getter, setter, key = _KEYS[axis]
    await _fn(setter)("off")
    assert len(fake_pg["exec_calls"]) == 1
    _sql, args = fake_pg["exec_calls"][0]
    assert args[0] == key
    assert args[1] == {"value": "off"}
