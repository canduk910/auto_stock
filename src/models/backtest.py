"""백테스트 관련 Pydantic 모델 (Phase 1 + Phase 2).

Phase 1: McpHealthResponse — `GET /api/backtest/mcp/health` 응답.
Phase 2: BacktestMetrics / BacktestRun / BacktestSummary — 외부 MCP 결과 정규화.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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


class BacktestMetrics(BaseModel):
    """외부 MCP 서버 ``get_backtest_result_tool`` 응답에서 정규화된 8개 메트릭.

    외부 서버 응답 키와 동일. 누락 값은 None 으로 모델 검증 통과.
    """

    total_return_pct: Optional[float] = None
    cagr: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None


class BacktestRun(BaseModel):
    """``backtest_runs`` 테이블 1 row 표상.

    Phase 2 산출. Phase 3 자문 통합에서 `BacktestSummary.current_run` /
    `BacktestSummary.recommended_run` 에 합쳐서 반환된다.
    """

    id: str
    target_date: date
    strategy_id: str
    params_kind: str  # "current" | "recommended"
    params_snapshot: dict[str, Any] = Field(default_factory=dict)
    metrics: Optional[BacktestMetrics] = None
    status: str  # queued | running | completed | failed | skipped
    mcp_job_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BacktestSummary(BaseModel):
    """Phase 3 자문 응답에 동봉되는 비교 요약.

    `current_run` / `recommended_run` 둘 다 None 일 수 있음 (graceful degrade —
    MCP 다운 / 전략 (b) 폴백 미구현 등). `diff` 는 메트릭별 차이값 dict.
    """

    current_run: Optional[BacktestRun] = None
    recommended_run: Optional[BacktestRun] = None
    diff: dict[str, Optional[float]] = Field(default_factory=dict)
