"""사이클 112 영역 1 (HIGH 6) — Supabase KRX OPEN API 키 관리 헬퍼.

Red 명세 (`_workspace/red/cycle112_krx_open_api_infra.md`):

G-DB-1~6 — `get_krx_open_api_config()` + `set_krx_open_api_config()` 영역.

위험 등급 HIGH (Supabase 평문 저장 + 응답 마스킹 영역 영구 차단).

영속 의무:
- 사이클 5 system_integrations 패턴 답습 (_set_bool / _get_bool_or_none)
- 사이클 7-A 마스킹 (사이클 7-A `kis_quote_accounts` 답습)
- 사이클 68 KST 영속 (`_kst.py::now_kst_iso()`)
- 사이클 89 한글 친숙 용어 영속
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# 사이클 M2a (2026-07-16) — system_config 가 supabase-py → src.db.pg(asyncpg) 전환.
# 기존 `.table().select().eq().execute()` 체인 mock → `fake_pg_kv`(conftest, key-value
# 인메모리 pg fake) 로 대체. round-trip 계약(get/set)은 동일 — mock 형상만 전환.


@pytest.fixture
def supabase_mock(monkeypatch, fake_pg_kv):
    """src.db.system_config 의 pg 객체를 fake_pg_kv 로 교체 (fixture 명칭은 하위 호환 보존)."""
    from src.db import system_config as sc

    monkeypatch.setattr(sc, "pg", fake_pg_kv)
    return fake_pg_kv


@pytest.mark.asyncio
async def test_g_db_1_get_default_when_all_keys_absent(supabase_mock):
    """G-DB-1: 모든 키 부재 시 디폴트 반환."""
    from src.db.system_config import get_krx_open_api_config
    from src.models.krx_open_api import DEFAULT_BASE_URL

    # fake_pg_kv 초기 상태 = 빈 store (3 키 모두 부재)
    config = await get_krx_open_api_config()

    assert config.enabled is False
    assert config.base_url == DEFAULT_BASE_URL
    assert config.key == ""


@pytest.mark.asyncio
async def test_g_db_2_get_returns_all_three_keys(supabase_mock):
    """G-DB-2: 3 키 모두 DB 존재 시 정확 반환."""
    from src.db.system_config import get_krx_open_api_config

    supabase_mock.store["krx_open_api_enabled"] = {"value": True}
    supabase_mock.store["krx_open_api_base_url"] = {"value": "https://custom.krx.example/svc"}
    supabase_mock.store["krx_open_api_key"] = {"value": "secret_key_abc1234"}

    config = await get_krx_open_api_config()

    assert config.enabled is True
    assert config.base_url == "https://custom.krx.example/svc"
    assert config.key == "secret_key_abc1234"


@pytest.mark.asyncio
async def test_g_db_3_set_with_kst_timestamp(supabase_mock, monkeypatch):
    """G-DB-3: set_krx_open_api_config 가 KST timestamp 사용 (사이클 68 영속)."""
    from src.db.system_config import set_krx_open_api_config

    upsert_calls: list[dict] = []
    orig_execute = supabase_mock.execute

    async def _capture_execute(sql, *args):
        # system_config._upsert_value 바인딩 = (key, value_dict, updated_at_datetime)
        upsert_calls.append({"key": args[0], "value": args[1], "updated_at": args[2]})
        return await orig_execute(sql, *args)

    monkeypatch.setattr(supabase_mock, "execute", _capture_execute)

    await set_krx_open_api_config(key="abc1234")

    # 평문 key 가 평문 그대로 저장 의무 (KIS app_secret 패턴 답습)
    assert len(upsert_calls) == 1
    payload = upsert_calls[0]
    assert payload["key"] == "krx_open_api_key"
    assert payload["value"] == {"value": "abc1234"}

    # updated_at 영역 KST 영속 (사이클 68 `now_kst_iso()` 명시) — datetime 바인딩(M1 패턴 2)
    assert payload["updated_at"] is not None
    assert payload["updated_at"].tzinfo is not None, "updated_at tz-aware datetime 계약."


@pytest.mark.asyncio
async def test_g_db_4_partial_update_enabled_only_preserves_key(supabase_mock, monkeypatch):
    """G-DB-4: enabled 단독 갱신 시 key 미저장 (기존 보존)."""
    from src.db.system_config import set_krx_open_api_config

    upsert_calls: list[dict] = []
    orig_execute = supabase_mock.execute

    async def _capture_execute(sql, *args):
        upsert_calls.append({"key": args[0], "value": args[1]})
        return await orig_execute(sql, *args)

    monkeypatch.setattr(supabase_mock, "execute", _capture_execute)

    await set_krx_open_api_config(enabled=True)

    # enabled 만 upsert + key 영역 갱신 0건 (부분 갱신 패턴)
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["key"] == "krx_open_api_enabled"
    assert upsert_calls[0]["value"] == {"value": True}


@pytest.mark.asyncio
async def test_g_db_5_partial_update_base_url_only(supabase_mock, monkeypatch):
    """G-DB-5: base_url 단독 갱신."""
    from src.db.system_config import set_krx_open_api_config

    upsert_calls: list[dict] = []
    orig_execute = supabase_mock.execute

    async def _capture_execute(sql, *args):
        upsert_calls.append({"key": args[0], "value": args[1]})
        return await orig_execute(sql, *args)

    monkeypatch.setattr(supabase_mock, "execute", _capture_execute)

    await set_krx_open_api_config(base_url="https://custom.krx.co.kr/svc")

    assert len(upsert_calls) == 1
    assert upsert_calls[0]["key"] == "krx_open_api_base_url"
    assert upsert_calls[0]["value"] == {"value": "https://custom.krx.co.kr/svc"}


def test_g_db_6_pydantic_model_fields_defined():
    """G-DB-6: KrxOpenApiConfig Pydantic 모델 3 필드 명확 정의."""
    from src.models.krx_open_api import KrxOpenApiConfig

    config = KrxOpenApiConfig(enabled=True, base_url="https://x.test", key="abc")
    assert config.enabled is True
    assert config.base_url == "https://x.test"
    assert config.key == "abc"

    # 디폴트 영역
    default = KrxOpenApiConfig()
    assert default.enabled is False
    assert default.base_url == "https://data-dbg.krx.co.kr/svc/apis"
    assert default.key == ""
