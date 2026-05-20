"""사이클 5 (2026-05-17): 외부 통합 토글 라우트 (`/api/integrations/*`).

3 토글:
- `dkstock-regime` — 외부 매크로 서버 (dkstock.cloud) 활성 여부.
- `kis-mcp` — 외부 백테스트 서버 활성 여부.
- `auto-regime-adjust` — 매크로 레짐 기반 cash_usage_ratio 자동 갱신 (사이클 2 이미 존재 키, 통합 위치 이동).

공통 동작:
- GET: 현재 enabled + source(db/env) + env_value + db_value 응답.
- PUT: DB 갱신 + 응답 갱신값.
- dkstock-regime 활성화(True) 시 백그라운드 fetch trigger 발화 (매크로 즉시 반영).
- kis-mcp 활성화는 즉시 fetch 안 함 (백테스트는 자문 시점 발화).

하위 호환성:
- DB 미설정 시 settings.* 환경변수로 fallback — Phase 1 / 사이클 2 운영자 영향 0.
- 즉시 fetch 실패는 graceful — toggle 자체는 성공 유지.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException

from src.config import settings
from src.db import system_config as sc
from src.models.response import ApiResponse
from src.models.system_integrations import (
    AutoApplyRequest,
    AutoApplyStatus,
    BuyBlockStatusResponse,
    BuyBlockThresholdsModel,
    BuyBlockUpdateRequest,
    IntegrationToggleRequest,
    IntegrationToggleStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# 백그라운드 fetch trigger (dkstock-regime 활성화 직후)
# ---------------------------------------------------------------------------
async def _refresh_market_regime_and_persist_safely() -> None:
    """dkstock.cloud 매크로 fetch + 메모리 + DB snapshot. 모든 예외 graceful 흡수.

    PUT /api/integrations/dkstock-regime enabled=true 직후 백그라운드 task 발화.
    toggle 자체는 성공 응답 후 즉시 반환 — fetch 결과는 GET /api/market-regime/current
    폴링으로 확인. fetch 실패해도 DB 갱신은 성공 마킹 (운영자 가시성 위해 로그만).
    """
    try:
        from datetime import datetime, timezone, timedelta

        from src.engine import market_regime as mr_mod

        regime = await mr_mod.refresh_from_dkstock()
        mr_mod.set_current_regime(regime)
        if not regime.is_empty():
            KST = timezone(timedelta(hours=9))
            today = datetime.now(tz=KST).date()
            await mr_mod.persist_snapshot(regime, today)
            logger.info(
                "[integrations] dkstock fetch 성공 — regime=%s vix=%s fg=%s buy_blocked=%s",
                regime.regime, regime.vix, regime.fear_greed_score, regime.buy_blocked,
            )
        else:
            logger.warning(
                "[integrations] dkstock fetch empty 응답 — 매수 가드 비활성 유지"
            )
    except Exception:
        logger.exception("[integrations] dkstock 백그라운드 fetch 실패 — DB 토글은 성공")


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
async def _build_status(
    db_getter: Callable[[], Awaitable[Optional[bool]]],
    env_value: bool,
) -> IntegrationToggleStatus:
    """공통 GET 응답 빌더 — DB 우선 / .env fallback 결정."""
    try:
        db_value = await db_getter()
    except Exception:
        logger.exception("[integrations] DB getter 실패 — .env fallback")
        db_value = None

    if db_value is not None:
        return IntegrationToggleStatus(
            enabled=bool(db_value),
            source="db",
            env_value=bool(env_value),
            db_value=bool(db_value),
        )
    return IntegrationToggleStatus(
        enabled=bool(env_value),
        source="env",
        env_value=bool(env_value),
        db_value=None,
    )


# ---------------------------------------------------------------------------
# dkstock-regime
# ---------------------------------------------------------------------------
@router.get("/dkstock-regime", response_model=ApiResponse)
async def get_dkstock_regime():
    """외부 매크로 서버 활성 여부 조회."""
    status = await _build_status(
        sc.get_dkstock_regime_enabled, settings.dkstock_regime_enabled,
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/dkstock-regime", response_model=ApiResponse)
async def set_dkstock_regime(req: IntegrationToggleRequest):
    """외부 매크로 서버 활성 토글 + 활성화 시 백그라운드 fetch trigger."""
    try:
        await sc.set_dkstock_regime_enabled(req.enabled)
    except Exception as e:
        logger.exception("[integrations] dkstock_regime DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 활성화 시 백그라운드 fetch 발화 — 응답은 즉시 반환.
    if req.enabled:
        try:
            asyncio.create_task(_refresh_market_regime_and_persist_safely())
        except RuntimeError:
            # event loop 미보유 등 예상외 — toggle 자체는 성공 보존
            logger.warning("[integrations] fetch task 발화 실패 (event loop 부재)")
    else:
        # 비활성화 — 메모리 regime 초기화 (graceful, 매수 가드 즉시 해제)
        try:
            from src.engine import market_regime as mr_mod

            mr_mod.set_current_regime(mr_mod.MarketRegime.empty())
        except Exception:
            logger.exception("[integrations] dkstock 비활성화 후 메모리 reset 실패")

    status = await _build_status(
        sc.get_dkstock_regime_enabled, settings.dkstock_regime_enabled,
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "외부 매크로 서버를 활성화했습니다. 백그라운드 fetch 진행 중 — 잠시 후 GET /api/market-regime/current 로 확인하세요."
            if req.enabled
            else "외부 매크로 서버를 비활성화했습니다. 매수 가드 즉시 해제됩니다."
        ),
    )


# ---------------------------------------------------------------------------
# kis-mcp
# ---------------------------------------------------------------------------
@router.get("/kis-mcp", response_model=ApiResponse)
async def get_kis_mcp():
    status = await _build_status(
        sc.get_kis_mcp_enabled, settings.kis_mcp_enabled,
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/kis-mcp", response_model=ApiResponse)
async def set_kis_mcp(req: IntegrationToggleRequest):
    """외부 백테스트 서버 활성 토글.

    즉시 fetch 안 함 — 백테스트는 자문 시점(20:00) 발화. 운영 매매 흐름 무관.
    """
    try:
        await sc.set_kis_mcp_enabled(req.enabled)
    except Exception as e:
        logger.exception("[integrations] kis_mcp DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    status = await _build_status(
        sc.get_kis_mcp_enabled, settings.kis_mcp_enabled,
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "외부 백테스트 서버를 활성화했습니다. 다음 20:00 자문부터 백테스트 검증이 반영됩니다."
            if req.enabled
            else "외부 백테스트 서버를 비활성화했습니다. 자문 흐름은 backtest_summary=null 로 graceful degrade."
        ),
    )


# ---------------------------------------------------------------------------
# auto-regime-adjust (사이클 2 기존 키 — 라우트만 통합 위치 이동)
# ---------------------------------------------------------------------------
async def _get_auto_regime_adjust_value() -> Optional[bool]:
    """`get_auto_regime_adjust` 는 항상 bool 반환(키 부재시 True). 본 라우트는 None
    분기가 무의미하지만 통합 API 응답 구조를 맞추기 위해 wrap.
    """
    try:
        v = await sc.get_auto_regime_adjust()
        return bool(v)
    except Exception:
        return None


@router.get("/auto-regime-adjust", response_model=ApiResponse)
async def get_auto_regime_adjust():
    """매크로 레짐 → cash_usage_ratio 자동 조정 토글 조회.

    기존 system_config 키 `auto_regime_adjust` 사용 (사이클 2). 본 라우트는 통합
    Settings UI 노출 일관성용. `env_value` 는 의미 없지만 응답 구조 동일성 위해 False
    고정.
    """
    status = await _build_status(
        _get_auto_regime_adjust_value, env_value=True,  # 기본 True (사이클 2)
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/auto-regime-adjust", response_model=ApiResponse)
async def set_auto_regime_adjust(req: IntegrationToggleRequest):
    try:
        await sc.set_auto_regime_adjust(req.enabled)
    except Exception as e:
        logger.exception("[integrations] auto_regime_adjust DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    status = await _build_status(
        _get_auto_regime_adjust_value, env_value=True,
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "자동 조정 활성 — 다음 _boot 부터 매크로 레짐 cash_min 기반 cash_usage_ratio 자동 갱신."
            if req.enabled
            else "수동 모드 — 운영자 cash_usage_ratio 보존."
        ),
    )


# ---------------------------------------------------------------------------
# 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값
# ---------------------------------------------------------------------------
async def _build_buy_block_status() -> BuyBlockStatusResponse:
    """현재 모드 + 임계 + 메모리 regime 평가 결과 → 응답 빌더.

    `get_current_regime().get_buy_block_state()` 가 진실의 원천 — DB 조회 1회 + 메모리 regime
    평가 1회로 구성. empty regime / fetch 실패 graceful.
    """
    from src.engine import market_regime as mr_mod

    mode = await sc.get_buy_block_mode()
    thresholds_db = await sc.get_buy_block_thresholds()
    regime = mr_mod.get_current_regime()
    try:
        state = await regime.get_buy_block_state()
    except Exception:
        logger.exception("[buy_block] state 조회 실패 — HARD/기본 fallback")
        state = mr_mod.BuyBlockState(
            mode=mode, blocked=False, soft_multiplier=1.0, reasons=[],
        )

    return BuyBlockStatusResponse(
        mode=state.mode,  # type: ignore[arg-type]
        thresholds=BuyBlockThresholdsModel(
            vix_threshold=thresholds_db.vix_threshold,
            fg_high_threshold=thresholds_db.fg_high_threshold,
            fg_low_threshold=thresholds_db.fg_low_threshold,
            defensive_enabled=thresholds_db.defensive_enabled,
        ),
        blocked=state.blocked,
        reasons=list(state.reasons),
        soft_multiplier=state.soft_multiplier,
    )


@router.get("/buy-block", response_model=ApiResponse)
async def get_buy_block():
    """매수 가드 현재 상태 조회 (사이클 8, 2026-05-18).

    응답:
    - mode: OFF/WARN/SOFT/HARD
    - thresholds: VIX/FG_high/FG_low/defensive_enabled
    - blocked: 현재 가드 발동 여부 (mode 무관, 임계 OR 평가)
    - reasons: 발동 사유 (UI 표시용 — defensive/vix/fg_high/fg_low)
    - soft_multiplier: SOFT 시 0.5, 그 외 1.0
    """
    status = await _build_buy_block_status()
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/buy-block", response_model=ApiResponse)
async def set_buy_block(req: BuyBlockUpdateRequest):
    """매수 가드 모드/임계 부분 갱신 (사이클 8, 2026-05-18).

    body 의 None 필드는 기존 값 보존. Pydantic 이 mode literal + 임계 ge/le 검증을
    수행하므로 잘못된 값은 422 자동. 갱신 후 전체 상태를 응답.
    """
    try:
        if req.mode is not None:
            await sc.set_buy_block_mode(req.mode)
        if (
            req.vix_threshold is not None
            or req.fg_high_threshold is not None
            or req.fg_low_threshold is not None
            or req.defensive_enabled is not None
        ):
            await sc.set_buy_block_thresholds(
                vix_threshold=req.vix_threshold,
                fg_high_threshold=req.fg_high_threshold,
                fg_low_threshold=req.fg_low_threshold,
                defensive_enabled=req.defensive_enabled,
            )
    except ValueError as e:
        # set_buy_block_mode 가 4 모드 외 값을 거부할 수 있음 (이중 안전망)
        logger.warning("[buy_block] PUT 검증 실패: %s", e)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("[buy_block] DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 사이클 11 (2026-05-18) — 메모리 regime 의 buy_block_state 캐시 즉시 무효화.
    # 운영자 토글 후 60s TTL 만료 기다리지 않고 다음 매수 신호부터 즉시 반영.
    try:
        from src.engine import market_regime as mr_mod

        current = mr_mod.get_current_regime()
        if current is not None:
            current.invalidate_buy_block_cache()
    except Exception:
        # 캐시 무효화 실패는 toggle 성공 자체를 깨뜨리지 않음 — 다음 TTL 만료에 자연 갱신
        logger.debug("[buy_block] cache invalidate 실패 (graceful)", exc_info=True)

    status = await _build_buy_block_status()
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            f"매수 가드 모드 '{status.mode}' 적용. 다음 매수 신호부터 즉시 반영됩니다."
        ),
    )


# ---------------------------------------------------------------------------
# 사이클 23 (2026-05-20) — AI 자문 자동 적용 토글
# ---------------------------------------------------------------------------
@router.get("/auto-apply", response_model=ApiResponse)
async def get_auto_apply():
    """AI 자문 자동 적용 토글 조회.

    기본 False — 안전 우선. 운영자 명시 활성화 후에만 자동 감액 + 보수적 파라미터 적용.
    """
    enabled = await sc.get_auto_apply_enabled()
    return ApiResponse(success=True, data=AutoApplyStatus(enabled=enabled).model_dump())


@router.put("/auto-apply", response_model=ApiResponse)
async def put_auto_apply(req: AutoApplyRequest):
    """AI 자문 자동 적용 토글 변경.

    ON: 20:00 AI 자문 직후 weight 감액(50% cap) + 보수적 파라미터 자동 적용.
    OFF: 기존 수동 흐름 (apply_weight=true 명시) 만 유지.
    """
    try:
        await sc.set_auto_apply_enabled(req.enabled)
    except Exception as e:
        logger.exception("[auto_apply] DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail="DB 저장 실패")
    return ApiResponse(
        success=True,
        data=AutoApplyStatus(enabled=req.enabled).model_dump(),
        message=(
            "AI 자문 자동 적용을 활성화했습니다. 매일 20:00 자문 직후 weight 감액(50% cap) + 보수적 파라미터가 자동 적용됩니다."
            if req.enabled
            else "AI 자문 자동 적용을 비활성화했습니다. 모든 자문은 운영자 수동 적용에서만 반영됩니다."
        ),
    )
