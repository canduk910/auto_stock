"""사이클 5 (2026-05-17): 외부 통합 토글 API 응답/요청 모델."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


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
