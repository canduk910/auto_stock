"""전략 관리 라우트: /api/strategies/*"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from src.db import system_config as _system_config
from src.db._kst import KST
from src.db.system_config import get_cash_usage_ratio, set_cash_usage_ratio
from src.db.trade_history import get_trade_pairs
from src.engine import param_catalog as pc
from src.engine.param_validation import BUDGET_KEYS, MAX_BUDGET_PRODUCT, validate_params
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
    """전략 파라미터 부분 dict.

    ⚠️ 유니언에서 **`bool` 이 맨 앞**이어야 한다. pydantic 2.11.2 실측 —
    `float | int | str | list[str] | None` 은 `True` 를 `1.0(float)` 으로 강등하고
    (bool 키 저장이 전건 실패한다), `bool` 을 앞에 두면 `True → True` 이면서
    `5 → 5(int)` 도 유지된다(정수가 실수로 강등되면 수량이 `"2.0"` 으로 나간다).
    """

    # bool → tradable_boards (list[str]) / exchange (str) / k_value_* (float) / 정수 순
    params: dict[str, bool | float | int | str | list[str] | None]


@router.get("", response_model=ApiResponse)
async def get_strategies():
    """전략별 상태를 반환한다."""
    return ApiResponse(
        success=True,
        data=trading_scheduler.registry.get_strategies_status(),
    )


# ───────────────────────────────────────────────────────────────────────────
# 파라미터 카탈로그 스키마 (사이클 278)
# ───────────────────────────────────────────────────────────────────────────
def _spec_to_dict(spec: pc.ParamSpec) -> dict[str, Any]:
    """`ParamSpec` → JSON. **필드를 임의로 빼지 않는다** — 화면이 키를 하드코딩하지
    않으려면 라벨·단위·범위·선택지·배지 근거가 전부 응답에 있어야 한다.
    """
    return {
        "key": spec.key,
        "label_ko": spec.label_ko,
        "group": spec.group,
        "type": spec.type,
        "min": spec.min,
        "max": spec.max,
        "step": spec.step,
        "unit": spec.unit,
        "editable": spec.editable,
        "risk": spec.risk,
        "auto_tunable": spec.auto_tunable,
        "deprecated": spec.deprecated,
        "deprecated_for": list(spec.deprecated_for),
        "range_src": spec.range_src,
        "pattern": spec.pattern,
        "min_items": spec.min_items,
        "forbidden_choices": [
            {"strategy_id": f.strategy_id, "value": f.value, "reason": f.reason}
            for f in spec.forbidden_choices
        ],
        "choices": [
            {
                "value": c.value,
                "label_ko": c.label_ko,
                "deprecated": c.deprecated,
                "help": c.help,
            }
            for c in spec.choices
        ],
        "applies_to": list(spec.applies_to),
        "help": spec.help,
    }


def _strategy_schema_row(strategy) -> dict[str, Any]:
    """전략 1행 — `keys`(카탈로그) · `params`(현재값) · `defaults`(코드 기본값).

    ⚠️ `defaults` 는 클래스 `DEFAULT_PARAMS` 의 **깊은 복사본**이다. 응답을 만드는
    과정에서 `DEFAULT_PARAMS` 나 `config.params` 가 변경되면 안 된다 — 참조를 그대로
    실으면 상위 계층의 어떤 변형이 전략의 기본값을 조용히 덮는다.
    """
    sid = strategy.strategy_id
    defaults = copy.deepcopy(dict(getattr(type(strategy), "DEFAULT_PARAMS", {}) or {}))
    current = copy.deepcopy(dict(getattr(strategy.config, "params", {}) or {}))
    keys = list(pc.keys_for_strategy(sid))
    return {
        "strategy_id": sid,
        "name": getattr(strategy.config, "name", sid),
        "enabled": bool(getattr(strategy.config, "enabled", False)),
        "keys": keys,
        "params": {k: current.get(k, defaults.get(k)) for k in keys},
        "defaults": {k: defaults.get(k) for k in keys},
        "deprecated_for_keys": [s.key for s in pc.PARAM_SPECS if sid in s.deprecated_for],
    }


def _build_params_schema(registry) -> dict[str, Any]:
    return {
        "catalog_version": pc.CATALOG_VERSION,
        "groups": [
            {"id": gid, "label_ko": label, "description": desc}
            for gid, label, desc in pc.GROUPS
        ],
        "types": list(pc.TYPES),
        "risks": list(pc.RISKS),
        "units": list(pc.UNITS),
        "params": [_spec_to_dict(s) for s in pc.PARAM_SPECS],
        "strategies": [_strategy_schema_row(s) for s in registry.all()],
        "invariants": {
            "budget": {
                "expr": f"{BUDGET_KEYS[0]} * {BUDGET_KEYS[1]} <= {MAX_BUDGET_PRODUCT}",
                "keys": list(BUDGET_KEYS),
                "enforced": True,
                "description": pc.BUDGET_INVARIANT,
            },
            "order": [
                {
                    "lo_key": inv.lo_key,
                    "hi_key": inv.hi_key,
                    "strategies": list(inv.strategies),
                    "enforced": inv.enforced,
                    "consequence": inv.consequence,
                }
                for inv in pc.ORDER_INVARIANTS
            ],
        },
    }


@router.get("/params-schema", response_model=ApiResponse)
async def get_params_schema():
    """파라미터 카탈로그 전체 + 전략별 적용 키·현재값·기본값을 반환한다 (사이클 278).

    화면은 **이 한 응답**으로 편집 폼을 렌더한다 — 키·라벨·단위·범위·선택지를 프론트에
    하드코딩하면 지금의 재드리프트(99키 중 73키가 화면 밖)가 그날부터 다시 시작된다.
    현재값을 별도 `GET /api/strategies`(staleTime 15s)에서 가져오면 diff 미리보기가
    낡은 기준값으로 계산되므로 현재값·기본값을 여기 함께 싣는다.
    """
    return ApiResponse(success=True, data=_build_params_schema(trading_scheduler.registry))


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
    """전략 파라미터를 업데이트한다 (사이클 278 — 검증 강화).

    종전에는 `if key in strategy.config.params` 로 기존 키만 반영하고 나머지를
    **조용히 버렸다** — 오타·신규 키가 성공 응답을 받고도 무시됐고, 범위 밖 값·자료형
    오류는 그대로 저장돼 다음 부팅에서야(또는 영원히) 드러났다. 이제 `validate_params`
    가 미지 키·읽기 전용 키·자료형·선택지·정규식·범위·예산 불변식을 검사하고,
    **오류가 하나라도 있으면 아무것도 저장하지 않는다**(all-or-nothing).

    보존되는 계약:

    * 요청에 없는 키는 그대로 남는다(부분 dict **병합**, 전체 덮어쓰기 아님).
    * `save_params` 는 병합된 **전체 dict** 로 호출된다.
    * 알 수 없는 전략 id 는 422 가 아니라 **200 + `success=false`**(기존 호출자 보존).
    * identity(리스크 정체성 상수) 키도 API 로는 저장된다 — 2단계 확인은 *화면의 절차*
      이지 서버의 거부가 아니다. 서버가 막으면 장중 긴급 롤백(PUT 이 유일 경로)이
      함께 막힌다.
    """
    registry = trading_scheduler.registry
    strategy = registry.get(strategy_id)
    if not strategy:
        return ApiResponse(success=False, message=f"전략 '{strategy_id}'을 찾을 수 없습니다")

    result = validate_params(strategy_id, strategy.config.params, req.params)
    if result.errors:
        logger.warning(
            "[param_validation_rejected] strategy=%s codes=%s keys=%s",
            strategy_id,
            [e.code for e in result.errors],
            [e.key for e in result.errors],
        )
        raise HTTPException(status_code=422, detail=[e.to_dict() for e in result.errors])

    strategy.config.params.update(result.accepted)

    # DB 영속화 — 병합된 전체 dict
    from src.db.strategy_config import save_params
    await save_params(strategy_id, strategy.config.params)

    return ApiResponse(
        success=True,
        message=f"{strategy.config.name} 파라미터 업데이트 완료",
        data={
            "applied": dict(result.accepted),
            "warnings": [w.to_dict() for w in result.warnings],
            "strategies": registry.get_strategies_status(),
        },
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
