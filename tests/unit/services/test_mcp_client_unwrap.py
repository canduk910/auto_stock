"""Phase 6 (보강) — MCPClient.call_tool() MCP content 래핑 unwrap 검증.

결함 A: 외부 서버 응답이 MCP Streamable HTTP 2겹 래핑 구조인데 풀지 않고 그대로 반환:
    {
      "content": [
        {"type":"text","text":"{\"success\":true,\"data\":{...}}"}
      ]
    }

→ BacktestEngine._unwrap() 이 data 키 못 찾아 빈 dict → 모든 메트릭 None.

Phase 1 16 케이스 회귀 보존 + content 래핑 자동 unwrap.

stock-manager `services/mcp_client.py::_extract_mcp_content()` 패턴 이식 검증.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

MCP_BASE = "http://43.202.187.5:3846"
MCP_PATH = "/mcp"
MCP_URL = MCP_BASE + MCP_PATH


# ---------------------------------------------------------------------------
# 헬퍼 (test_mcp_client.py 와 동일 패턴)
# ---------------------------------------------------------------------------
def _initialize_resp(session_id: str = "sess-1") -> httpx.Response:
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


def _sse_with_result(result: dict, req_id: int = 2) -> httpx.Response:
    """SSE 응답 (JSON-RPC result 안에 원하는 dict 주입)."""
    body = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})


def _content_wrapped(payload: dict) -> dict:
    """외부 서버 stock-manager 패턴 응답 모사.

    JSON-RPC `result` 가 `{"content":[{"type":"text","text":"<JSON>"}]}` 인 케이스.
    """
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
        ]
    }


@pytest.fixture
def reset_singleton():
    from src.services import mcp_client as mc

    mc._client_instance = None
    yield
    mc._client_instance = None


# ---------------------------------------------------------------------------
# A1 회귀: 일반 result dict → 그대로 반환 (Phase 1 케이스 보존)
# ---------------------------------------------------------------------------
async def test_a1_regression_plain_result_returns_as_is(reset_singleton):
    """기존 Phase 1 A9/A10 회귀 — content 키 없으면 result 그대로."""
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result({"metrics": {"cagr": 0.21}}),
            ]
        )
        result = await client.call_tool("any_tool", {})

    # content 키 없는 일반 dict 는 변형 없이 그대로 반환
    assert result == {"metrics": {"cagr": 0.21}}
    await client.close()


# ---------------------------------------------------------------------------
# A3: MCP content 래핑 + success:true + data → data 평탄화
# ---------------------------------------------------------------------------
async def test_a3_content_wrapped_success_data_extracted(reset_singleton):
    """결함 A 핵심 케이스 — 외부 서버 실측 응답 구조."""
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    payload = {
        "success": True,
        "data": {"job_id": "bt-001", "status": "running"},
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(_content_wrapped(payload)),
            ]
        )
        result = await client.call_tool("run_preset_backtest_tool", {})

    # call_tool 이 content 래핑 자동 풀어서 data dict 반환
    assert result == {"job_id": "bt-001", "status": "running"}
    await client.close()


# ---------------------------------------------------------------------------
# A4: content 래핑 + success:false + error → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_a4_content_wrapped_failure_raises(reset_singleton):
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    payload = {
        "success": False,
        "error": "Invalid preset id: foo",
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(_content_wrapped(payload)),
            ]
        )
        with pytest.raises(ExternalAPIError, match="Invalid preset"):
            await client.call_tool("run_preset_backtest_tool", {})

    await client.close()


# ---------------------------------------------------------------------------
# A5: content 래핑 + success:true + data 없음 → parsed 전체 반환 (graceful)
# ---------------------------------------------------------------------------
async def test_a5_content_wrapped_success_without_data_returns_parsed(reset_singleton):
    """data 가 없으면 parsed 전체를 반환해 호출부가 직접 살펴볼 수 있게 한다."""
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    payload = {"success": True, "message": "ok"}
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(_content_wrapped(payload)),
            ]
        )
        result = await client.call_tool("any_tool", {})

    # data 키 없을 때 parsed 전체 반환 (graceful)
    assert result == {"success": True, "message": "ok"}
    await client.close()


# ---------------------------------------------------------------------------
# A6: content 배열에 여러 text 항목 → 첫 번째 text 만 사용
# ---------------------------------------------------------------------------
async def test_a6_content_multiple_items_uses_first_text(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    payload1 = {"success": True, "data": {"first": "ok"}}
    payload2 = {"success": True, "data": {"second": "ignore"}}
    multi = {
        "content": [
            {"type": "text", "text": json.dumps(payload1)},
            {"type": "text", "text": json.dumps(payload2)},
        ]
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(multi),
            ]
        )
        result = await client.call_tool("any_tool", {})

    assert result == {"first": "ok"}
    await client.close()


# ---------------------------------------------------------------------------
# A7: content[0].text 가 JSON 파싱 실패 → 원본 result dict 반환 (graceful)
# ---------------------------------------------------------------------------
async def test_a7_content_text_invalid_json_returns_raw(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    raw = {"content": [{"type": "text", "text": "not a json {{{"}]}
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(raw),
            ]
        )
        result = await client.call_tool("any_tool", {})

    # JSON 파싱 실패 시 원본 result 그대로 반환 (호출자가 직접 해석 가능)
    assert result == raw
    await client.close()


# ---------------------------------------------------------------------------
# A8: content[0].type != "text" → 원본 그대로
# ---------------------------------------------------------------------------
async def test_a8_content_non_text_type_returns_raw(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    raw = {"content": [{"type": "image", "data": "..."}]}
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(raw),
            ]
        )
        result = await client.call_tool("any_tool", {})

    assert result == raw
    await client.close()


# ---------------------------------------------------------------------------
# A9: content 키 자체 없음 → 기존 동작
# ---------------------------------------------------------------------------
async def test_a9_no_content_key_returns_as_is(reset_singleton):
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    raw = {"foo": "bar", "result_field": 42}
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(raw),
            ]
        )
        result = await client.call_tool("any_tool", {})

    assert result == raw
    await client.close()


# ---------------------------------------------------------------------------
# A10: 실측 list_presets_tool 응답 형태 (외부 검증 스크립트 결과 그대로)
# ---------------------------------------------------------------------------
async def test_a10_real_list_presets_response_shape(reset_singleton):
    """실측: list_presets_tool 응답 = content[text=JSON{success,data:[10 presets]}]."""
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)

    presets = [
        {"id": "sma_crossover", "name": "SMA Crossover"},
        {"id": "momentum", "name": "Momentum"},
        {"id": "volatility_breakout", "name": "VB"},
    ]
    payload = {"success": True, "data": presets}
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_result(_content_wrapped(payload)),
            ]
        )
        result = await client.call_tool("list_presets_tool", {})

    # data 가 list 여도 그대로 평탄화 반환
    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0]["id"] == "sma_crossover"
    await client.close()
