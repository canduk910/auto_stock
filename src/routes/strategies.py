"""전략 관리 라우트: /api/strategies/*"""

from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, field_validator

from src.db import system_config as _system_config
from src.db._kst import KST, now_kst_iso
from src.db.system_config import get_cash_usage_ratio, set_cash_usage_ratio
from src.db.trade_history import get_trade_pairs
from src.engine import cost_overlay
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
#: 2차 보완 B4 — 비용 조회가 하나라도 실패한 계산은 짧게만 캐시한다(그 계산이 비용 없이
#: 세전으로 내려간 결과이기 때문 — 비용 DB 가 살아나면 빨리 세후 값으로 돌아와야 한다).
_TE_CACHE_FAILURE_TTL = 60.0
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
    any_costs_unavailable = False
    for strategy in trading_scheduler.registry.all():
        sid = strategy.strategy_id
        try:
            pairs = await get_trade_pairs(strategy=sid)
        except Exception:
            metrics = compute_te_rr([], now=now, window_days=window_days, strategy_id=sid)
            data.append(asdict(metrics))
            any_costs_unavailable = True
            continue

        # 2차 보완 B4 — 사용자 결정 10-08 Q2: 판정을 net 기준으로 내리려면 compute_te_rr
        # 가 보기 전에 페어에 net_profit_loss/net_profit_rate 를 얹어야 한다. `overlay_pairs`
        # 는 **별도 try** 로 불러 그 실패(None 반환·예외)가 이 전략의 나머지 지표(n·세전
        # 합 등)까지 비우지 않게 한다 — 실패하면 `costs_available=False` 로 compute_te_rr
        # 에 넘겨 net 전용 칸(`realized_net_sum_krw`·`fee_sum`·`tax_sum`)만 None 이 되고
        # 판정은 페어가 들고 온 값(세전 폴백) 그대로 진행한다.
        costs_available = True
        try:
            overlaid = await cost_overlay.overlay_pairs(pairs)
            if overlaid is None:
                costs_available = False
        except Exception:
            logger.warning(
                "[cost_overlay_unavailable] /api/strategies/te 실비용 조회 실패 sid=%s", sid,
                exc_info=True,
            )
            costs_available = False

        if not costs_available:
            any_costs_unavailable = True

        metrics = compute_te_rr(
            pairs, now=now, window_days=window_days, strategy_id=sid,
            costs_available=costs_available,
        )
        data.append(asdict(metrics))

    # 2차 보완 B4 — 비용 조회가 하나라도 실패했으면 짧게만 캐시한다(세전 폴백 결과를
    # 오래 남기지 않는다). `invalidate_te_cache()` 는 테스트/토글용으로 그대로 둔다.
    ttl = _TE_CACHE_FAILURE_TTL if any_costs_unavailable else _TE_CACHE_TTL
    _te_cache[months] = (time.monotonic() + ttl, data)
    return ApiResponse(success=True, data=data)


async def _held_tickers_from_db(strategy_id: str) -> list[str]:
    """그 전략이 **DB 에** 들고 있는 종목 (cycle325).

    🔴 메모리(`state.positions`)가 아니라 DB 를 보는 이유 = 부팅 전에는 메모리가 비어 있다.
    주말 대기 중 실측(2026-09-20)으로 `Σ total_investment = 0` 이라 아래 하한선 검증이
    통째로 건너뛰어지는 것을 확인했다 — 그 창에서 메모리를 보면 똑같이 뚫린다.
    """
    from src.db import positions as _positions

    try:
        rows = await _positions.load_all()
    except Exception:
        # DB 를 못 읽는 상황(풀 미초기화 등)은 프로덕션에서는 이미 매매가 못 도는 상태다.
        # 여기서 무조건 거부하면 DB 없는 맥락(계약 테스트 등)까지 막으므로,
        # **메모리로 물러서되 그 사실을 남긴다.** 잔여 사각 = DB 불가 + 부팅 전 + 비중 0
        # 요청이 겹치는 창(메모리가 비어 통과한다). 그 창은 `[weight_zero_probe_degraded]` 로 보인다.
        logger.warning(
            "[weight_zero_probe_degraded] sid=%s — DB 보유 조회 불가, 메모리로 판정", strategy_id,
        )
        return []
    return [
        str(r.get("ticker"))
        for r in rows
        if str(r.get("strategy_id") or "") == strategy_id
    ]


