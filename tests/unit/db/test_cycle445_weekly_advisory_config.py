"""cycle445 D8 — `system_config.get_weekly_advisory_weekday_raw()` (키 `weekly_advisory_weekday`).

`status_exit_mode` 와 같은 규약 (`src/db/CLAUDE.md` 「종목상태 킬스위치 2키」) — 키 없음 =
`None`, 모양이 틀린 값(값 없는 dict·JSONB null·숫자·목록)은 어휘 밖 마커 문자열
(`_MALFORMED_MARKER`), **DB 조회 예외는 전파**한다(leaf `weekly_advisory.py` 가
"키 없음"과 "DB 장애"를 같게 다루되, 그 처리는 leaf 쪽 책임이지 이 getter 가 삼키면 안
된다 — 삼키면 `normalize_weekday` 가 둘을 구분할 길이 사라진다).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _fn(name):
    from src.db import system_config as sc

    fn = getattr(sc, name, None)
    assert fn is not None, f"system_config.{name} 미존재"
    return fn


@pytest.fixture
def fake_pg(monkeypatch):
    import src.db.pg as pg

    state = {"rows": {}, "fetch_calls": [], "raise": None}

    async def _fetch(sql, *args):
        state["fetch_calls"].append((sql, args))
        if state["raise"] is not None:
            raise state["raise"]
        key = args[0] if args else None
        v = state["rows"].get(key)
        return [] if key not in state["rows"] else [{"value": v}]

    monkeypatch.setattr(pg, "fetch", _fetch)
    return state


async def test_missing_key_is_none(fake_pg):
    got = await _fn("get_weekly_advisory_weekday_raw")()
    assert got is None
    assert fake_pg["fetch_calls"][0][1] == ("weekly_advisory_weekday",)


async def test_returns_stored_string(fake_pg):
    fake_pg["rows"]["weekly_advisory_weekday"] = {"value": "mon"}
    got = await _fn("get_weekly_advisory_weekday_raw")()
    assert got == "mon"


async def test_malformed_value_is_marker_not_none(fake_pg):
    """값 없는 dict·JSONB null 은 「키 없음」과 다르다 — 어휘 밖 마커를 돌려준다."""
    fake_pg["rows"]["weekly_advisory_weekday"] = {"value": None}
    got = await _fn("get_weekly_advisory_weekday_raw")()
    assert got is not None and got != "mon"


async def test_db_exception_propagates(fake_pg):
    fake_pg["raise"] = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await _fn("get_weekly_advisory_weekday_raw")()
