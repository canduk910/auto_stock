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
