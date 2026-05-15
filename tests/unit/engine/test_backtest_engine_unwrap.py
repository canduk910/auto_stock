"""Phase 6 (보강) — BacktestEngine + MCP content 래핑 통합 검증.

결함 A 가 mcp_client 에서 fix 된 후, BacktestEngine 이 unwrap 된 응답에서
job_id / status / metrics 를 정상 추출하는지 end-to-end 검증.

mcp_client 실제 사용 — respx 로 HTTP 단에서 외부 서버 응답 모사.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

MCP_URL = "http://43.202.187.5:3846/mcp"


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


def _sse_with_content(payload: dict, req_id: int = 2) -> httpx.Response:
    """외부 서버 실측 응답: result.content[0].text = JSON.dumps({success, data:...})."""
    wrapper = {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
        ]
    }
    body = {"jsonrpc": "2.0", "id": req_id, "result": wrapper}
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})


@pytest.fixture
def reset_singleton():
    from src.services import mcp_client as mc

    mc._client_instance = None
    yield
    mc._client_instance = None


# ---------------------------------------------------------------------------
# D1: BacktestEngine.run_for_strategy — content 래핑 응답에서 job_id 추출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d1_run_for_strategy_extracts_job_id_from_content_wrapped(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    validate_payload = {"success": True, "data": {"valid": True}}
    run_payload = {
        "success": True,
        "data": {"job_id": "bt-momentum-001", "status": "running"},
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(validate_payload),
                _sse_with_content(run_payload),
            ]
        )
        job_id = await engine.run_for_strategy("momentum", {})

    assert job_id == "bt-momentum-001"
    await client.close()


# ---------------------------------------------------------------------------
# D2: BacktestEngine.poll — content 래핑 응답에서 metrics 추출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d2_poll_extracts_metrics_from_content_wrapped(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    result_payload = {
        "success": True,
        "data": {
            "status": "completed",
            "metrics": {
                "total_return_pct": 15.5,
                "cagr": 12.3,
                "sharpe_ratio": 1.8,
                "sortino_ratio": 2.1,
                "max_drawdown": -8.2,
                "win_rate": 55.0,
                "profit_factor": 1.7,
                "total_trades": 42,
            },
        },
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(result_payload),
            ]
        )
        metrics = await engine.poll("bt-momentum-001")

    assert metrics is not None
    assert metrics.total_return_pct == 15.5
    assert metrics.cagr == 12.3
    assert metrics.sharpe_ratio == 1.8
    assert metrics.win_rate == 55.0
    assert metrics.total_trades == 42
    await client.close()


# ---------------------------------------------------------------------------
# D2-b: poll 이 running 상태 응답을 None 반환
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d2b_poll_returns_none_when_running(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    running_payload = {
        "success": True,
        "data": {"status": "running", "job_id": "bt-001"},
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(running_payload),
            ]
        )
        metrics = await engine.poll("bt-001")

    assert metrics is None
    await client.close()


# ---------------------------------------------------------------------------
# D3: validate_yaml_tool 응답이 content 래핑 통과 후 valid 정상 인식
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d3_validate_yaml_ok_after_unwrap(reset_singleton):
    """validate_yaml_tool 도 content 래핑 → success/data/valid 평탄화 후 True 인식."""
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    validate_payload = {"success": True, "data": {"valid": True}}
    run_payload = {"success": True, "data": {"job_id": "bt-d3"}}
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(validate_payload),
                _sse_with_content(run_payload),
            ]
        )
        # validate 가 false 면 ExternalAPIError 가 raise — 정상 통과 검증
        job_id = await engine.run_for_strategy("donchian_swing", {})

    assert job_id == "bt-d3"
    await client.close()


# ---------------------------------------------------------------------------
# D4: validate_yaml_tool 거부 시 ExternalAPIError (회귀 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d4_validate_yaml_reject_raises(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.exceptions import ExternalAPIError
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    # validate 가 success:true 인데 data.valid=false 케이스
    validate_payload = {
        "success": True,
        "data": {"valid": False, "errors": ["YAML invalid: missing strategy.id"]},
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(validate_payload),
            ]
        )
        with pytest.raises(ExternalAPIError, match="validate_yaml_tool"):
            await engine.run_for_strategy("momentum", {})

    await client.close()
