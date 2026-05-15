"""백테스트 라우트 — /api/backtest/* (Phase 1).

Phase 1 산출: ``GET /api/backtest/mcp/health`` — 외부 MCP 백테스트 서버 헬스체크.
Phase 2 이후 백테스트 실행/조회 엔드포인트 추가 예정.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from src.config import settings
from src.models.backtest import McpHealthResponse
from src.models.response import ApiResponse
from src.services.exceptions import ConfigError, ExternalAPIError
from src.services.mcp_client import get_mcp_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.get("/mcp/health", response_model=ApiResponse)
async def mcp_health() -> ApiResponse:
    """외부 MCP 백테스트 서버 헬스체크.

    - ``enabled=false`` (기본) 면 즉시 reachable=false 반환 (외부 호출 0회)
    - ``enabled=true`` 면 ``list_tools()`` 호출로 실제 접속 검증
    - 어떤 경우에도 HTTP 200 반환 (graceful degrade)
    """
    enabled = bool(settings.kis_mcp_enabled)
    if not enabled:
        payload = McpHealthResponse(
            enabled=False, reachable=False, tools_count=0, error=None
        )
        return ApiResponse(success=True, data=payload.model_dump(), message="MCP 비활성")

    client = get_mcp_client()
    error: str | None = None
    tools_count = 0
    reachable = False
    try:
        tools = await client.list_tools()
        tools_count = len(tools)
        reachable = True
    except (ConfigError, ExternalAPIError) as e:
        error = str(e)
        logger.warning("[backtest_health] %s", e)
    except Exception as e:  # pragma: no cover — 예상 외 예외도 graceful
        error = f"예상 외 오류: {e}"
        logger.exception("[backtest_health] 예외")

    payload = McpHealthResponse(
        enabled=True,
        reachable=reachable,
        tools_count=tools_count,
        error=error,
    )
    return ApiResponse(
        success=True,
        data=payload.model_dump(),
        message="MCP 활성" if reachable else "MCP 접속 실패",
    )
