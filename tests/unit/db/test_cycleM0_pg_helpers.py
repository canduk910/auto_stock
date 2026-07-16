"""사이클 M0 (Red) — src/db/pg.py asyncpg 풀 + 쿼리 헬퍼 단위 회귀 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 0 인프라).

이 단계 = 어느 db 모듈도 pg 미사용 = 행위 변화 0. supabase.py 병존, 순수 추가.

Red 유효성: 현재 `src/db/pg.py` 미존재 → 전 테스트 import 단계 FAIL.
Green 후 PASS.

계약 (supabase-py `.execute()` 4형태 대응 = 반환형이 계약):
- fetch(sql, *args) -> list[dict]      (SELECT 다건 → [dict(r) for r in rows], result.data)
- fetchrow(sql, *args) -> dict | None  (1건)
- fetchval(sql, *args)                 (스칼라, count="exact" 대응)
- execute(sql, *args) -> str           (쓰기, "UPDATE 3" 상태문자열; retry 미적용)
- executemany(sql, args_list) -> None  (upsert_batch chunk)

`init_pool` = asyncpg.create_pool(min_size=2, max_size=10,
max_inactive_connection_lifetime=300.0, command_timeout=30.0, init=_init_conn).

`_with_retry(coro_factory, *, op="")` = execute_with_retry(사이클187) asyncpg 대체 —
asyncpg 연결 예외군 재시도, read 전용, write_log 미호출(logger.warning 단독), 0.2s backoff.

테스트 격리:
- 실 DB 불요. asyncpg.create_pool 을 patch(AsyncMock). conn/pool 은 AsyncMock.
- asyncio.sleep 전역 patch (retry backoff 실지연 0).
- pg import 는 각 테스트 lazy (Red ImportError = 깔끔한 FAIL).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def no_sleep():
    """asyncio.sleep 무력화 — retry backoff 실지연 0."""
    with patch("asyncio.sleep", new_callable=AsyncMock) as m:
        yield m


def _make_pool_with_conn(conn):
    """pool.acquire() async context manager 가 conn 을 내주는 AsyncMock pool.

    asyncpg pool 은 `async with pool.acquire() as conn:` 패턴.
    """
    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool


# ---------------------------------------------------------------------------
# init_pool — create_pool 인자 (min2/max10/max_inactive300/command_timeout30/init)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_init_pool_create_pool_args():
    """init_pool 이 asyncpg.create_pool 을 규정된 인자로 호출."""
    import src.db.pg as pg

    fake_pool = MagicMock()
    with patch("asyncpg.create_pool", new=AsyncMock(return_value=fake_pool)) as cp:
        await pg.init_pool()

    assert cp.await_count == 1, "init_pool 이 create_pool 을 1회 호출해야 함."
    _, kwargs = cp.call_args
    assert kwargs.get("min_size") == 2, "min_size=2 규정 위반."
    assert kwargs.get("max_size") == 10, "max_size=10 규정 위반."
    assert kwargs.get("max_inactive_connection_lifetime") == 300.0, (
        "max_inactive_connection_lifetime=300.0 (stale 연결 능동 폐기, 사이클187 crash 방어)."
    )
    assert kwargs.get("command_timeout") == 30.0, "command_timeout=30.0 규정 위반."
    assert kwargs.get("init") is pg._init_conn, (
        "init=_init_conn 미전달 — JSONB codec/TZ 설정이 신규 연결마다 적용 안 됨(silent 결함)."
    )
    # dsn 은 settings.database_url 경유
    assert "dsn" in kwargs, "create_pool 이 dsn 키워드로 database_url 전달해야 함."


@pytest.mark.asyncio
async def test_close_pool_closes_and_clears():
    """close_pool 이 전역 _pool.close() 호출 + 전역 초기화."""
    import src.db.pg as pg

    fake_pool = MagicMock()
    fake_pool.close = AsyncMock()
    with patch("asyncpg.create_pool", new=AsyncMock(return_value=fake_pool)):
        await pg.init_pool()
    await pg.close_pool()

    assert fake_pool.close.await_count == 1, "close_pool 이 pool.close() 호출해야 함."


# ---------------------------------------------------------------------------
# fetch — list[dict] (dict(record) 변환)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_returns_list_of_dict(no_sleep):
    """fetch → list[dict] — asyncpg Record 를 dict 로 변환 (result.data 대응)."""
    import src.db.pg as pg

    # asyncpg Record 는 dict(record) 가능. dict 자체로 흉내 (dict(d) == d).
    records = [{"ticker": "005930", "qty": 10}, {"ticker": "000660", "qty": 5}]
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=records)
    pool = _make_pool_with_conn(conn)

    with patch.object(pg, "_pool", pool):
        out = await pg.fetch("SELECT * FROM positions WHERE qty > $1", 0)

    assert isinstance(out, list), "fetch 반환형은 list."
    assert all(isinstance(r, dict) for r in out), "각 원소는 dict (dict(record) 변환)."
    assert out == records, "행 내용 보존."
    conn.fetch.assert_awaited_once_with(
        "SELECT * FROM positions WHERE qty > $1", 0
    )


@pytest.mark.asyncio
async def test_fetch_empty_returns_empty_list(no_sleep):
    """fetch 0건 → [] (result.data 빈 배열 대응, graceful)."""
    import src.db.pg as pg

    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    pool = _make_pool_with_conn(conn)

    with patch.object(pg, "_pool", pool):
        out = await pg.fetch("SELECT 1 WHERE false")

    assert out == [], "0건 → 빈 리스트."


# ---------------------------------------------------------------------------
# fetchrow — dict | None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetchrow_returns_dict(no_sleep):
    """fetchrow 1건 → dict (result.data[0] if ... 대응)."""
    import src.db.pg as pg

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"ticker": "005930", "qty": 10})
    pool = _make_pool_with_conn(conn)

    with patch.object(pg, "_pool", pool):
        out = await pg.fetchrow("SELECT * FROM positions WHERE ticker = $1", "005930")

    assert isinstance(out, dict), "fetchrow 1건 → dict."
    assert out["ticker"] == "005930"


@pytest.mark.asyncio
async def test_fetchrow_none_returns_none(no_sleep):
    """fetchrow miss → None (dict|None 계약)."""
    import src.db.pg as pg

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = _make_pool_with_conn(conn)

    with patch.object(pg, "_pool", pool):
        out = await pg.fetchrow("SELECT * FROM positions WHERE ticker = $1", "ZZZ")

    assert out is None, "miss → None."


# ---------------------------------------------------------------------------
# fetchval — 스칼라 (count="exact" 대응)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetchval_returns_scalar(no_sleep):
    """fetchval → 스칼라 (SELECT count(*) → int, result.count 대응)."""
    import src.db.pg as pg

    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=42)
    pool = _make_pool_with_conn(conn)

    with patch.object(pg, "_pool", pool):
        out = await pg.fetchval("SELECT count(*) FROM trade_history")

    assert out == 42, "스칼라 값 그대로 반환."


# ---------------------------------------------------------------------------
# execute — str (쓰기, "UPDATE 3" 상태문자열, retry 미적용)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_returns_status_string():
    """execute → 상태문자열 (쓰기). retry 미경유 = 멱등 우려."""
    import src.db.pg as pg

    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 3")
    pool = _make_pool_with_conn(conn)

    with patch.object(pg, "_pool", pool):
        out = await pg.execute("UPDATE positions SET qty = 0 WHERE ticker = $1", "005930")

    assert out == "UPDATE 3", "asyncpg 상태문자열 그대로 반환."
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_executemany_returns_none():
    """executemany → None (upsert_batch chunk)."""
    import src.db.pg as pg

    conn = MagicMock()
    conn.executemany = AsyncMock(return_value=None)
    pool = _make_pool_with_conn(conn)

    args_list = [("005930", 10), ("000660", 5)]
    with patch.object(pg, "_pool", pool):
        out = await pg.executemany(
            "INSERT INTO positions (ticker, qty) VALUES ($1, $2)", args_list
        )

    assert out is None
    conn.executemany.assert_awaited_once_with(
        "INSERT INTO positions (ticker, qty) VALUES ($1, $2)", args_list
    )


# ---------------------------------------------------------------------------
# _with_retry — asyncpg 연결 예외군 재시도 (execute_with_retry 사이클187 대체)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_with_retry_retries_on_connection_error(no_sleep):
    """asyncpg 연결 예외 1회 후 2차 정상 → 결과 반환 (coro_factory 2회)."""
    import asyncpg

    import src.db.pg as pg

    call_count = {"n": 0}

    async def _factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise asyncpg.InterfaceError("connection lost")
        return "ok"

    out = await pg._with_retry(_factory, op="test")

    assert out == "ok", "2차 정상 → 결과 반환."
    assert call_count["n"] == 2, "connection 예외 1회 → 2회 호출."
    assert no_sleep.await_count >= 1, "재시도 사이 backoff sleep 발화."


@pytest.mark.asyncio
async def test_with_retry_raises_after_exhaust(no_sleep):
    """재시도 소진 시 마지막 예외 raise (호출자 graceful except 보존)."""
    import asyncpg

    import src.db.pg as pg

    async def _factory():
        raise asyncpg.PostgresConnectionError("down")

    with pytest.raises(asyncpg.PostgresConnectionError):
        await pg._with_retry(_factory, op="test")


@pytest.mark.asyncio
async def test_with_retry_non_connection_error_propagates(no_sleep):
    """비-연결 예외(ValueError 등)는 즉시 전파 (재시도 0)."""
    import src.db.pg as pg

    call_count = {"n": 0}

    async def _factory():
        call_count["n"] += 1
        raise ValueError("bad sql")

    with pytest.raises(ValueError):
        await pg._with_retry(_factory, op="test")

    assert call_count["n"] == 1, "비-연결 예외는 재시도 없이 1회만."


@pytest.mark.asyncio
async def test_with_retry_timeout_error_retried(no_sleep):
    """asyncio.TimeoutError 도 연결 예외군에 포함 → 재시도."""
    import asyncio as _asyncio

    import src.db.pg as pg

    call_count = {"n": 0}

    async def _factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _asyncio.TimeoutError()
        return "recovered"

    out = await pg._with_retry(_factory, op="test")
    assert out == "recovered"
    assert call_count["n"] == 2, "TimeoutError → 재시도."
