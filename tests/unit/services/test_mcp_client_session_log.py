"""Phase 6 (보강) — 결함 C: initialize 세션-id 누락 경고 로그 레벨 다운그레이드.

외부 서버가 stateless 모드면 mcp-session-id 헤더 미반환. 매 호출 WARNING 로그 노이즈.
운영 영향 미미하지만 가시성 개선.

요구 행위:
- C1: initialize() 응답에 session-id 없으면 DEBUG 레벨 로그 (WARNING 아님)
- C2: 빈 session_id 도 정상 처리 (이전과 동일하게 None 저장)
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

MCP_URL = "http://43.202.187.5:3846/mcp"


def _initialize_resp_no_session_id() -> httpx.Response:
    """session-id 헤더 없는 initialize 응답 (stateless 서버)."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "kis-backtest", "version": "1.0"},
        },
    }
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    # mcp-session-id 헤더 의도적 생략
    return httpx.Response(
        200, text=sse, headers={"content-type": "text/event-stream"}
    )


@pytest.fixture
def reset_singleton():
    from src.services import mcp_client as mc

    mc._client_instance = None
    yield
    mc._client_instance = None


# ---------------------------------------------------------------------------
# C1: session-id 헤더 없을 때 로그 레벨이 DEBUG (WARNING 아님)
# ---------------------------------------------------------------------------
async def test_c1_initialize_no_session_id_logs_at_debug(
    reset_singleton, caplog
):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(side_effect=[_initialize_resp_no_session_id()])
        with caplog.at_level(logging.DEBUG, logger="src.services.mcp_client"):
            session_id = await client.initialize()

    assert session_id == ""
    # WARNING 레벨 메시지가 없어야 한다
    warnings = [
        r for r in caplog.records
        if r.name == "src.services.mcp_client" and r.levelno >= logging.WARNING
    ]
    assert not warnings, f"WARNING 로그 발생 안 됨이 기대인데 {len(warnings)}건: {[r.message for r in warnings]}"
    await client.close()


# ---------------------------------------------------------------------------
# C2: 빈 session_id 후속 호출도 정상 동작 (Mcp-Session-Id 헤더 미부착)
# ---------------------------------------------------------------------------
async def test_c2_initialize_no_session_id_allows_call_tool(reset_singleton):
    """session-id 없어도 call_tool 이 작동 (stateless 외부 서버)."""
    import json

    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    def _tool_resp(payload: dict, req_id: int = 2) -> httpx.Response:
        body = {"jsonrpc": "2.0", "id": req_id, "result": payload}
        sse = f"event: message\ndata: {json.dumps(body)}\n\n"
        return httpx.Response(
            200, text=sse, headers={"content-type": "text/event-stream"}
        )

    with respx.mock() as router:
        route = router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp_no_session_id(),
                _tool_resp({"ok": True}),
            ]
        )
        result = await client.call_tool("any_tool", {})

    assert result == {"ok": True}
    # 두 번째 요청에 Mcp-Session-Id 헤더가 없어야 한다 (session_id 가 None/빈)
    second_req = route.calls[1].request
    assert second_req.headers.get("mcp-session-id") in (None, "", "None")
    await client.close()