@router.put("/weights", response_model=ApiResponse)
async def update_weights(req: WeightsRequest):
    """전략별 비중을 업데이트하고 즉시 자금을 재분배한다.

    이미 매수된 금액이 있는 전략은 해당 금액 비율 이하로 비중을 낮출 수 없다.

    🔴 **비중 0 은 「매수만 멈추기」가 아니다** — `registry.update_weights` 가
    `config.enabled = weight > 0` 을 자동 토글하고, `risk.on_tick` 은 `enabled()` 만
    순회하므로 그 전략의 보유 종목은 **손절·트레일링·익일청산·15:20 청산이 전부 멈춘다.**
    그래서 보유가 있으면 비중 0 을 거부한다(루트 `CLAUDE.md` 「절대 깨지 말 것」).
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

    # 🔴 비중 0 가드 (cycle325) — **아래 `if total_asset > 0` 게이트보다 앞**이다.
    # 그 게이트 안에 넣으면 부팅 전(예산 합 0)에 통째로 건너뛰어져 고친 것이 아무 일도
    # 하지 않는다. 비중 0 = 비활성화 = 손절 정지이므로 예산과 무관하게 판정해야 한다.
    for sid, new_weight in weights.items():
        if new_weight > 0:
            continue
        strat = registry.get(sid)
        if not strat:
            continue
        # DB(부팅 전에도 유효) ∪ 메모리(DB 불가 시 폴백) — 둘 중 하나라도 보유면 막는다.
        held = set(await _held_tickers_from_db(sid))
        try:
            held |= {str(t) for t in (strat.state.positions or {})}
        except Exception:
            pass
        if held:
            logger.warning(
                "[weight_zero_guard] sid=%s held=%d — 비중 0 거부(손절 정지 차단)",
                sid, len(held),
            )
            return ApiResponse(
                success=False,
                message=(
                    f"{sid} 에 보유 종목 {len(held)}건이 있어 비중을 0 으로 내릴 수 없습니다. "
                    "비중 0 은 전략을 비활성화하고 그 순간 보유 종목의 손절·트레일링·"
                    "익일청산이 멈춥니다. 먼저 보유를 청산한 뒤 내려 주세요. "
                    "매수만 줄이려면 position_ratio / max_positions 를 쓰세요."
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
    # cycle399 — 비중 0 인데 메모리에서 켜져 있는 전략 = `update_weights` 가 섀도라서 켜짐을
    # 지킨 전략이다. DB 에도 같은 켜짐을 적어야 다음 재시작에 꺼지지 않는다. 섀도가 없으면
    # 호출 모양은 그대로다.
    keep_enabled = {
        sid for sid, w in weights.items()
        if w <= 0 and (st := registry.get(sid)) is not None and st.config.enabled is True
    }
    if keep_enabled:
        await save_weights(weights, keep_enabled=keep_enabled)
    else:
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
    await save_params(
        strategy_id, strategy.config.params,
        enabled=getattr(strategy.config, "enabled", None),
        weight=getattr(strategy.config, "weight", None),
    )

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


# ───────────────────────────────────────────────────────────────────────────
# GET /monitor — 전략별 진행상황 읽기 전용 스냅샷 (cycle414)
# ───────────────────────────────────────────────────────────────────────────
#
# 명세 = `_workspace/red/cycle414/monitor_spec.md` §3. 대시보드가 5~10초마다 때리는
# **운영 엔진 메모리 창**이다 — 후보 깔때기 중간 수·보유 방어선 구성·래치·오늘
# 거르기 사유·시장 유닛 스냅샷은 여기서만 열린다. 호출 한 번이 래치를 pop 하거나
# (`_latch_entry`) 캡의 날짜를 넘기면(`should_emit`/`count_matching`) 화면을 여는
# 것만으로 손절·매수 판정이 바뀐다 — 그래서 아래 `_monitor*` 함수들은 **읽기만**
# 한다(캡의 `_day`/`_emitted` 를 직접 읽고, `should_emit`/`mark_emitted`/
# `_latch_entry`/`_market_unit_view` 어느 것도 부르지 않는다). 순수성은
# `tests/unit/ast/test_cycle414_monitor_purity.py` 가 AST 로 강제한다(cycle412 G1
# 선례와 같은 패턴) — 이름이 `_monitor` 로 시작하는 모듈 함수 전부가 그 범위다.
#
# 캐시(exit-lines G1 과 같은 꼴) — `global` 재바인딩은 `_monitor_cache` 하나만.
_MONITOR_CACHE_TTL_S = 2.0
_monitor_cache: tuple[float, str] | None = None
_monitor_clock = time.monotonic

#: 시장 유닛 표시 대상 — 터틀 4전략 + etf_trend(§2.4). 그 밖(VB·모멘텀·LTV)은 None.
_MONITOR_MU_SIDS = frozenset({
    "kojiro", "donchian_swing", "vcp_breakout", "bull_flag_breakout", "etf_trend",
})


def _monitor_cap_emitted(cap, today_iso):
    """`KstDailyEmitCap` 의 `_emitted` — `_day` 가 오늘(KST)이 아니면 빈 집합.

    `should_emit`/`_sync_day` 를 부르지 않는다 — 캡을 고치지 않고 읽기만 한다
    (명세 §3.3 「캡 날짜 처리」). 오늘이 아닌 캡은 "오늘 기록 없음" 으로 보되
    객체는 그대로 둔다(어제 항목을 지우지 않는다).
    """
    day = getattr(cap, "_day", None) if cap is not None else None
    emitted = getattr(cap, "_emitted", None) if cap is not None else None
    emitted = emitted if isinstance(emitted, set) else set()
    return emitted if day == today_iso else set()


def _monitor_cap_day(cap):
    """캡의 `_day` 그대로 — 오늘이 아니어도 그 값 자체는 보여준다(화면이 「언제
    기록인지」 알게)."""
    return getattr(cap, "_day", None) if cap is not None else None


def _monitor_tick_iso(ts):
    return ts.isoformat() if ts is not None else None


def _monitor_prepare(strategy):
    """`_live_prepare_meta` → ISO(KST) 문자열. 없으면 `None`(준비 기록이 없는
    전략은 null — 0 이나 빈 dict 로 메우지 않는다)."""
    meta = getattr(strategy, "_live_prepare_meta", None)
    if not isinstance(meta, dict):
        return None
    as_of = meta.get("as_of")
    started = meta.get("started_at")
    finished = meta.get("finished_at")
    return {
        "as_of": as_of.isoformat() if as_of is not None else None,
        "phase": meta.get("phase"),
        "started_at": started.isoformat() if started is not None else None,
        "finished_at": finished.isoformat() if finished is not None else None,
        "ok": meta.get("ok"),
    }


def _monitor_funnel(strategy):
    """`_funnel_steps` 5키만(생존·탈락 목록은 5초 폴링에 싣지 않는다, 명세 §2.5)."""
    steps = getattr(strategy, "_funnel_steps", None)
    steps = steps if isinstance(steps, list) else []
    return [
        {
            "step_no": step.get("step_no"),
            "step_name": step.get("step_name"),
            "step_conditions": step.get("step_conditions"),
            "survived_count": step.get("survived_count"),
            "excluded_count": step.get("excluded_count"),
        }
        for step in steps if isinstance(step, dict)
    ]


def _monitor_market_unit(strategy, today_date):
    """시장 유닛(§2.4) — 터틀 4전략·etf 만, 오늘 스냅샷 `_market_unit_snaps[오늘]`
    그대로(어제 것으로 메우지 않는다). 그 밖 전략은 `None`."""
    if strategy.strategy_id not in _MONITOR_MU_SIDS:
        return None
    from src.engine import market_unit

    mode, _valid = market_unit.normalize_mode(strategy.config.params.get(market_unit.MODE_KEY))
    snaps = getattr(strategy, "_market_unit_snaps", None)
    snap = snaps.get(today_date) if isinstance(snaps, dict) else None
    if snap is None:
        return {"mode": mode, "ok": False, "reason": "not_computed"}
    bar_date = getattr(snap, "bar_date", None)
    return {
        "mode": mode,
        "ok": bool(getattr(snap, "ok", False)),
        "m": getattr(snap, "m", None),
        "state": getattr(snap, "state", None),
        "bar_date": bar_date.isoformat() if bar_date is not None else None,
        "reason": getattr(snap, "reason", None),
    }


def _monitor_skip_counts(parsed):
    reasons = sorted({reason for _, reason in parsed})
    return {reason: sum(1 for _, r in parsed if r == reason) for reason in reasons}


def _monitor_skip_by_ticker(parsed):
    tickers = sorted({ticker for ticker, _ in parsed})
    return {ticker: sorted({r for t, r in parsed if t == ticker}) for ticker in tickers}


def _monitor_skips_result(parsed, day):
    return {
        "known": True, "day": day,
        "counts": _monitor_skip_counts(parsed),
        "by_ticker": _monitor_skip_by_ticker(parsed),
    }


def _monitor_cap_pairs_split(cap, today_iso):
    """`"ticker|reason"` 키 캡(etf `_skip_logged`) → `(ticker, reason)` 목록."""
    active = _monitor_cap_emitted(cap, today_iso)
    return [tuple(key.split("|", 1)) for key in active if isinstance(key, str) and "|" in key]


def _monitor_skips(strategy, today_iso, today_date):
    """오늘 거르기 사유(§2.7·§3.3) — 종목별 사유 사상. 캡이 없는 전략은
    `{"known": False}`(0 으로 쓰지 않는다)."""
    sid = strategy.strategy_id
    if sid == "etf_trend":
        cap = getattr(strategy, "_skip_logged", None)
        return _monitor_skips_result(_monitor_cap_pairs_split(cap, today_iso), _monitor_cap_day(cap))
    if sid == "donchian_swing":
        lot_zero_cap = getattr(strategy, "_kk_lot_zero_logged", None)
        entry_cap = getattr(strategy, "_kk_entry_cap_logged", None)
        lot_zero = _monitor_cap_emitted(lot_zero_cap, today_iso)
        entry = _monitor_cap_emitted(entry_cap, today_iso)
        parsed = [(t, "kk_lot_zero") for t in lot_zero] + [(t, "daily_entry_cap") for t in entry]
        return _monitor_skips_result(parsed, _monitor_cap_day(lot_zero_cap))
    if sid in ("vcp_breakout", "bull_flag_breakout"):
        gate_day = getattr(strategy, "_gate_emit_day", None)
        capped = getattr(strategy, "_gate_emit_capped", None)
        capped = capped if isinstance(capped, set) else set()
        active = capped if gate_day == today_date else set()
        day = gate_day.isoformat() if gate_day is not None else None
        return _monitor_skips_result(list(active), day)
    return {"known": False}


def _monitor_paused_skips(strategy, today_iso):
    """`_buy_paused_logged` 의 `"skip|<ticker>"` 키(오늘) — 멈춘 동안 평가된 후보."""
    active = _monitor_cap_emitted(getattr(strategy, "_buy_paused_logged", None), today_iso)
    return sorted({key.split("|", 1)[1] for key in active if isinstance(key, str) and key.startswith("skip|")})


def _monitor_shadow_buys(strategy, today_iso):
    """`_shadow_logged` 의 `"buy|<ticker>"` 키(오늘) — 실전이었으면 샀을 종목."""
    active = _monitor_cap_emitted(getattr(strategy, "_shadow_logged", None), today_iso)
    return sorted({key.split("|", 1)[1] for key in active if isinstance(key, str) and key.startswith("buy|")})


def _monitor_ticks(ticker_last_tick, tick_volume_mod, tickers):
    """후보 ∪ 보유 종목의 마지막 틱 시각·실측 거래량(§2.6). 미관측은 `None`(0 이
    아니다 — `tick_volume` sentinel 규약)."""
    return {
        t: {
            "last_tick_at": _monitor_tick_iso(ticker_last_tick.get(t)),
            "acml_vol": tick_volume_mod.get_observed_acml_vol(t),
        }
        for t in tickers
    }


def _monitor_cluster_partners(strategy, ticker):
    """etf 묶음(§4.1) — 보유∪주문중∪당일매도 풀에서 이 종목과 상관 쌍인 상대."""
    pairs = getattr(strategy, "_cluster_pairs", None)
    pairs = pairs if isinstance(pairs, set) else set()
    if not pairs:
        return []
    pool = set(strategy.state.positions) | set(strategy.state.pending_buys) | set(strategy.state.sold_today)
    return sorted(other for other in pool if other != ticker and frozenset({ticker, other}) in pairs)


def _monitor_candidates_etf(strategy, cands):
    return {
        t: {
            **info,
            "design_qty": strategy._pure_turtle_qty(info.get("prev_close", 0), info),
            "cluster_partners": _monitor_cluster_partners(strategy, t),
            "cluster_blocked": strategy._cluster_blocked(t),
        }
        for t, info in cands.items()
    }


def _monitor_donchian_candidate(strategy, ticker, info):
    prev_close = info.get("prev_close", 0)
    atr = info.get("atr", 0)
    r = strategy._kk_r(prev_close, atr)
    lot = strategy._kk_design_lot(prev_close, ticker, 1.0)
    return {
        **info,
        "r_won": r,
        "r_pct": (r / prev_close * 100) if prev_close else None,
        "design_lot": lot[0],
    }


def _monitor_candidates_donchian(strategy, cands):
    return {t: _monitor_donchian_candidate(strategy, t, info) for t, info in cands.items()}


def _monitor_latch_armed_at(entry, today_date):
    """오늘(`armed_date`) 무장 래치만 ISO(KST) 시각 — 지난 래치는 `None`(pop 금지,
    객체는 그대로 둔다)."""
    if not isinstance(entry, dict):
        return None
    if entry.get("armed_date") != today_date:
        return None
    armed_at = entry.get("armed_at")
    return armed_at.isoformat() if armed_at is not None else None


def _monitor_vcp_crossing(strategy, today_date):
    """VCP 전용 — `breakout_event_summary`(순수 읽기) 의 종목별 첫 교차·최고가."""
    summary = strategy.breakout_event_summary(today_date)
    per_ticker = summary.get("per_ticker") if isinstance(summary, dict) else None
    per_ticker = per_ticker if isinstance(per_ticker, dict) else {}
    return {
        t: {"first_cross_at": ent.get("first_cross_at"), "max": ent.get("max")}
        for t, ent in per_ticker.items()
    }


def _monitor_candidates_latch(strategy, cands, today_date):
    sid = strategy.strategy_id
    latch = getattr(strategy, "_vol_latch", None)
    latch = latch if isinstance(latch, dict) else {}
    crossing = _monitor_vcp_crossing(strategy, today_date) if sid == "vcp_breakout" else {}
    return {
        t: {
            **info,
            "latch_armed_at": _monitor_latch_armed_at(latch.get(t), today_date),
            **crossing.get(t, {}),
        }
        for t, info in cands.items()
    }


def _monitor_candidates(strategy, cands, today_date):
    """전략별 후보 칸(§4) — etf/donchian/VCP·BFB 는 고유 키, 그 밖은 원본 그대로."""
    sid = strategy.strategy_id
    if sid == "etf_trend":
        return _monitor_candidates_etf(strategy, cands)
    if sid == "donchian_swing":
        return _monitor_candidates_donchian(strategy, cands)
    if sid in ("vcp_breakout", "bull_flag_breakout"):
        return _monitor_candidates_latch(strategy, cands, today_date)
    return {t: dict(info) for t, info in cands.items()}


def _monitor_holding_etf(strategy, ticker, pos):
    """etf 보유 방어선(§4.1 (f)) — 구성 선은 엔진 함수(`etf_trend_core`)로만 계산,
    실효 손절선은 `get_effective_stop_price` 엔진 값 그대로."""
    from src.engine import etf_trend_core as core

    params = strategy.config.params
    n = strategy._entry_atr.get(ticker)
    hsb = strategy._hsb_closed.get(ticker)
    bars = strategy._bars_since_buy.get(ticker, 0)
    chan = strategy._channel_low.get(ticker)
    e = pos.buy_price
    hard = core.hard_stop(
        e, n, backstop_pct=float(params["turtle_backstop_pct"]), stop_atr=float(params["stop_atr"]),
    )
    breakeven_atr = float(params["breakeven_promote_atr"])
    trail_atr = float(params["atr_trail_mult"])
    has_trail_inputs = hsb is not None and n
    trail = (hsb - trail_atr * n) if has_trail_inputs else None
    breakeven = e if (has_trail_inputs and hsb >= e + breakeven_atr * n) else None
    channel = chan if bars >= 1 else None
    min_bars = int(params["breakout_fail_min_bars"])
    return {
        "entry_n": n, "hsb_closed": hsb, "bars_since_buy": bars,
        "lines": {"hard": hard, "breakeven": breakeven, "trail": trail, "channel": channel},
        "breakout_fail": {"line": strategy._breakout_line.get(ticker), "active": bars >= min_bars},
        "effective_stop": strategy.get_effective_stop_price(ticker),
    }


def _monitor_holding_donchian(strategy, ticker, pos, today_date):
    """돈키언 보유 사다리(§4.2 (c)) — 손절·무장·무장가는 exit-lines 와 같은 헬퍼
    (`_exit_lines_kk`/`_kk_exit_lines`)로 계산해 두 출처가 어긋나지 않게 한다."""
    from src.routes.balance import _exit_lines_kk

    atr = strategy._entry_atr.get(ticker, 0)
    r = strategy._kk_r(pos.buy_price, atr)
    stop, armed, channel = strategy._kk_exit_lines(ticker, pos)
    _armed_dup, arm_price = _exit_lines_kk(strategy, "donchian_swing", ticker, pos)
    min_r = strategy._kk("kk_time_exit_min_r")
    target_1r = pos.buy_price + min_r * r
    days_held, days_fallback = strategy._business_days_held(pos.buy_date, today_date)
    return {
        "r_won": r, "stop": stop, "armed": armed, "channel": channel,
        "arm_price": arm_price, "target_1r": target_1r,
        "reached_1r": pos.high_since_buy >= target_1r,
        "days_held": days_held, "days_fallback": days_fallback,
        "time_exit_bars": strategy._kk("kk_time_exit_bars"),
        "max_hold_bars": strategy._kk("kk_max_hold_bars"),
    }


def _monitor_holding_generic(strategy, ticker):
    return {"effective_stop": strategy.get_effective_stop_price(ticker)}


def _monitor_holdings(strategy, positions, today_date):
    """전략별 보유 방어선(§4) — etf/donchian 는 고유 사다리, 그 밖은 실효 손절선만."""
    sid = strategy.strategy_id
    if sid == "etf_trend":
        return {t: _monitor_holding_etf(strategy, t, pos) for t, pos in positions.items()}
    if sid == "donchian_swing":
        return {t: _monitor_holding_donchian(strategy, t, pos, today_date) for t, pos in positions.items()}
    return {t: _monitor_holding_generic(strategy, t) for t in positions}


def _monitor_extra(strategy, today_date):
    """전략 고유 보조 값 — donchian 하루 신규 진입 게이지(§4.2 (c))만, 그 밖은 `{}`."""
    if strategy.strategy_id != "donchian_swing":
        return {}
    positions = strategy.state.positions
    count = sum(1 for p in positions.values() if p.buy_date == today_date)
    count = count + len(strategy.state.pending_buys)
    return {"daily_entries": {"count": count, "cap": strategy._kk("max_daily_entries")}}


def _monitor_strategy_entry(strategy, today_date, today_iso, ticker_last_tick, tick_volume_mod):
    candidates_raw = getattr(strategy, "_candidates", None)
    candidates_raw = candidates_raw if isinstance(candidates_raw, dict) else {}
    positions = strategy.state.positions
    positions = positions if isinstance(positions, dict) else {}
    tickers = set(candidates_raw) | set(positions)
    return {
        "prepare": _monitor_prepare(strategy),
        "funnel": _monitor_funnel(strategy),
        "market_unit": _monitor_market_unit(strategy, today_date),
        "skips": _monitor_skips(strategy, today_iso, today_date),
        "paused_skips": _monitor_paused_skips(strategy, today_iso),
        "shadow_buys": _monitor_shadow_buys(strategy, today_iso),
        "ticks": _monitor_ticks(ticker_last_tick, tick_volume_mod, tickers),
        "candidates": _monitor_candidates(strategy, candidates_raw, today_date),
        "holdings": _monitor_holdings(strategy, positions, today_date),
        "extra": _monitor_extra(strategy, today_date),
    }


def _monitor_strategies(strategies, today_date, today_iso, ticker_last_tick, tick_volume_mod):
    return {
        s.strategy_id: _monitor_strategy_entry(s, today_date, today_iso, ticker_last_tick, tick_volume_mod)
        for s in strategies
    }


def _monitor_payload(strategies, running, today_date, today_iso, ticker_last_tick, tick_volume_mod):
    return {
        "as_of": now_kst_iso(),
        "running": running,
        "strategies": _monitor_strategies(strategies, today_date, today_iso, ticker_last_tick, tick_volume_mod),
    }


@router.get("/monitor")
async def get_strategies_monitor():
    """전략별 진행상황 읽기 전용 스냅샷(cycle414) — `GET /api/strategies/monitor`.

    대시보드 요약표 + 전략별 상세 패널이 5~10초마다 읽는 창. `await` 0 ·
    DB·KIS 호출 0 · 운영 전략 객체 무변경(순수성 = AST 가드가 강제). 실패는
    전부 HTTP 200 + `success=false` 로 흡수한다(폴링 엔드포인트가 500 스택트레이스를
    로그에 쌓지 않게). 2초 서버 캐시(exit-lines G1 과 같은 패턴).
    """
    global _monitor_cache
    try:
        now = _monitor_clock()
        cached = _monitor_cache
        if cached is not None and (now - cached[0]) < _MONITOR_CACHE_TTL_S:
            body = cached[1]
        else:
            from src.engine import tick_volume
            from src.engine.scanner import ticker_last_tick
            from src.engine.scheduler import trading_scheduler

            today_date = datetime.now(KST).date()
            today_iso = today_date.isoformat()
            payload = _monitor_payload(
                trading_scheduler.registry.all(), bool(trading_scheduler.is_running),
                today_date, today_iso, ticker_last_tick, tick_volume,
            )
            body = json.dumps({"success": True, "data": payload, "message": ""}, default=str)
            _monitor_cache = (now, body)
        return Response(content=body, media_type="application/json")
    except Exception:
        logger.debug("[strategies_monitor] 조회 실패 — graceful", exc_info=True)
        return ApiResponse(success=False, data=None, message="전략 진행상황 조회 실패")
