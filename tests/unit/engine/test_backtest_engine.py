"""Phase 2 Red — `src/engine/backtest_engine.py` BacktestEngine.

외부 MCP 백테스트 서버 통합.

흐름:
1. `run_for_strategy(strategy_id, params, days=90, kind="current")` →
   - YAML build → `validate_yaml_tool` → `run_backtest_tool` → job_id 반환
   - (b) 폴백 전략은 `BacktestNotSupportedError` propagate
2. `poll(job_id)` → `get_backtest_result_tool(wait=False)` 1회 호출
   - status=running 시 None
   - status=completed 시 BacktestMetrics 반환
   - status=failed 시 ExternalAPIError raise
3. `KIS_MCP_ENABLED=false` 시 `run_for_strategy` 가 ConfigError raise (graceful degrade)
4. 외부 서버 timeout/connect 에러 → ExternalAPIError propagate (자문 흐름은 graceful)

핵심 안전 원칙:
- 운영 매매 흐름(scheduler/order_engine/risk) 영역 침범 없음.
- 모든 에러 발생 시 자문 흐름은 backtest_summary=null 로 graceful degrade.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼: BacktestEngine 인스턴스 생성 + 모의 MCP 클라이언트 주입
# ---------------------------------------------------------------------------
def _engine_with_fake_client(enabled: bool = True):
    """BacktestEngine + 가짜 client 페어 반환.

    client.call_tool 은 AsyncMock — 테스트에서 side_effect 로 응답 시나리오 작성.
    """
    from src.engine.backtest_engine import BacktestEngine

    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock()
    eng = BacktestEngine(client=fake_client, enabled=enabled)
    return eng, fake_client


# ---------------------------------------------------------------------------
# A: run_for_strategy 정상 — YAML build → validate → run → job_id
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_for_strategy_momentum_submits_yaml_and_returns_job_id():
    eng, client = _engine_with_fake_client(enabled=True)

    # 외부 서버 응답 시나리오 (순서대로): validate_yaml_tool → run_backtest_tool
    client.call_tool.side_effect = [
        {"success": True, "data": {"valid": True}},
        {"success": True, "data": {"job_id": "bt-momentum-001"}},
    ]

    job_id = await eng.run_for_strategy(
        strategy_id="momentum",
        params={"buy_threshold": 29.0, "stop_loss_rate": -7.5},
        days=90,
        kind="current",
    )

    assert job_id == "bt-momentum-001"
    assert client.call_tool.await_count == 2
    # 첫 호출 = validate_yaml_tool
    first_call_args = client.call_tool.await_args_list[0]
    assert first_call_args.args[0] == "validate_yaml_tool"
    assert "yaml_content" in first_call_args.args[1]
    # 두번째 호출 = run_backtest_tool
    second_call_args = client.call_tool.await_args_list[1]
    assert second_call_args.args[0] == "run_backtest_tool"
    assert "symbols" in second_call_args.args[1]


# ---------------------------------------------------------------------------
# B: poll — running 시 None / completed 시 metrics 반환
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_returns_none_when_running():
    eng, client = _engine_with_fake_client(enabled=True)

    client.call_tool.return_value = {
        "success": True,
        "data": {"status": "running", "progress": 0.4},
    }

    result = await eng.poll("bt-001")
    assert result is None


@pytest.mark.asyncio
async def test_poll_returns_metrics_when_completed():
    eng, client = _engine_with_fake_client(enabled=True)

    client.call_tool.return_value = {
        "success": True,
        "data": {
            "status": "completed",
            "metrics": {
                "total_return_pct": 12.3,
                "cagr": 0.45,
                "sharpe_ratio": 1.4,
                "sortino_ratio": 2.1,
                "max_drawdown": -8.7,
                "win_rate": 0.62,
                "profit_factor": 1.8,
                "total_trades": 18,
            },
        },
    }

    result = await eng.poll("bt-001")
    assert result is not None
    assert result.total_return_pct == 12.3
    assert result.sharpe_ratio == 1.4
    assert result.total_trades == 18


# ---------------------------------------------------------------------------
# C: poll → failed 시 ExternalAPIError raise
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_raises_when_failed():
    eng, client = _engine_with_fake_client(enabled=True)
    from src.services.exceptions import ExternalAPIError

    client.call_tool.return_value = {
        "success": True,
        "data": {
            "status": "failed",
            "error": "EGW00201: API 호출 한도 초과",
        },
    }

    with pytest.raises(ExternalAPIError) as exc:
        await eng.poll("bt-001")
    assert "EGW00201" in str(exc.value) or "한도" in str(exc.value)


# ---------------------------------------------------------------------------
# D: KIS_MCP_ENABLED=false → run_for_strategy 거부 (graceful degrade)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_for_strategy_when_disabled_raises_config_error():
    from src.services.exceptions import ConfigError

    eng, client = _engine_with_fake_client(enabled=False)

    with pytest.raises(ConfigError):
        await eng.run_for_strategy(
            strategy_id="momentum",
            params={},
            days=90,
            kind="current",
        )

    # 외부 호출은 0회 (graceful)
    assert client.call_tool.await_count == 0


# ---------------------------------------------------------------------------
# E: 6 전략 매핑 검증 — (a) 3 전략은 정상 / (b) 3 전략은 BacktestNotSupportedError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", ["momentum", "volatility_breakout", "donchian_swing"])
async def test_run_for_strategy_yaml_strategies_succeed(strategy_id: str):
    """(a) YAML 매핑 가능 3 전략 — job_id 정상 반환."""
    eng, client = _engine_with_fake_client(enabled=True)
    client.call_tool.side_effect = [
        {"success": True, "data": {"valid": True}},
        {"success": True, "data": {"job_id": f"bt-{strategy_id}"}},
    ]

    job_id = await eng.run_for_strategy(
        strategy_id=strategy_id, params={}, days=90, kind="current"
    )
    assert job_id == f"bt-{strategy_id}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "strategy_id", ["long_tail_volatility", "bull_flag_breakout", "vcp_breakout"]
)
async def test_run_for_strategy_local_fallback_strategies_raise_not_supported(
    strategy_id: str,
):
    """(b) 로컬 폴백 전략 — BacktestNotSupportedError propagate.

    호출자(recommendation_engine) 가 본 에러를 잡아 backtest_runs.status=skipped
    또는 fallback_local 분기로 보내야 한다. Phase 4-bis 에서 로컬 어댑터 구현.
    """
    from src.services.exceptions import BacktestNotSupportedError

    eng, client = _engine_with_fake_client(enabled=True)

    with pytest.raises(BacktestNotSupportedError):
        await eng.run_for_strategy(
            strategy_id=strategy_id, params={}, days=90, kind="current"
        )
    # 외부 호출은 0회 (YAML build 단계에서 거부)
    assert client.call_tool.await_count == 0


# ---------------------------------------------------------------------------
# F: validate_yaml_tool 실패 → ExternalAPIError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_for_strategy_validate_failure_raises():
    from src.services.exceptions import ExternalAPIError

    eng, client = _engine_with_fake_client(enabled=True)
    client.call_tool.return_value = {
        "success": True,
        "data": {"valid": False, "errors": ["bad indicator alias"]},
    }

    with pytest.raises(ExternalAPIError):
        await eng.run_for_strategy(
            strategy_id="momentum", params={}, days=90, kind="current"
        )
