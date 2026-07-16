"""asyncpg 기반 RDS(PostgreSQL) 연결 풀 + 쿼리 헬퍼 (사이클 M0, Supabase→RDS 이전 단계 0).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 0 인프라).

이 단계 = 순수 추가. 아직 어느 db 모듈도 본 모듈을 사용하지 않는다(`src/db/supabase.py`
병존). 매매 안전성 8영역 변경 0.

## 미러 대상 (정본)
- `src/db/supabase.py::execute_with_retry` (사이클187) — asyncpg 예외군으로 대체한 것이
  `_with_retry`. read 전용, write_log 미호출, 0.2s backoff.

## ⚠️ 최대 위험 (계획 3대 리스크 1순위)
asyncpg 는 JSONB 컬럼을 기본 `str` 로 반환한다. `_init_conn` 의 codec 등록이 누락되면
`system_config.get_cash_usage_ratio` 등 `isinstance(raw, dict)` 를 기대하는 코드가 전부
silent 폴백(기본값 강제)한다 — 매매 파라미터 오작동으로 직결. 신규 연결마다 반드시
`init=_init_conn` 을 통해 codec 이 등록되어야 한다.
"""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg

from src.config import settings

logger = logging.getLogger(__name__)

# 전역 커넥션 풀. init_pool() 로 채워지고 close_pool() 로 비워진다.
_pool: asyncpg.Pool | None = None

# _with_retry 재시도 대상 — 연결/타임아웃 계열만 (사이클187 _RETRY_EXCEPTIONS 미러).
_RETRY_EXCEPTIONS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncio.TimeoutError,
)

_RETRY_BACKOFF_SECS = 0.2


async def _init_conn(conn: asyncpg.Connection) -> None:
    """신규 연결마다 실행되는 초기화 훅 (asyncpg.create_pool(init=...)).

    JSONB/JSON codec 등록 — asyncpg 기본 str 반환을 dict 로 강제 변환(왕복 무손실).

    ⚠️ M2a 통합 검증 발견 (2026-07-16): KST 타임존은 여기서 세션 `SET TIME ZONE`으로
    설정하지 않는다 — asyncpg pool 은 커넥션을 release 할 때 세션 상태(SET 으로 바뀐
    파라미터)를 서버 기본값으로 리셋한다(`init=` 훅은 신규 *물리* 연결 최초 1회만
    실행되고, 이후 pool 재사용 시에는 재실행되지 않음). 그 결과 `min_size=2` 이상으로
    확보된 연결이 재사용될 때마다 timezone 이 `Etc/UTC` 로 되돌아가는 silent 결함을
    유발한다(trade_history 읽기 `to_char(...,'+09:00')` 가 UTC 기준으로 렌더링되어
    KST 날짜가 하루 밀리는 사고로 실증). `init_pool()` 의 `server_settings`(연결
    핸드셰이크 파라미터, pool 재사용과 무관하게 매 물리 연결에 영속) 로 이전.
    """
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def init_pool() -> None:
    """전역 연결 풀 생성. main.py lifespan 시작 시 1회 호출.

    KST 타임존은 `server_settings`(연결 핸드셰이크 파라미터)로 지정한다 — `init=`
    훅 내 `SET TIME ZONE`(세션 레벨)과 달리 pool 이 커넥션을 release/재획득해도
    유지된다(사이클 M2a 통합 검증 발견, `_init_conn` docstring 참조).
    """
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        max_inactive_connection_lifetime=300.0,
        command_timeout=30.0,
        init=_init_conn,
        server_settings={"timezone": "Asia/Seoul"},
    )


async def close_pool() -> None:
    """전역 연결 풀 종료. main.py lifespan 종료 시 1회 호출."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _with_retry(coro_factory, *, op: str = ""):
    """coro_factory() 를 연결 계열 예외에 한해 1회 재시도.

    `src/db/supabase.py::execute_with_retry` (사이클187) 의 asyncpg 대체. read 전용
    (fetch/fetchrow/fetchval) — 쓰기(execute/executemany)는 멱등 우려로 미경유.
    logger.warning 단독 — write_log 미호출(사이클72 이중 INSERT 차단).

    Args:
        coro_factory: 인자 없는 async callable. 매 시도마다 새로 호출.
        op: 로그 식별자.
    """
    retries = 1
    for attempt in range(retries + 1):
        try:
            return await coro_factory()
        except _RETRY_EXCEPTIONS as exc:
            if attempt >= retries:
                raise
            logger.warning(
                "[pg_retry] op=%s attempt=%d/%d exc=%s 재시도",
                op or "?", attempt + 1, retries + 1, type(exc).__name__,
            )
            await asyncio.sleep(_RETRY_BACKOFF_SECS)


async def fetch(sql: str, *args) -> list[dict]:
    """SELECT 다건 → list[dict] (supabase result.data 대응)."""
    async def _factory():
        async with _pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(r) for r in rows]

    return await _with_retry(_factory, op="fetch")


async def fetchrow(sql: str, *args) -> dict | None:
    """SELECT 1건 → dict | None (supabase result.data[0] 대응)."""
    async def _factory():
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row is not None else None

    return await _with_retry(_factory, op="fetchrow")


async def fetchval(sql: str, *args):
    """SELECT 스칼라 (supabase count="exact" 대응)."""
    async def _factory():
        async with _pool.acquire() as conn:
            return await conn.fetchval(sql, *args)

    return await _with_retry(_factory, op="fetchval")


async def execute(sql: str, *args) -> str:
    """쓰기(INSERT/UPDATE/DELETE) → asyncpg 상태 문자열. retry 미적용(멱등 우려)."""
    async with _pool.acquire() as conn:
        return await conn.execute(sql, *args)


async def executemany(sql: str, args_list) -> None:
    """배치 쓰기 (upsert_batch chunk 등). retry 미적용(멱등 우려)."""
    async with _pool.acquire() as conn:
        await conn.executemany(sql, args_list)
