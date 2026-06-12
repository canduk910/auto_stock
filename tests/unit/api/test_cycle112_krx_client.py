"""사이클 112 영역 3 (HIGH 5) — `src/api/krx.py` 클라이언트 추상.

Red 명세 (`_workspace/red/cycle112_krx_open_api_infra.md`):

G-AP-1~5 — KrxApiError + fetch_krx_open_api Supabase 동적 키 로드 + AUTH_KEY header + graceful.

위험 등급 HIGH (사이클 88 G-REJECT graceful 영속 + 사이클 110 호출 사이트 0건 영속).

영속 의무:
- 사이클 88 G-REJECT 영속 (graceful = 호출자 폴백 의무)
- 사이클 17 OPSP0002 backoff 영역 패턴 (KIS 와 별개 시스템이나 안전 의무 동일)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

pytestmark = pytest.mark.unit


def test_g_ap_1_krx_api_error_defined():
    """G-AP-1: KrxApiError 예외 클래스 정의 + import 가능."""
    from src.api.krx import KrxApiError

    assert issubclass(KrxApiError, Exception)

    # raise 동작 확인
    with pytest.raises(KrxApiError, match="test"):
        raise KrxApiError("test")


@pytest.mark.asyncio
async def test_g_ap_2_dynamic_key_load_from_supabase(monkeypatch):
    """G-AP-2: fetch_krx_open_api 가 Supabase 에서 동적 키 로드."""
    from src.api import krx as krx_mod
    from src.models.krx_open_api import KrxOpenApiConfig

    config_used = []

    async def _fake_get():
        config = KrxOpenApiConfig(
            enabled=True,
            base_url="https://data-dbg.krx.co.kr/svc/apis",
            key="dynamic_key_5678",
        )
        config_used.append(config)
        return config

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_get
    )

    # httpx AsyncClient mock
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"OutBlock_1": []})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        result = await krx_mod.fetch_krx_open_api(
            "/sto/stk_bydd_trd", {"basDd": "20260612"}
        )

    # Supabase 호출 검증
    assert len(config_used) == 1
    assert config_used[0].key == "dynamic_key_5678"

    # 응답 반환
    assert result == {"OutBlock_1": []}


@pytest.mark.asyncio
async def test_g_ap_3_raise_when_disabled_or_missing_key(monkeypatch):
    """G-AP-3: enabled=False 또는 key 부재 시 KrxApiError raise (사이클 88 G-REJECT graceful)."""
    from src.api import krx as krx_mod
    from src.api.krx import KrxApiError
    from src.models.krx_open_api import KrxOpenApiConfig

    # enabled=False
    async def _fake_disabled():
        return KrxOpenApiConfig(enabled=False, key="some_key")

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_disabled
    )
    with pytest.raises(KrxApiError, match="비활성"):
        await krx_mod.fetch_krx_open_api("/sto/stk_bydd_trd", {})

    # key 부재
    async def _fake_no_key():
        return KrxOpenApiConfig(enabled=True, key="")

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_no_key
    )
    with pytest.raises(KrxApiError, match="key 부재"):
        await krx_mod.fetch_krx_open_api("/sto/stk_bydd_trd", {})


@pytest.mark.asyncio
async def test_g_ap_4_auth_key_header_and_json_post(monkeypatch):
    """G-AP-4: httpx POST + AUTH_KEY header + Content-Type: application/json 전송."""
    from src.api import krx as krx_mod
    from src.models.krx_open_api import KrxOpenApiConfig

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=True,
            base_url="https://data-dbg.krx.co.kr/svc/apis",
            key="header_test_key_1234",
        )

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_get
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"OutBlock_1": [{"ISU_CD": "005930"}]})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    post_calls = []

    async def _capture_post(url, headers=None, json=None):
        post_calls.append({"url": url, "headers": headers, "json": json})
        return mock_response

    mock_client.post = _capture_post

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        await krx_mod.fetch_krx_open_api("/sto/stk_bydd_trd", {"basDd": "20260612"})

    assert len(post_calls) == 1
    call = post_calls[0]
    assert call["url"] == "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
    # AUTH_KEY header 사용 (Bearer token 영역 아님)
    assert call["headers"]["AUTH_KEY"] == "header_test_key_1234"
    assert call["headers"]["Content-Type"] == "application/json"
    # JSON body
    assert call["json"] == {"basDd": "20260612"}


@pytest.mark.asyncio
async def test_g_ap_5_httpx_exception_converted_to_krx_api_error(monkeypatch):
    """G-AP-5: httpx 네트워크/timeout 예외 → KrxApiError 변환 raise (graceful)."""
    from src.api import krx as krx_mod
    from src.api.krx import KrxApiError
    from src.models.krx_open_api import KrxOpenApiConfig

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=True,
            base_url="https://x.test",
            key="anykey1234",
        )

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_get
    )

    # Timeout 예외
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(KrxApiError, match="timeout"):
            await krx_mod.fetch_krx_open_api("/sto/stk_bydd_trd", {})

    # 401 (서비스 승인 대기) 변환
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "unauthorized"

    mock_client2 = MagicMock()
    mock_client2.__aenter__ = AsyncMock(return_value=mock_client2)
    mock_client2.__aexit__ = AsyncMock(return_value=None)
    mock_client2.post = AsyncMock(return_value=mock_response)

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client2):
        with pytest.raises(KrxApiError, match="401"):
            await krx_mod.fetch_krx_open_api("/sto/stk_bydd_trd", {})
