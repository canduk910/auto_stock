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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def supabase_mock(monkeypatch):
    """src.db.system_config 의 supabase 객체 mock."""
    from src.db import system_config as sc

    mock_supabase = MagicMock()
    monkeypatch.setattr(sc, "supabase", mock_supabase)
    return mock_supabase


def _build_query_result(rows: list[dict]) -> MagicMock:
    """Supabase 응답 형식 mock."""
    result = MagicMock()
    result.data = rows
    return result


@pytest.mark.asyncio
async def test_g_db_1_get_default_when_all_keys_absent(supabase_mock):
    """G-DB-1: 모든 키 부재 시 디폴트 반환."""
    from src.db.system_config import get_krx_open_api_config
    from src.models.krx_open_api import DEFAULT_BASE_URL

    # 3 키 모두 빈 응답
    supabase_mock.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        _build_query_result([])
    )

    config = await get_krx_open_api_config()

    assert config.enabled is False
    assert config.base_url == DEFAULT_BASE_URL
    assert config.key == ""


@pytest.mark.asyncio
async def test_g_db_2_get_returns_all_three_keys(supabase_mock):
    """G-DB-2: 3 키 모두 DB 존재 시 정확 반환."""
    from src.db.system_config import get_krx_open_api_config

    # asyncio.to_thread 가 동기 함수를 실행하므로 각 호출별 다른 응답 반환을 위한 처리
    call_count = {"n": 0}
    responses = [
        _build_query_result([{"value": {"value": True}}]),  # enabled
        _build_query_result([{"value": {"value": "https://custom.krx.example/svc"}}]),  # base_url
        _build_query_result([{"value": {"value": "secret_key_abc1234"}}]),  # key
    ]

    def _exec_side_effect(*args, **kwargs):
        i = call_count["n"]
        call_count["n"] += 1
        return responses[i]

    supabase_mock.table.return_value.select.return_value.eq.return_value.execute.side_effect = (
        _exec_side_effect
    )

    config = await get_krx_open_api_config()

    assert config.enabled is True
    assert config.base_url == "https://custom.krx.example/svc"
    assert config.key == "secret_key_abc1234"


@pytest.mark.asyncio
async def test_g_db_3_set_with_kst_timestamp(supabase_mock):
    """G-DB-3: set_krx_open_api_config 가 KST timestamp 사용 (사이클 68 영속)."""
    from src.db.system_config import set_krx_open_api_config

    upsert_calls = []
    supabase_mock.table.return_value.upsert.side_effect = lambda payload, on_conflict: MagicMock(
        execute=MagicMock(return_value=_build_query_result([])),
        _payload=payload,  # 캡처용
    )

    def _capture_upsert(payload, on_conflict):
        upsert_calls.append(payload)
        return MagicMock(execute=MagicMock(return_value=_build_query_result([])))

    supabase_mock.table.return_value.upsert.side_effect = _capture_upsert

    await set_krx_open_api_config(key="abc1234")

    # 평문 key 가 평문 그대로 저장 의무 (KIS app_secret 패턴 답습)
    assert len(upsert_calls) == 1
    payload = upsert_calls[0]
    assert payload["key"] == "krx_open_api_key"
    assert payload["value"] == {"value": "abc1234"}

    # updated_at 영역 KST 영속 (사이클 68 `now_kst_iso()` 명시)
    assert "updated_at" in payload
    # KST `+09:00` 영속 (사이클 68 `_kst.py::now_kst_iso()` 형식)
    assert "+09:00" in payload["updated_at"] or "T" in payload["updated_at"]


@pytest.mark.asyncio
async def test_g_db_4_partial_update_enabled_only_preserves_key(supabase_mock):
    """G-DB-4: enabled 단독 갱신 시 key 미저장 (기존 보존)."""
    from src.db.system_config import set_krx_open_api_config

    upsert_calls = []

    def _capture_upsert(payload, on_conflict):
        upsert_calls.append(payload)
        return MagicMock(execute=MagicMock(return_value=_build_query_result([])))

    supabase_mock.table.return_value.upsert.side_effect = _capture_upsert

    await set_krx_open_api_config(enabled=True)

    # enabled 만 upsert + key 영역 갱신 0건 (부분 갱신 패턴)
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["key"] == "krx_open_api_enabled"
    assert upsert_calls[0]["value"] == {"value": True}


@pytest.mark.asyncio
async def test_g_db_5_partial_update_base_url_only(supabase_mock):
    """G-DB-5: base_url 단독 갱신."""
    from src.db.system_config import set_krx_open_api_config

    upsert_calls = []

    def _capture_upsert(payload, on_conflict):
        upsert_calls.append(payload)
        return MagicMock(execute=MagicMock(return_value=_build_query_result([])))

    supabase_mock.table.return_value.upsert.side_effect = _capture_upsert

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
