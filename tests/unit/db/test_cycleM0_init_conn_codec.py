"""사이클 M0 (Red) — src/db/pg.py `_init_conn` JSONB/JSON codec 등록 회귀 가드.

⚠️ **이 이전 전체의 최대 위험** (계획 3대 리스크 1순위):
asyncpg 는 JSONB 를 기본 `str` 반환 → codec 미등록 시 `system_config.get_cash_usage_ratio`
등이 `isinstance(raw, dict)` False 로 **전 설정 silent 폴백** (cash_usage_ratio=1.0 강제 등
매매 파라미터 오작동). 따라서 codec 등록을 반드시 단언.

`_init_conn(conn)` 3설정:
1. JSONB codec: conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
   schema="pg_catalog")
2. JSON codec: 동일 "json"
3. conn.execute("SET TIME ZONE 'Asia/Seoul'")

Red 유효성: 현재 `src/db/pg.py` 미존재 → import FAIL.
Green 후 PASS.

테스트 격리: 실 DB 불요. conn 은 AsyncMock — set_type_codec/execute 호출 인자 단언.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, call

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_init_conn_registers_jsonb_and_json_codec():
    """_init_conn 이 jsonb + json codec 을 각각 등록 (set_type_codec 2회).

    ⚠️ 미등록 시 JSONB→str silent 폴백 = 매매 파라미터 오작동. 최우선 가드.
    """
    import src.db.pg as pg

    conn = AsyncMock()

    await pg._init_conn(conn)

    # set_type_codec 최소 2회 (jsonb + json)
    assert conn.set_type_codec.await_count >= 2, (
        "_init_conn 이 jsonb + json codec 을 각각 등록해야 함 (set_type_codec ≥ 2회). "
        "미등록 시 asyncpg JSONB→str → dict 기대 코드 전 설정 silent 폴백."
    )

    # 등록된 type 이름 집합
    registered_types = set()
    for c in conn.set_type_codec.await_args_list:
        pos_args, kw_args = c
        type_name = pos_args[0] if pos_args else kw_args.get("type_name") or kw_args.get("typename")
        registered_types.add(type_name)

    assert "jsonb" in registered_types, "jsonb codec 미등록 (최대 위험)."
    assert "json" in registered_types, "json codec 미등록."


@pytest.mark.asyncio
async def test_init_conn_codec_uses_json_dumps_loads():
    """codec encoder/decoder 가 json.dumps / json.loads (dict↔JSONB 왕복 보장)."""
    import src.db.pg as pg

    conn = AsyncMock()
    await pg._init_conn(conn)

    for c in conn.set_type_codec.await_args_list:
        pos_args, kw_args = c
        type_name = pos_args[0] if pos_args else kw_args.get("type_name") or kw_args.get("typename")
        if type_name not in ("jsonb", "json"):
            continue
        encoder = kw_args.get("encoder")
        decoder = kw_args.get("decoder")
        assert encoder is json.dumps, (
            f"{type_name} codec encoder 는 json.dumps 여야 함 (dict → JSONB 텍스트)."
        )
        assert decoder is json.loads, (
            f"{type_name} codec decoder 는 json.loads 여야 함 (JSONB → dict, silent 폴백 방지)."
        )


@pytest.mark.asyncio
async def test_init_conn_codec_schema_pg_catalog():
    """codec schema='pg_catalog' (asyncpg 내장 jsonb/json 타입 위치)."""
    import src.db.pg as pg

    conn = AsyncMock()
    await pg._init_conn(conn)

    for c in conn.set_type_codec.await_args_list:
        pos_args, kw_args = c
        type_name = pos_args[0] if pos_args else kw_args.get("type_name") or kw_args.get("typename")
        if type_name not in ("jsonb", "json"):
            continue
        assert kw_args.get("schema") == "pg_catalog", (
            f"{type_name} codec schema 는 'pg_catalog' 여야 함."
        )


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason=(
        "사이클 M2a (2026-07-16) 발견 — asyncpg pool 은 커넥션 release/재획득 시 "
        "세션 레벨 SET(SET TIME ZONE)을 서버 기본값으로 리셋한다(`init=` 훅은 신규 "
        "*물리* 연결 최초 1회만 실행되고 이후 재사용 시 재실행되지 않음). 통합 검증 "
        "(trade_history KST +09:00 왕복)에서 min_size=2 이상 풀의 재사용 커넥션이 "
        "Etc/UTC 로 되돌아가는 실사고로 확인 — `_init_conn` 의 `SET TIME ZONE` 을 "
        "`init_pool()` 의 `server_settings={'timezone': 'Asia/Seoul'}` (연결 핸드셰이크"
        "파라미터, pool 재사용과 무관하게 매 물리 연결에 영속)로 이전. 대체 계약 = "
        "test_init_pool_uses_asia_seoul_server_settings."
    ),
    strict=False,
)
async def test_init_conn_sets_kst_timezone():
    """_init_conn 이 SET TIME ZONE 'Asia/Seoul' 실행 (KST 정합, 사이클69 TIMESTAMPTZ).

    사이클 M2a 전환 후 — KST 타임존은 `init_pool()` 의 `server_settings` 로 이전
    (pool 재사용 시 세션 리셋 결함 회피). `_init_conn` 은 codec 등록만 담당.
    """
    import src.db.pg as pg

    conn = AsyncMock()
    await pg._init_conn(conn)

    tz_calls = [
        c for c in conn.execute.await_args_list
        if c.args and "TIME ZONE" in str(c.args[0]) and "Asia/Seoul" in str(c.args[0])
    ]
    assert tz_calls, (
        "_init_conn 이 conn.execute(\"SET TIME ZONE 'Asia/Seoul'\") 호출해야 함 "
        "(now() DEFAULT·표시 KST 정합)."
    )


def test_init_pool_uses_asia_seoul_server_settings():
    """init_pool() 이 create_pool 호출 시 server_settings={'timezone': 'Asia/Seoul'} 전달.

    사이클 M2a — pool 재사용 커넥션의 timezone 리셋 결함(위 xfail 참조)을
    `init=` 세션 SET 대신 연결 핸드셰이크 파라미터로 우회하는 정본 계약.
    """
    import inspect

    import src.db.pg as pg

    src = inspect.getsource(pg.init_pool)
    assert "server_settings" in src, (
        "init_pool() 이 asyncpg.create_pool(server_settings=...) 을 전달해야 함 "
        "(pool 재사용 시 세션 TIME ZONE 리셋 결함 회피)."
    )
    assert "Asia/Seoul" in src, "server_settings 값에 'Asia/Seoul' 명시 누락."


@pytest.mark.asyncio
async def test_init_conn_dict_roundtrip_via_codec():
    """codec encoder/decoder 왕복 = dict → str → dict 무손실 (계약 실증)."""
    import src.db.pg as pg

    conn = AsyncMock()
    await pg._init_conn(conn)

    sample = {"value": 0.35, "nested": {"a": [1, 2]}}
    for c in conn.set_type_codec.await_args_list:
        pos_args, kw_args = c
        type_name = pos_args[0] if pos_args else kw_args.get("type_name") or kw_args.get("typename")
        if type_name != "jsonb":
            continue
        encoder = kw_args.get("encoder")
        decoder = kw_args.get("decoder")
        assert decoder(encoder(sample)) == sample, (
            "jsonb codec 왕복 무손실 실패 — dict 기대 코드 silent 폴백 위험."
        )
        break
    else:
        pytest.fail("jsonb codec 미등록 — 왕복 검증 불가.")
