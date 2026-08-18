"""전략 관리 라우트: /api/strategies/*"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from src.db import system_config as _system_config
from src.db._kst import KST
from src.db.system_config import get_cash_usage_ratio, set_cash_usage_ratio
from src.db.trade_history import get_trade_pairs
from src.engine.scheduler import trading_scheduler
from src.engine.te_metrics import compute_te_rr
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# 비중 합(Σ) 불변식 허용오차 — 프론트 반올림 잔차 흡수용
_WEIGHT_SUM_TOLERANCE = 1e-3


class WeightsRequest(BaseModel):
    """전략별 비중. **단위 = 비율(0.0~1.0)**.

    ⚠️ 퍼센트(0~100) 금지. 값 크기로 단위를 추론하던 종전 규약(`v / 100 if v > 1`)은
    1%(=정수 1)를 100%로 저장하는 결함이라 2026-08-18 폐기했다.
    `GET /api/strategies` 의 weight 도 비율이므로 GET↔PUT 왕복이 항등이다.
    """

    weights: dict[str, float]

    @field_validator("weights")
    @classmethod
    def _validate_ratio_range(cls, v: dict[str, float]) -> dict[str, float]:
        for sid, w in v.items():
            fw = float(w)
            if not (0.0 <= fw <= 1.0):
                raise ValueError(
                    f"비중은 비율(0.0~1.0)이어야 합니다: {sid}={w}"
                    " — 퍼센트(0~100) 형식은 지원하지 않습니다"
                )
        return v


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


_TE_CACHE_TTL = 300.0
_te_cache: dict[int, tuple[float, list[dict]]] = {}


def invalidate_te_cache() -> None:
    """TE/RR 캐시 무효화 (테스트/토글용, convention: invalidate_*)."""
    _te_cache.clear()


@router.get("/te", response_model=ApiResponse)
async def get_strategies_te(months: int = 3):
    """전략별 TE(예지치)/RR(손익비) 최근 N개월 지표를 반환한다 (관찰 전용, 사이클 F).

    5분 TTL 프로세스 캐시(장중 DB 부하 완화, months 키). 전략별 계산 실패는
    해당 전략만 빈 디폴트로 격리 — 나머지 전략은 정상 진행(F-B8).
    """
    cached = _te_cache.get(months)
    if cached is not None and time.monotonic() < cached[0]:
        return ApiResponse(success=True, data=cached[1])

    window_days = months * 30
    now = datetime.now(KST)

    data: list[dict] = []
    for strategy in trading_scheduler.registry.all():
        sid = strategy.strategy_id
        try:
            pairs = await get_trade_pairs(strategy=sid)
            metrics = compute_te_rr(pairs, now=now, window_days=window_days, strategy_id=sid)
        except Exception:
            metrics = compute_te_rr([], now=now, window_days=window_days, strategy_id=sid)
        data.append(asdict(metrics))

    _te_cache[months] = (time.monotonic() + _TE_CACHE_TTL, data)
    return ApiResponse(success=True, data=data)


@router.put("/weights", response_model=ApiResponse)
async def update_weights(req: WeightsRequest):
    """전략별 비중을 업데이트하고 즉시 자금을 재분배한다.

    이미 매수된 금액이 있는 전략은 해당 금액 비율 이하로 비중을 낮출 수 없다.
    """
    registry = trading_scheduler.registry
    # 단위 = 비율(0~1). 값 크기 기반 추론 변환 금지 (2026-08-18 결함 — 1%가 100%로 저장됨)
    weights = {k: float(v) for k, v in req.weights.items()}

    # Σ 불변식 — 오염 payload 는 저장(메모리/DB) *전에* 거부한다.
    # 부분 payload(Σ<1)는 통과시키는 비대칭 가드(복구 저장 보존).
    total_weight_req = sum(weights.values())
    if total_weight_req > 1.0 + _WEIGHT_SUM_TOLERANCE:
        logger.warning(
            "[weight_unit_violation] sum=%.4f payload=%s", total_weight_req, weights,
        )
        return ApiResponse(
            success=False,
            message=(
                f"비중 합이 100%를 초과합니다 (현재 {total_weight_req * 100:.1f}%). "
                "비중은 비율(0.0~1.0)로 전송해야 하며 합이 1.0 을 넘을 수 없습니다."
            ),
        )

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
    enabled = await _system_config.get_auto_start()
    return ApiResponse(success=True, data={"auto_start": enabled})


@router.put("/system/auto-start", response_model=ApiResponse)
async def set_auto_start(req: AutoStartRequest):
    """자동 매매 시작 설정을 변경한다."""
    await _system_config.set_auto_start(req.enabled)
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
