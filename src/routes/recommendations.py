"""파라미터 추천 라우트: /api/recommendations/*"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.db.parameter_recommendations import (
    get_recommendation,
    list_recommendations,
    update_recommendation_status,
)
from src.db.strategy_config import save_params, save_weights
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
    """선택한 키 + (옵션) weight 를 전략에 적용한다.

    - status가 pending|partial이 아니면 거부.
    - body.keys ∩ recommended_params.keys 만 추려 적용.
    - body.apply_weight=true 면 strategy_config.weight 도 recommended_weight 로 갱신.
      recommended_weight 가 null 이면 거부 (적용할 weight 없음).
    - 잔여 키 있으면 status='partial', 모두 적용되면 'applied'.

    Phase J4 (2026-05-12): apply_weight 옵션 추가. 자동 적용 절대 없음 — 명시 토글에서만.
    `allocate_funds()` 즉시 재호출 안 함 — 다음 _boot() 에서 자연 반영.
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

    # Phase J4 — weight 적용 사전 검증
    recommended_weight = rec.get("recommended_weight")
    if req.apply_weight:
        if recommended_weight is None:
            return ApiResponse(
                success=False,
                message="적용할 weight 가 없습니다 (recommended_weight=null)",
            )
        # weight 가 있는 경우, 키 없이도 적용 가능 — valid_keys 빈집합 통과
    elif not valid_keys:
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
    applied_count = 0
    for k in valid_keys:
        if k in strategy.config.params:
            strategy.config.params[k] = recommended_params[k]
            applied_count += 1
    if valid_keys:
        await save_params(strategy_id, strategy.config.params)

    # applied_params 누적 머지
    prev_applied = rec.get("applied_params") or {}
    if not isinstance(prev_applied, dict):
        prev_applied = {}
    new_applied = {**prev_applied, **{k: recommended_params[k] for k in valid_keys}}

    # Phase J4 — weight 적용
    applied_weight: float | None = None
    if req.apply_weight and recommended_weight is not None:
        try:
            new_weight = float(recommended_weight)
            await save_weights({strategy_id: new_weight})
            # 메모리 registry 반영 (다음 _boot 까지 일관성)
            strategy.config.weight = new_weight
            applied_weight = new_weight
            logger.info(
                "추천 weight 적용: %s (%s) %.4f → 다음 _boot 에서 자금 재배분",
                rec_id, strategy_id, new_weight,
            )
        except (TypeError, ValueError):
            logger.warning(
                "추천 weight 변환 실패: rec_id=%s val=%r — 적용 건너뜀",
                rec_id, recommended_weight,
            )

    # 잔여 키 판정 (weight 는 상태 판정에서 제외 — params 기준만)
    remaining = set(recommended_params.keys()) - set(new_applied.keys())
    new_status = "partial" if remaining else "applied"

    updated = await update_recommendation_status(
        rec_id, new_status,
        applied_params=new_applied,
        applied_weight=applied_weight,
    )
    # 응답에 applied_weight 가 반영되도록 한 번 더 보장
    if isinstance(updated, dict) and applied_weight is not None:
        updated.setdefault("applied_weight", applied_weight)

    logger.info(
        "추천 적용: %s (%s) keys=%s, status=%s, apply_weight=%s",
        rec_id, strategy_id, list(valid_keys), new_status, req.apply_weight,
    )

    msg_parts = []
    if applied_count > 0:
        msg_parts.append(f"{applied_count}개 파라미터 적용")
    if applied_weight is not None:
        msg_parts.append(f"weight={applied_weight:.2f} 적용")
    message = " · ".join(msg_parts) if msg_parts else "변경사항 없음"

    return ApiResponse(
        success=True,
        message=message,
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
