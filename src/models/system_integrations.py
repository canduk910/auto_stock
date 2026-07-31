"""사이클 5 (2026-05-17): 외부 통합 토글 API 응답/요청 모델.

사이클 8 (2026-05-18) 확장: 매수 가드 4 모드 + 4 임계값 모델 추가.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class IntegrationToggleStatus(BaseModel):
    """`GET /api/integrations/*` 공통 응답.

    Fields:
        enabled: 현재 유효한 활성 여부 (DB 우선, 없으면 env).
        source: enabled 결정 출처. "db" = DB 값 채택, "env" = .env fallback.
        env_value: settings.* 환경변수 원본 (DB 토글 OFF 시 fallback 후보).
        db_value: system_config DB 원본 (없으면 None).
    """

    enabled: bool
    source: Literal["db", "env"]
    env_value: bool
    db_value: Optional[bool] = None


class IntegrationToggleRequest(BaseModel):
    """`PUT /api/integrations/*` 공통 요청."""

    enabled: bool


# ---------------------------------------------------------------------------
# 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값
# ---------------------------------------------------------------------------
BuyBlockMode = Literal["OFF", "WARN", "SOFT", "HARD"]


class BuyBlockThresholdsModel(BaseModel):
    """4 임계값 응답."""

    vix_threshold: float = Field(default=25.0)
    fg_high_threshold: float = Field(default=85.0)
    fg_low_threshold: float = Field(default=15.0)
    defensive_enabled: bool = Field(default=True)


class BuyBlockStatusResponse(BaseModel):
    """`GET /api/integrations/buy-block` 응답.

    사이클 D (2026-07-31) — `data_available`/`guard_inert` 관찰성 필드 추가
    (레짐 가드 silent inert 가시화). `blocked`/`soft_multiplier`/`reasons` 는
    무변경 — 신규 2 필드는 표시용(프론트 degraded 배너 근거).
    """

    mode: BuyBlockMode
    thresholds: BuyBlockThresholdsModel
    blocked: bool
    reasons: List[str] = Field(default_factory=list)
    soft_multiplier: float = 1.0
    data_available: bool = True
    guard_inert: bool = False


class BuyBlockUpdateRequest(BaseModel):
    """`PUT /api/integrations/buy-block` 요청 — 부분 갱신.

    범위 검증:
    - vix_threshold: [10.0, 50.0]
    - fg_high_threshold: [50.0, 100.0]
    - fg_low_threshold: [0.0, 50.0]
    - mode: BuyBlockMode literal (Pydantic 자동 422)
    """

    mode: Optional[BuyBlockMode] = None
    vix_threshold: Optional[float] = Field(default=None, ge=10.0, le=50.0)
    fg_high_threshold: Optional[float] = Field(default=None, ge=50.0, le=100.0)
    fg_low_threshold: Optional[float] = Field(default=None, ge=0.0, le=50.0)
    defensive_enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# 사이클 23 (2026-05-20) — AI 자문 자동 적용 토글
# ---------------------------------------------------------------------------
class AutoApplyRequest(BaseModel):
    """`PUT /api/integrations/auto-apply` 요청."""

    enabled: bool


class AutoApplyStatus(BaseModel):
    """`GET /api/integrations/auto-apply` 응답."""

    enabled: bool
