"""파라미터 추천 모델."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class RecommendationItem(BaseModel):
    id: str
    created_at: str
    target_date: str
    strategy_id: str
    status: Literal["pending", "applied", "rejected", "partial", "expired"]
    current_params: dict
    recommended_params: dict
    applied_params: Optional[dict] = None
    reasoning: Optional[str] = None
    metrics: Optional[dict] = None
    applied_at: Optional[str] = None
    rejected_at: Optional[str] = None
    # Phase J4 (2026-05-12)
    recommended_weight: Optional[float] = None
    code_review_notes: Optional[str] = None
    applied_weight: Optional[float] = None
    # Phase 3 (2026-05-16) — 외부 MCP 백테스트 비교 결과 동봉.
    # null 이면 백테스트 미실행/진행중/실패. UI 가 fallback 처리.
    backtest_summary: Optional[dict] = None


class ApplyRequest(BaseModel):
    keys: list[str] = []
    # Phase J4 (2026-05-12) — recommended_weight 적용 토글.
    # True 이면 strategy_config.weight 를 recommended_weight 로 갱신.
    # recommended_weight 가 null 이면 400 반환.
    apply_weight: bool = False
