"""백테스트 라우트 계약 — /api/backtest/* (Phase 1).

`/api/backtest/mcp/health` 만 검증. 실제 MCP 호출은 monkeypatch 로 격리.
Phase 2 이후 백테스트 실행 라우트가 추가되면 본 파일을 확장.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def test_mcp_health_when_disabled_then_returns_enabled_false(contract_env, monkeypatch):
    """KIS_MCP_ENABLED=false 면 enabled=false / reachable=false / tools_count=0."""
    import src.routes.backtest as backtest_route

    class _FakeClient:
        async def health_check(self):
            return False

        async def list_tools(self):
            return []

    monkeypatch.setattr(backtest_route, "get_mcp_client", lambda: _FakeClient())
    monkeypatch.setattr(backtest_route.settings, "kis_mcp_enabled", False, raising=False)

    r = contract_env.client.get("/api/backtest/mcp/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["enabled"] is False
    assert data["reachable"] is False
    assert data["tools_count"] == 0
    # error 는 nullable
    assert "error" in data


def test_mcp_health_when_enabled_and_reachable_then_returns_tools_count(
    contract_env, monkeypatch
):
    """KIS_MCP_ENABLED=true + 서버 접속 성공 시 tools_count 반환."""
    import src.routes.backtest as backtest_route

    class _FakeClient:
        async def health_check(self):
            return True

        async def list_tools(self):
            return [
                {"name": "run_preset_backtest_tool"},
                {"name": "run_backtest_tool"},
                {"name": "validate_yaml_tool"},
                {"name": "get_backtest_result_tool"},
            ]

    monkeypatch.setattr(backtest_route, "get_mcp_client", lambda: _FakeClient())
    monkeypatch.setattr(backtest_route.settings, "kis_mcp_enabled", True, raising=False)

    r = contract_env.client.get("/api/backtest/mcp/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["enabled"] is True
    assert data["reachable"] is True
    assert data["tools_count"] == 4
    assert data.get("error") is None


def test_mcp_health_when_enabled_but_unreachable_then_error_message(
    contract_env, monkeypatch
):
    """활성화는 됐는데 서버가 다운된 경우 error 메시지를 반환하되 200 으로 graceful."""
    import src.routes.backtest as backtest_route
    from src.services.exceptions import ExternalAPIError

    class _FakeClient:
        async def health_check(self):
            return False

        async def list_tools(self):
            raise ExternalAPIError("KIS MCP 서버에 연결할 수 없습니다")

    monkeypatch.setattr(backtest_route, "get_mcp_client", lambda: _FakeClient())
    monkeypatch.setattr(backtest_route.settings, "kis_mcp_enabled", True, raising=False)

    r = contract_env.client.get("/api/backtest/mcp/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["enabled"] is True
    assert data["reachable"] is False
    assert data["tools_count"] == 0
    assert data["error"] is not None
    assert "연결" in data["error"] or "MCP" in data["error"]
