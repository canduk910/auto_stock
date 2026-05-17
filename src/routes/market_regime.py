"""시장 레짐 라우트 (사이클 2, 2026-05-17): /api/market-regime/*

- `GET /current` — 현 레짐 + 매수 가드 상태 + auto_regime_adjust + cash_usage_ratio
- `GET /history?days=30` — 최근 N 영업일 snapshot 추세 (Dashboard sparkline)
- `PUT /auto-adjust` — auto_regime_adjust 토글 (Settings UI)

graceful 정책: dkstock.cloud fetch 실패 시 empty regime + 가드 비활성.
운영 활성화 (DKSTOCK_REGIME_ENABLED=true) 전에도 본 라우트는 정상 200 응답
(empty 상태 표시).
"""
from __future__ import annotations

from fastapi import APIRouter

from src.config import settings
from src.db import market_regime_snapshots as mrs
from src.db import system_config as sc
from src.engine import market_regime as mr_mod
from src.models.market_regime import (
    AutoAdjustRequest, MarketRegimeCurrent, MarketRegimeSnapshotItem,
)
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/market-regime", tags=["market-regime"])


@router.get("/current", response_model=ApiResponse)
async def get_current():
    """현재 메모리 레짐 + 매수 가드 + cash_usage_ratio + auto_regime_adjust."""
    regime = mr_mod.get_current_regime()
    try:
        auto = await sc.get_auto_regime_adjust()
    except Exception:
        auto = True
    try:
        ratio = await sc.get_cash_usage_ratio()
    except Exception:
        ratio = 1.0

    body = MarketRegimeCurrent(
        regime=regime.regime,
        regime_desc=regime.regime_desc,
        cycle_phase=regime.cycle_phase,
        vix=regime.vix,
        fear_greed_score=regime.fear_greed_score,
        buffett_ratio=regime.buffett_ratio,
        cash_min=regime.cash_min,
        buy_blocked=regime.buy_blocked,
        block_reason=regime.block_reason,
        auto_regime_adjust=auto,
        cash_usage_ratio=ratio,
        enabled=settings.dkstock_regime_enabled,
    )
    return ApiResponse(success=True, data=body.model_dump())


@router.get("/history", response_model=ApiResponse)
async def get_history(days: int = 30):
    """최근 N 영업일 snapshot. Dashboard sparkline 용."""
    days = max(1, min(days, 365))
    rows = await mrs.list_recent(days=days)
    items = [
        MarketRegimeSnapshotItem(
            snapshot_date=row.get("snapshot_date") or "",
            regime=row.get("regime") or "",
            regime_desc=row.get("regime_desc"),
            cycle_phase=row.get("cycle_phase"),
            vix=row.get("vix"),
            fear_greed_score=row.get("fear_greed_score"),
            buffett_ratio=row.get("buffett_ratio"),
            computed_cash_usage_ratio=row.get("computed_cash_usage_ratio"),
            buy_blocked=bool(row.get("buy_blocked", False)),
            block_reason=row.get("block_reason"),
            created_at=row.get("created_at"),
        ).model_dump()
        for row in rows
    ]
    return ApiResponse(success=True, data=items)


@router.put("/auto-adjust", response_model=ApiResponse)
async def update_auto_adjust(req: AutoAdjustRequest):
    """auto_regime_adjust 토글. 다음 _boot 부터 반영 (Settings UI 안내 필요).

    true → 매크로 레짐 cash_min 기반 cash_usage_ratio 자동 갱신.
    false → 운영자 수동 cash_usage_ratio 보존.
    """
    await sc.set_auto_regime_adjust(req.enabled)
    return ApiResponse(
        success=True,
        data={"auto_regime_adjust": req.enabled},
        message="다음 영업일 _boot 부터 반영됩니다." if req.enabled else "수동 모드로 전환됨 (cash_usage_ratio 자동 갱신 안 함).",
    )
