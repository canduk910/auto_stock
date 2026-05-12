"""전략 관리 라우트: /api/strategies/*"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.supabase import supabase
from src.db.system_config import get_cash_usage_ratio, set_cash_usage_ratio
from src.engine.scheduler import trading_scheduler
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class WeightsRequest(BaseModel):
    weights: dict[str, float]


class ParamsRequest(BaseModel):
    # tradable_boards (list[str]) / exchange (str) / k_value_* (float) / 기타 수치 모두 허용
    params: dict[str, float | int | str | list[str] | None]


@router.get("", response_model=ApiResponse)
async def get_strategies():
    """전략별 상태를 반환한다."""
    return ApiResponse(
        success=True,
        data=trading_scheduler.registry.get_strategies_status(),
    )


@router.put("/weights", response_model=ApiResponse)
async def update_weights(req: WeightsRequest):
    """전략별 비중을 업데이트하고 즉시 자금을 재분배한다.

    이미 매수된 금액이 있는 전략은 해당 금액 비율 이하로 비중을 낮출 수 없다.
    """
    registry = trading_scheduler.registry
    # 프론트에서 퍼센트(0~100)로 보내면 비율(0~1)로 변환
    weights = {k: v / 100 if v > 1 else v for k, v in req.weights.items()}

    # 매수금액 하한선 검증
    total_asset = sum(s.state.total_investment for s in registry.all())
    if total_asset > 0:
        for sid, new_weight in weights.items():
            strategy = registry.get(sid)
            if not strategy:
                continue
            # 보유 포지션의 매수금액 합산
            invested = sum(
                pos.buy_price * pos.quantity
                for pos in strategy.state.positions.values()
            )
            if invested <= 0:
                continue
            min_weight = invested / total_asset
            if new_weight < min_weight:
                pct = round(min_weight * 100)
                return ApiResponse(
                    success=False,
                    message=f"{strategy.config.name}에 매수 중인 금액({invested:,}원)이 있어 "
                            f"최소 {pct}% 이상이어야 합니다. 보유 종목 매도 후 비중을 줄여주세요.",
                )

    registry.update_weights(weights)

    # 즉시 자금 재분배
    if total_asset > 0:
        registry.allocate_funds(total_asset)

    # DB 영속화 (비율 단위로 저장)
    from src.db.strategy_config import save_weights
    await save_weights(weights)

    return ApiResponse(
        success=True,
        message="비중 업데이트 및 자금 재분배 완료",
        data=registry.get_strategies_status(),
    )


@router.put("/{strategy_id}/params", response_model=ApiResponse)
async def update_params(strategy_id: str, req: ParamsRequest):
    """전략 파라미터를 업데이트한다."""
    registry = trading_scheduler.registry
    strategy = registry.get(strategy_id)
    if not strategy:
        return ApiResponse(success=False, message=f"전략 '{strategy_id}'을 찾을 수 없습니다")

    for key, value in req.params.items():
        if key in strategy.config.params:
            strategy.config.params[key] = value

    # DB 영속화
    from src.db.strategy_config import save_params
    await save_params(strategy_id, strategy.config.params)

    return ApiResponse(
        success=True,
        message=f"{strategy.config.name} 파라미터 업데이트 완료",
        data=registry.get_strategies_status(),
    )


class AutoStartRequest(BaseModel):
    enabled: bool


@router.get("/system/auto-start", response_model=ApiResponse)
async def get_auto_start():
    """자동 매매 시작 설정을 조회한다."""
    result = supabase.table("system_config").select("value").eq("key", "auto_start").execute()
    raw = result.data[0]["value"] if result.data else False
    # JSONB에서 문자열 "true"/"false"로 저장될 수 있으므로 boolean 변환
    enabled = raw is True or raw == "true"
    return ApiResponse(success=True, data={"auto_start": enabled})


@router.put("/system/auto-start", response_model=ApiResponse)
async def set_auto_start(req: AutoStartRequest):
    """자동 매매 시작 설정을 변경한다."""
    supabase.table("system_config").upsert({
        "key": "auto_start",
        "value": req.enabled,
    }, on_conflict="key").execute()
    return ApiResponse(success=True, message=f"자동 매매 시작 {'활성화' if req.enabled else '비활성화'}")


class CashUsageRatioRequest(BaseModel):
    ratio: float


@router.get("/system/cash-usage-ratio", response_model=ApiResponse)
async def get_cash_usage_ratio_endpoint():
    """매매 가용 자금 비율을 조회한다 (J3, 2026-05-12).

    `system_config.cash_usage_ratio` 키. 미설정 시 기본 1.0.
    scheduler `_boot()` 에서 `summary.net_asset × ratio` 로 `allocate_funds()` 호출.
    """
    ratio = await get_cash_usage_ratio()
    return ApiResponse(success=True, data={"ratio": ratio})


@router.put("/system/cash-usage-ratio", response_model=ApiResponse)
async def set_cash_usage_ratio_endpoint(req: CashUsageRatioRequest):
    """매매 가용 자금 비율을 변경한다 (J3, 2026-05-12).

    범위: [0.5, 1.0], 5% 단위 자동 보정. 다음 영업일 `_boot()` 부터 반영.
    """
    try:
        await set_cash_usage_ratio(req.ratio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # 보정된 값을 다시 조회해 응답에 포함
    actual = await get_cash_usage_ratio()
    return ApiResponse(
        success=True,
        data={"ratio": actual},
        message=f"가용 자금 비율 {actual:.2f} 저장 — 다음 영업일부터 반영",
    )
