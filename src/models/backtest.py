"""백테스트 관련 Pydantic 모델 (Phase 1).

Phase 1 — MCP 헬스체크 응답만. Phase 2 에서 BacktestMetrics/BacktestRun/Summary 확장.
"""
from __future__ import annotations

from pydantic import BaseModel


class McpHealthResponse(BaseModel):
    """`GET /api/backtest/mcp/health` 응답.

    - ``enabled``: ``settings.kis_mcp_enabled`` (config 토글)
    - ``reachable``: 외부 서버 실제 접속 가능 여부 (비활성 시 False)
    - ``tools_count``: 노출된 MCP 도구 개수 (접속 실패 시 0)
    - ``error``: 실패 메시지 (성공 시 None)
    """

    enabled: bool
    reachable: bool
    tools_count: int
    error: str | None = None
