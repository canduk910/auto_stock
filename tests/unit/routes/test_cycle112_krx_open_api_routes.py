"""사이클 112 영역 2 (HIGH 6) — `/api/integrations/krx-open-api` GET/PUT 라우트.

Red 명세 (`_workspace/red/cycle112_krx_open_api_infra.md`):

G-RT-1~6 — 응답 형식 정확성 + 평문 key 절대 노출 차단 + 부분 갱신 정합성.

위험 등급 HIGH (평문 key 노출 영구 차단 + 사이클 5 패턴 답습).

영속 의무:
- 사이클 5 system_integrations 라우트 패턴 (ApiResponse 래퍼)
- 사이클 7-A 마스킹 (`****1234` 형식)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    """라우트 격리 fixture — get/set 헬퍼 mock."""
    from src.main import app

    return TestClient(app)


@pytest.mark.asyncio
async def test_g_rt_1_get_response_shape(monkeypatch, client):
    """G-RT-1: GET 응답 = {enabled, base_url, key_masked} 정확 형식."""
    from src.models.krx_open_api import KrxOpenApiConfig
    from src.routes import system_integrations as si

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=True,
            base_url="https://data-dbg.krx.co.kr/svc/apis",
            key="secret_key_1234",
        )

    monkeypatch.setattr(si.sc, "get_krx_open_api_config", _fake_get)

    response = client.get("/api/integrations/krx-open-api")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert set(data.keys()) == {"enabled", "base_url", "key_masked"}
    assert data["enabled"] is True
    assert data["base_url"] == "https://data-dbg.krx.co.kr/svc/apis"
    # 평문 key 노출 0건 — 마스킹 의무
    assert data["key_masked"] == "****1234"


@pytest.mark.asyncio
async def test_g_rt_2_key_masked_no_plaintext_long_key(monkeypatch, client):
    """G-RT-2: 8자 이상 key 는 `****1234` 마스킹."""
    from src.models.krx_open_api import KrxOpenApiConfig
    from src.routes import system_integrations as si

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=False,
            base_url="https://data-dbg.krx.co.kr/svc/apis",
            key="abcdef1234567890abcd",
        )

    monkeypatch.setattr(si.sc, "get_krx_open_api_config", _fake_get)

    response = client.get("/api/integrations/krx-open-api")
    data = response.json()["data"]
    # 평문 absolute 부재
    assert "abcdef1234567890" not in data["key_masked"]
    assert "abcd" in data["key_masked"]  # 마지막 4자리만
    assert data["key_masked"] == "****abcd"


@pytest.mark.asyncio
async def test_g_rt_3_put_saves_plaintext_and_returns_masked(monkeypatch, client):
    """G-RT-3: PUT body key → DB 평문 저장 + 응답 마스킹."""
    from src.models.krx_open_api import KrxOpenApiConfig
    from src.routes import system_integrations as si

    set_calls = []

    async def _fake_set(**kwargs):
        set_calls.append(kwargs)

    async def _fake_get():
        # set 호출 후 응답에 새 키 마스킹 반영
        return KrxOpenApiConfig(
            enabled=False,
            base_url="https://data-dbg.krx.co.kr/svc/apis",
            key="secret_key_1234",
        )

    monkeypatch.setattr(si.sc, "set_krx_open_api_config", _fake_set)
    monkeypatch.setattr(si.sc, "get_krx_open_api_config", _fake_get)

    response = client.put(
        "/api/integrations/krx-open-api",
        json={"key": "secret_key_1234"},
    )
    assert response.status_code == 200

    # DB 저장 시점에 평문 key 전달
    assert len(set_calls) == 1
    assert set_calls[0]["key"] == "secret_key_1234"

    # 응답은 항상 마스킹
    data = response.json()["data"]
    assert data["key_masked"] == "****1234"
    # 평문 응답 노출 0건
    assert "secret_key_1234" not in response.text


@pytest.mark.asyncio
async def test_g_rt_4_put_without_key_preserves_existing(monkeypatch, client):
    """G-RT-4: PUT body 가 key 미포함 → set_krx_open_api_config(key=None) 전달 (기존 보존)."""
    from src.models.krx_open_api import KrxOpenApiConfig
    from src.routes import system_integrations as si

    set_calls = []

    async def _fake_set(**kwargs):
        set_calls.append(kwargs)

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=True,
            base_url="https://x.test",
            key="existing_key_5678",
        )

    monkeypatch.setattr(si.sc, "set_krx_open_api_config", _fake_set)
    monkeypatch.setattr(si.sc, "get_krx_open_api_config", _fake_get)

    response = client.put(
        "/api/integrations/krx-open-api",
        json={"enabled": True},
    )
    assert response.status_code == 200

    # key=None 전달 (기존 보존 시그널)
    assert len(set_calls) == 1
    assert set_calls[0]["key"] is None
    assert set_calls[0]["enabled"] is True


@pytest.mark.asyncio
async def test_g_rt_5_put_empty_body_returns_current(monkeypatch, client):
    """G-RT-5: 빈 body PUT → graceful 현재 상태 응답 (기존 값 유지)."""
    from src.models.krx_open_api import KrxOpenApiConfig
    from src.routes import system_integrations as si

    async def _fake_set(**kwargs):
        pass

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=False,
            base_url="https://x.test",
            key="kept_key_9012",
        )

    monkeypatch.setattr(si.sc, "set_krx_open_api_config", _fake_set)
    monkeypatch.setattr(si.sc, "get_krx_open_api_config", _fake_get)

    response = client.put("/api/integrations/krx-open-api", json={})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["key_masked"] == "****9012"


@pytest.mark.asyncio
async def test_g_rt_6_put_db_failure_returns_500(monkeypatch, client):
    """G-RT-6: DB 갱신 실패 → 500 + 평문 key 절대 노출 차단."""
    from src.routes import system_integrations as si

    async def _fake_set(**kwargs):
        raise RuntimeError("DB connection failed")

    monkeypatch.setattr(si.sc, "set_krx_open_api_config", _fake_set)

    response = client.put(
        "/api/integrations/krx-open-api",
        json={"key": "absolutely_must_not_appear_anywhere"},
    )
    assert response.status_code == 500
    # 평문 key 가 500 응답에 노출되지 않음 — 보안 의무
    assert "absolutely_must_not_appear_anywhere" not in response.text
