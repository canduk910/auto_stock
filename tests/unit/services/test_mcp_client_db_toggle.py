"""사이클 5 (2026-05-17) Red — mcp_client `_check_enabled` DB 우선 / .env fallback.

dkstock_client_db_toggle 패턴과 동일 구조. KIS_MCP_ENABLED 환경변수 fallback 보존.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_client(enabled_ctor: bool = False):
    from src.services.mcp_client import MCPClient

    return MCPClient(
        base_url="http://test:3846/mcp",
        enabled=enabled_ctor,
    )


@pytest.mark.asyncio
async def test_db_true_overrides_env_false(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return True

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    client = _make_client(enabled_ctor=False)

    enabled = await client._check_enabled_async()
    assert enabled is True


@pytest.mark.asyncio
async def test_db_false_overrides_env_true(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return False

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    client = _make_client(enabled_ctor=True)

    enabled = await client._check_enabled_async()
    assert enabled is False


@pytest.mark.asyncio
async def test_db_none_falls_back_to_env_true(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return None

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    client = _make_client(enabled_ctor=True)

    enabled = await client._check_enabled_async()
    assert enabled is True


@pytest.mark.asyncio
async def test_db_none_falls_back_to_env_false(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return None

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    client = _make_client(enabled_ctor=False)

    enabled = await client._check_enabled_async()
    assert enabled is False


@pytest.mark.asyncio
async def test_db_value_change_is_reflected_immediately(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    state = {"value": False}

    async def fake_get_db():
        return state["value"]

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    client = _make_client(enabled_ctor=False)

    assert await client._check_enabled_async() is False
    state["value"] = True
    assert await client._check_enabled_async() is True


@pytest.mark.asyncio
async def test_db_exception_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        raise RuntimeError("DB error")

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    client = _make_client(enabled_ctor=True)

    enabled = await client._check_enabled_async()
    assert enabled is True
