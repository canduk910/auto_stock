"""src/services/mcp_client.py 단위 테스트 (Phase 1 — backtest MCP 통합).

외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`) 와 JSON-RPC 2.0
over Streamable HTTP/SSE 로 통신하는 클라이언트 검증.

- 비활성(graceful degrade) → ConfigError / health_check False
- 활성 + 세션 초기화 → mcp-session-id 추출 후 tools/call
- 세션 재사용 (싱글톤)
- 421 만료 → 1회 자동 재초기화 후 재시도
- 타임아웃 / HTTP 5xx / JSON-RPC error / SSE & JSON 응답 양쪽 파싱
- list_tools / health_check

stock-manager `services/mcp_client.py` 패턴을 async 환경으로 이식.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

# MCP 서버 URL — conftest 의 settings 와 동일한 디폴트 사용
MCP_BASE = "http://43.202.187.5:3846"
MCP_PATH = "/mcp"
MCP_URL = MCP_BASE + MCP_PATH


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _initialize_resp(session_id: str = "session-abc-123") -> httpx.Response:
    """MCP initialize 정상 응답 (SSE 포맷)."""
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
    return httpx.Response(
        200,
        text=sse,
        headers={
            "content-type": "text/event-stream",
            "mcp-session-id": session_id,
        },
    )


def _sse_tool_result(result: dict, req_id: int = 2) -> httpx.Response:
    body = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})


def _sse_tool_error(message: str, code: int = -32000, req_id: int = 2) -> httpx.Response:
    body = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})


def _json_tool_result(result: dict, req_id: int = 2) -> httpx.Response:
    body = {"jsonrpc": "2.0", "id": req_id, "result": result}
    return httpx.Response(200, json=body, headers={"content-type": "application/json"})


@pytest.fixture
def reset_singleton():
    """모듈 레벨 싱글턴을 매 테스트마다 초기화."""
    from src.services import mcp_client as mc

    mc._client_instance = None
    yield
    # 사용 후에도 reset — 다른 테스트에 영향 주지 않도록
    inst = mc._client_instance
    if inst is not None:
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(inst.close())
        except Exception:
            pass
    mc._client_instance = None


# ---------------------------------------------------------------------------
# A1: 비활성 (graceful degrade)
# ---------------------------------------------------------------------------
async def test_a1_call_tool_when_disabled_then_raises_config_error(reset_singleton):
    from src.services.exceptions import ConfigError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=False)
    with pytest.raises(ConfigError):
        await client.call_tool("noop", {})
    await client.close()


async def test_a1_health_check_when_disabled_then_returns_false(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=False)
    ok = await client.health_check()
    assert ok is False
    await client.close()


# ---------------------------------------------------------------------------
# A2: 활성 + 미초기화 → initialize 후 tools/call
# ---------------------------------------------------------------------------
async def test_a2_call_tool_when_no_session_then_initializes_then_calls(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock(assert_all_called=True) as router:
        init_route = router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_tool_result({"backtest_id": "bt-001"}),
            ]
        )

        result = await client.call_tool("run_backtest_tool", {"strategy": "momentum"})

    assert init_route.call_count == 2
    # 첫 호출 = initialize (Mcp-Session-Id 헤더 없어야 함)
    first_req = init_route.calls[0].request
    first_body = json.loads(first_req.content)
    assert first_body["method"] == "initialize"
    assert first_body["params"]["protocolVersion"]  # 명세된 버전 포함
    assert "mcp-session-id" not in {k.lower() for k in first_req.headers.keys()}

    # 두번째 호출 = tools/call (Mcp-Session-Id 헤더 포함)
    second_req = init_route.calls[1].request
    second_body = json.loads(second_req.content)
    assert second_body["method"] == "tools/call"
    assert second_body["params"]["name"] == "run_backtest_tool"
    assert second_body["params"]["arguments"] == {"strategy": "momentum"}
    assert second_req.headers.get("mcp-session-id") == "sess-1"
    # MCP 스펙: Accept 헤더에 SSE 포함
    assert "text/event-stream" in second_req.headers.get("accept", "")

    assert result == {"backtest_id": "bt-001"}

    await client.close()


# ---------------------------------------------------------------------------
# A3: 세션 재사용
# ---------------------------------------------------------------------------
async def test_a3_second_call_when_session_exists_then_skips_initialize(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock(assert_all_called=True) as router:
        route = router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-A"),
                _sse_tool_result({"first": "ok"}),
                _sse_tool_result({"second": "ok"}),
            ]
        )

        r1 = await client.call_tool("tool1", {})
        r2 = await client.call_tool("tool2", {})

    assert route.call_count == 3  # init + tool1 + tool2 (재초기화 없음)
    assert r1 == {"first": "ok"}
    assert r2 == {"second": "ok"}

    # 3번째 호출은 tools/call (initialize 없음)
    third_req = route.calls[2].request
    third_body = json.loads(third_req.content)
    assert third_body["method"] == "tools/call"
    assert third_body["params"]["name"] == "tool2"
    assert third_req.headers.get("mcp-session-id") == "sess-A"

    await client.close()


# ---------------------------------------------------------------------------
# A4: 421 → 자동 재초기화 → 재시도 성공
# ---------------------------------------------------------------------------
async def test_a4_when_421_then_reinitializes_and_retries(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock(assert_all_called=True) as router:
        route = router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-old"),
                httpx.Response(421, json={"error": "session expired"}),
                _initialize_resp("sess-new"),
                _sse_tool_result({"retry": "ok"}),
            ]
        )

        result = await client.call_tool("validate_yaml_tool", {"yaml": "..."})

    assert route.call_count == 4
    assert result == {"retry": "ok"}

    # 마지막 tools/call 은 새 세션 ID 사용
    last_req = route.calls[3].request
    assert last_req.headers.get("mcp-session-id") == "sess-new"

    await client.close()


# ---------------------------------------------------------------------------
# A5: 421 재시도 후에도 실패 → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_a5_when_421_persists_then_raises_external_api_error(reset_singleton):
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock(assert_all_called=True) as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                httpx.Response(421, json={"error": "expired"}),
                _initialize_resp("sess-2"),
                httpx.Response(421, json={"error": "expired"}),
            ]
        )

        with pytest.raises(ExternalAPIError):
            await client.call_tool("tool", {})

    await client.close()


# ---------------------------------------------------------------------------
# A6: connect 타임아웃 → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_a6_when_connect_timeout_then_raises_external_api_error(reset_singleton):
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(side_effect=httpx.ConnectTimeout("connect timeout"))
        with pytest.raises(ExternalAPIError):
            await client.call_tool("tool", {})

    await client.close()


# ---------------------------------------------------------------------------
# A7: read 타임아웃 → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_a7_when_read_timeout_then_raises_external_api_error(reset_singleton):
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                httpx.ReadTimeout("read timeout"),
            ]
        )
        with pytest.raises(ExternalAPIError):
            await client.call_tool("tool", {})

    await client.close()


# ---------------------------------------------------------------------------
# A8: HTTP 5xx → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_a8_when_http_500_then_raises_external_api_error(reset_singleton):
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                httpx.Response(500, text="internal error"),
            ]
        )
        with pytest.raises(ExternalAPIError):
            await client.call_tool("tool", {})

    await client.close()


# ---------------------------------------------------------------------------
# A9: SSE 응답 파싱
# ---------------------------------------------------------------------------
async def test_a9_when_sse_response_then_extracts_result(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_tool_result({"metrics": {"cagr": 0.21}}),
            ]
        )
        result = await client.call_tool("run_backtest_tool", {})

    assert result == {"metrics": {"cagr": 0.21}}
    await client.close()


# ---------------------------------------------------------------------------
# A10: 표준 JSON 응답 파싱
# ---------------------------------------------------------------------------
async def test_a10_when_application_json_response_then_extracts_result(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _json_tool_result({"plain": "json"}),
            ]
        )
        result = await client.call_tool("any_tool", {})

    assert result == {"plain": "json"}
    await client.close()


# ---------------------------------------------------------------------------
# A11: JSON-RPC error → ExternalAPIError(message=error.message)
# ---------------------------------------------------------------------------
async def test_a11_when_jsonrpc_error_then_raises_with_message(reset_singleton):
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_tool_error("Invalid params: missing strategy"),
            ]
        )
        with pytest.raises(ExternalAPIError, match="Invalid params"):
            await client.call_tool("bad_tool", {})

    await client.close()


# ---------------------------------------------------------------------------
# A12: health_check / list_tools
# ---------------------------------------------------------------------------
async def test_a12_health_check_when_tools_list_succeeds_then_returns_true(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_tool_result(
                    {
                        "tools": [
                            {"name": "run_preset_backtest_tool"},
                            {"name": "run_backtest_tool"},
                            {"name": "validate_yaml_tool"},
                            {"name": "get_backtest_result_tool"},
                        ]
                    }
                ),
            ]
        )
        ok = await client.health_check()

    assert ok is True
    await client.close()


async def test_a12_health_check_when_server_unreachable_then_returns_false(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(side_effect=httpx.ConnectError("refused"))
        ok = await client.health_check()

    assert ok is False
    await client.close()


async def test_a12_list_tools_returns_tool_list(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    tools_payload = {
        "tools": [
            {"name": "run_preset_backtest_tool", "description": "..."},
            {"name": "run_backtest_tool", "description": "..."},
            {"name": "validate_yaml_tool", "description": "..."},
        ]
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[_initialize_resp("sess-1"), _sse_tool_result(tools_payload)]
        )
        tools = await client.list_tools()

    # tools 키의 list 그대로 반환 또는 도구명 list 반환 — 어느 쪽이든 4종 검증 가능하게
    assert len(tools) >= 3
    names = []
    for item in tools:
        if isinstance(item, dict):
            names.append(item.get("name"))
        else:
            names.append(item)
    assert "run_preset_backtest_tool" in names
    assert "validate_yaml_tool" in names

    await client.close()


# ---------------------------------------------------------------------------
# 보너스: 싱글톤 getter — get_mcp_client() 동일 인스턴스 반환
# ---------------------------------------------------------------------------
async def test_get_mcp_client_returns_same_instance(reset_singleton):
    from src.services.mcp_client import get_mcp_client

    a = get_mcp_client()
    b = get_mcp_client()
    assert a is b
    await a.close()
