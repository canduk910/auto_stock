"""백테스트 MCP 헬스체크 계약 테스트 (Phase 1).

실제 외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`) 접속 검증.

- `KIS_MCP_ENABLED=false` (기본) 면 skip — CI/로컬 일반 실행에서는 외부 서버 호출 없음
- 로컬에서 수동 검증 시: `KIS_MCP_ENABLED=true pytest tests/contract/test_backtest_mcp_health.py`
  (운영 EC2 IP 화이트리스트는 이미 통과돼 있음)
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.contract


_ENABLED = os.environ.get("KIS_MCP_ENABLED", "").lower() in ("true", "1", "yes")


@pytest.mark.skipif(not _ENABLED, reason="KIS_MCP_ENABLED=true 일 때만 외부 서버 호출")
async def test_real_mcp_server_health_check_succeeds():
    """실제 외부 MCP 서버에 tools/list 호출 → True 반환."""
    from src.services.mcp_client import MCPClient
    from src.config import settings

    client = MCPClient(base_url=settings.kis_mcp_url, enabled=True)
    try:
        ok = await client.health_check()
        assert ok is True, "외부 MCP 서버 헬스체크 실패 — 서버 다운 또는 IP 화이트리스트 차단 가능"
    finally:
        await client.close()


@pytest.mark.skipif(not _ENABLED, reason="KIS_MCP_ENABLED=true 일 때만 외부 서버 호출")
async def test_real_mcp_server_list_tools_includes_backtest_tools():
    """실제 외부 MCP 서버에 도구 목록 조회 → 백테스트 도구 4종 노출."""
    from src.services.mcp_client import MCPClient
    from src.config import settings

    client = MCPClient(base_url=settings.kis_mcp_url, enabled=True)
    try:
        tools = await client.list_tools()
        names = []
        for item in tools:
            if isinstance(item, dict):
                names.append(item.get("name"))
            else:
                names.append(item)

        # Phase 2 에서 사용할 4 도구 중 최소한 run_backtest_tool 은 존재해야 함
        expected_any = {
            "run_preset_backtest_tool",
            "run_backtest_tool",
            "validate_yaml_tool",
            "get_backtest_result_tool",
        }
        assert (
            set(names) & expected_any
        ), f"백테스트 도구 미노출. 실제 노출 목록: {names}"
    finally:
        await client.close()
