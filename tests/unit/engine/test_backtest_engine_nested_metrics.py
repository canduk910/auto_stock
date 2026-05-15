"""Phase 6 (보강) 추가 결함 — 외부 서버 metrics 중첩 응답 평탄화.

verify_mcp_response_schema.py 실측 결과:

응답 구조 (unwrap 후 data):
{
    "job_id": "...", "status": "completed",
    "result": {                       # ← 한 단계 더 들어감
        "metrics": {
            "basic":   {"total_return", "annual_return", "max_drawdown", ...},
            "risk":    {"sharpe_ratio", "sortino_ratio"},
            "trading": {"total_orders", "win_rate", "profit_loss_ratio", ...}
        },
        "equity_curve": {...},
        "trades": [...]
    }
}

키 매핑:
- basic.total_return       → total_return_pct
- basic.annual_return      → cagr (둘 다 percent)
- basic.max_drawdown       → max_drawdown (양수, 절대값)
- risk.sharpe_ratio        → sharpe_ratio
- risk.sortino_ratio       → sortino_ratio
- trading.win_rate         → win_rate
- trading.profit_loss_ratio → profit_factor (외부 서버 명명 차이)
- trading.total_orders     → total_trades
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
    wrapper = {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
        ]
    }
    body = {"jsonrpc": "2.0", "id": req_id, "result": wrapper}
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})


def _real_response_shape() -> dict:
    """verify_mcp_response_schema.py 에서 캡처한 실측 응답 (sma_crossover, 005930)."""
    return {
        "success": True,
        "data": {
            "job_id": "552bfdc3-73d2-4d0c-b548-aec00bc92243",
            "status": "completed",
            "strategy_name": "SMA 골든/데드 크로스",
            "symbols": ["005930"],
            "result": {
                "run_id": "mcp_552bfdc3_sma_crossover",
                "strategy_name": "SMA 골든/데드 크로스",
                "symbols": ["005930"],
                "start_date": "2026-02-01",
                "end_date": "2026-04-30",
                "initial_capital": 10000000.0,
                "final_capital": 9255282.74,
                "net_profit": -744717.26,
                "net_profit_percent": -7.447,
                "metrics": {
                    "basic": {
                        "total_return": -7.447,
                        "annual_return": -27.468,
                        "max_drawdown": 16.1,
                        "drawdown_recovery": 0.0,
                        "start_equity": 10000000.0,
                        "end_equity": 9255282.74,
                    },
                    "risk": {
                        "sharpe_ratio": -0.796,
                        "sortino_ratio": -0.42,
                    },
                    "trading": {
                        "total_orders": 6,
                        "win_rate": 33.0,
                        "loss_rate": 67.0,
                        "avg_win": 10.08,
                        "avg_loss": -8.56,
                        "profit_loss_ratio": 1.18,
                    },
                },
                "equity_curve": {"2026-02-01": 10000000.0},
                "trades_count": 6,
                "trades": [],
            },
        },
    }


@pytest.fixture
def reset_singleton():
    from src.services import mcp_client as mc

    mc._client_instance = None
    yield
    mc._client_instance = None


# ---------------------------------------------------------------------------
# N1: 실측 응답 — poll 이 nested metrics 평탄화 후 BacktestMetrics 정상 구성
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_n1_poll_flattens_nested_metrics(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(_real_response_shape()),
            ]
        )
        metrics = await engine.poll("552bfdc3-73d2-4d0c-b548-aec00bc92243")

    assert metrics is not None
    # 평탄화 매핑 검증
    assert metrics.total_return_pct == -7.447
    assert metrics.cagr == -27.468
    assert metrics.max_drawdown == 16.1  # 양수 = 절대값
    assert metrics.sharpe_ratio == -0.796
    assert metrics.sortino_ratio == -0.42
    assert metrics.win_rate == 33.0
    assert metrics.profit_factor == 1.18  # profit_loss_ratio → profit_factor 매핑
    assert metrics.total_trades == 6     # total_orders → total_trades 매핑
    await client.close()


# ---------------------------------------------------------------------------
# N2: 평탄 응답도 그대로 처리 (회귀 보존 — D2 케이스)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_n2_poll_flat_metrics_still_works(reset_singleton):
    """8 키 평탄 응답도 그대로 BacktestMetrics 로 매핑 (예전 호환)."""
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    flat_payload = {
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
                _sse_with_content(flat_payload),
            ]
        )
        metrics = await engine.poll("any-job")

    assert metrics is not None
    assert metrics.total_return_pct == 15.5
    assert metrics.cagr == 12.3
    assert metrics.profit_factor == 1.7
    assert metrics.total_trades == 42
    await client.close()


# ---------------------------------------------------------------------------
# N3: 부분 중첩 — basic 만 있고 risk/trading 누락 → 가능한 키만 채움 + None 허용
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_n3_partial_nested_metrics_graceful(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    partial = {
        "success": True,
        "data": {
            "status": "completed",
            "result": {
                "metrics": {
                    "basic": {"total_return": 5.0, "annual_return": 18.0, "max_drawdown": 4.5},
                    # risk / trading 누락
                }
            },
        },
    }
    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(partial),
            ]
        )
        metrics = await engine.poll("any-job")

    assert metrics is not None
    assert metrics.total_return_pct == 5.0
    assert metrics.cagr == 18.0
    assert metrics.max_drawdown == 4.5
    # 미제공 필드는 None
    assert metrics.sharpe_ratio is None
    assert metrics.profit_factor is None
    assert metrics.total_trades is None
    await client.close()


# ---------------------------------------------------------------------------
# N4: wait_for_result 도 동일 평탄화 (Phase 3 자문 흐름)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_n4_wait_for_result_flattens_nested(reset_singleton):
    from src.engine.backtest_engine import BacktestEngine
    from src.services.mcp_client import MCPClient

    client = MCPClient(base_url=MCP_URL, enabled=True)
    engine = BacktestEngine(client=client, enabled=True)

    with respx.mock() as router:
        router.post(MCP_URL).mock(
            side_effect=[
                _initialize_resp("sess-1"),
                _sse_with_content(_real_response_shape()),
            ]
        )
        metrics = await engine.wait_for_result("any-job", timeout=10)

    assert metrics is not None
    assert metrics.total_return_pct == -7.447
    assert metrics.profit_factor == 1.18
    await client.close()
