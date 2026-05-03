"""파라미터 추천 라우트: /api/recommendations/*"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.db.parameter_recommendations import (
    get_recommendation,
    list_recommendations,
    update_recommendation_status,
)
from src.db.strategy_config import save_params
from src.engine.scheduler import trading_scheduler
from src.models.recommendation import ApplyRequest
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=ApiResponse)
async def list_recs():
    """최근 30일 + 오늘 pending 추천 목록을 반환한다."""
    rows = await list_recommendations(days=30)
    return ApiResponse(success=True, data=rows)


@router.get("/{rec_id}", response_model=ApiResponse)
async def get_rec(rec_id: str):
    """단일 추천 상세를 반환한다."""
    row = await get_recommendation(rec_id)
    if not row:
        return ApiResponse(success=False, message="추천 레코드를 찾을 수 없습니다")
    return ApiResponse(success=True, data=row)


@router.post("/{rec_id}/apply", response_model=ApiResponse)
async def apply_rec(rec_id: str, req: ApplyRequest):
    """선택한 키만 전략 파라미터에 적용한다.

    - status가 pending|partial이 아니면 거부.
    - body.keys ∩ recommended_params.keys만 추려 적용.
    - 잔여 키 있으면 status='partial', 모두 적용되면 'applied'.
    """
    rec = await get_recommendation(rec_id)
    if not rec:
        return ApiResponse(success=False, message="추천 레코드를 찾을 수 없습니다")

    if rec.get("status") not in ("pending", "partial"):
        return ApiResponse(
            success=False,
            message=f"적용 불가 상태: {rec.get('status')}",
        )

    recommended_params = rec.get("recommended_params") or {}
    valid_keys = set(req.keys) & set(recommended_params.keys())
    if not valid_keys:
        return ApiResponse(
            success=False,
            message="적용 가능한 키가 없습니다",
        )

    strategy_id = rec["strategy_id"]
    registry = trading_scheduler.registry
    strategy = registry.get(strategy_id)
    if not strategy:
        return ApiResponse(
            success=False,
            message=f"전략 '{strategy_id}'을 찾을 수 없습니다",
        )

    # 전략 파라미터에 적용
    for k in valid_keys:
        if k in strategy.config.params:
            strategy.config.params[k] = recommended_params[k]
    await save_params(strategy_id, strategy.config.params)

    # applied_params 누적 머지
    prev_applied = rec.get("applied_params") or {}
    if not isinstance(prev_applied, dict):
        prev_applied = {}
    new_applied = {**prev_applied, **{k: recommended_params[k] for k in valid_keys}}

    # 잔여 키 판정
    remaining = set(recommended_params.keys()) - set(new_applied.keys())
    new_status = "partial" if remaining else "applied"

    updated = await update_recommendation_status(
        rec_id, new_status, applied_params=new_applied,
    )

    logger.info(
        "추천 적용: %s (%s) keys=%s, status=%s",
        rec_id, strategy_id, list(valid_keys), new_status,
    )
    return ApiResponse(
        success=True,
        message=f"{len(valid_keys)}개 파라미터 적용 완료",
        data=updated,
    )


@router.post("/{rec_id}/reject", response_model=ApiResponse)
async def reject_rec(rec_id: str):
    """추천을 전체 거절한다."""
    rec = await get_recommendation(rec_id)
    if not rec:
        return ApiResponse(success=False, message="추천 레코드를 찾을 수 없습니다")

    if rec.get("status") not in ("pending", "partial"):
        return ApiResponse(
            success=False,
            message=f"거절 불가 상태: {rec.get('status')}",
        )

    updated = await update_recommendation_status(rec_id, "rejected")
    return ApiResponse(success=True, message="추천 거절 완료", data=updated)
