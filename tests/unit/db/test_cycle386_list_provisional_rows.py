"""cycle386 Red — `stock_master_daily.list_provisional_rows(*, since, head, today_boundary)` 단위 계약.

조건 자체(경계·시간대)는 실 Postgres 로 `tests/integration/test_cycle386_provisional_predicate_pg.py` 가 잰다.
여기서는 모양만 — 키워드 전용 · 읽기 전용 · 예외 전파.

🔴 **예외를 삼키지 않는다** — 이 모듈의 다른 읽기 헬퍼(`get_recent_daily` 등)는 실패 시 빈 목록을 돌려주지만,
이 함수가 그렇게 하면 「대상 조회 실패」가 「고칠 것 없음(noop, INFO)」으로 둔갑한다. 설계 §8-6 은 그 경우를
`result=error stage=select` WARNING 으로 요구한다(`system_config.get_status_exit_mode_raw` E8 선례와 같은 방향).

## HEAD 기준
함수 부재로 전부 RED.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_ARGS = dict(since=date(2026, 9, 7), head=date(2026, 9, 25),
             today_boundary=datetime(2026, 9, 28, 6, 0, tzinfo=KST))


def test_l1_signature_is_keyword_only():
    from src.db import stock_master_daily as smd

    sig = inspect.signature(smd.list_provisional_rows)
    params = sig.parameters
    assert set(params) == {"since", "head", "today_boundary"}, f"인자 = since · head · today_boundary — {list(params)}"
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values()), "키워드 전용이어야 한다"
    assert inspect.iscoroutinefunction(smd.list_provisional_rows)


@pytest.mark.asyncio
async def test_l2_reads_once_with_the_three_values_and_returns_dicts(monkeypatch):
    import src.db.pg as pg
    from src.db import stock_master_daily as smd

    calls: list[tuple[str, tuple]] = []

    async def _fetch(sql, *args):
        calls.append((sql, args))
        return [{"ticker": "394800", "bas_dd": date(2026, 9, 23), "open_price": 5700, "high_price": 6100,
                 "low_price": 5280, "close_price": 5520}]

    async def _no_write(*_a, **_k):
        raise AssertionError("대상 조회가 쓰기를 했다")

    monkeypatch.setattr(pg, "fetch", _fetch)
    monkeypatch.setattr(pg, "execute", _no_write)
    monkeypatch.setattr(pg, "executemany", _no_write)

    rows = await smd.list_provisional_rows(**_ARGS)

    assert len(calls) == 1
    sql, args = calls[0]
    assert "stock_master_daily" in sql and "updated_at" in sql
    for v in _ARGS.values():
        assert v in args, f"{v!r} 가 바인딩 인자에 없다 — 문자열 보간은 금지(asyncpg 바인딩)"
    assert rows == [{"ticker": "394800", "bas_dd": date(2026, 9, 23), "open_price": 5700,
                     "high_price": 6100, "low_price": 5280, "close_price": 5520}]


@pytest.mark.asyncio
async def test_l3_db_failure_propagates(monkeypatch):
    import src.db.pg as pg
    from src.db import stock_master_daily as smd

    async def _boom(*_a, **_k):
        raise ConnectionError("pg down")

    monkeypatch.setattr(pg, "fetch", _boom)

    with pytest.raises(ConnectionError):
        await smd.list_provisional_rows(**_ARGS)
