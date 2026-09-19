"""시장 레짐 라우트 (사이클 2, 2026-05-17): /api/market-regime/*

- `GET /current` — 현 레짐 + 매수 가드 상태 + auto_regime_adjust + cash_usage_ratio
- `GET /history?days=30` — 최근 N 영업일 snapshot 추세 (Dashboard sparkline)
- `PUT /auto-adjust` — auto_regime_adjust 토글 (Settings UI)

graceful 정책: 매크로 fetch(우리 `macro` 컨테이너) 실패 시 empty regime.
레짐이 꺼져 있어도 본 라우트는 정상 200 응답(empty 상태 표시).

`enabled` 는 **DB 우선 / `.env` fallback** 이다 — `system_config.dkstock_regime_enabled`
가 True/False 면 그 값을, 키가 없거나 조회가 실패하면 `settings.dkstock_regime_enabled`
를 쓴다(`routes/system_integrations.py::_build_status` 와 같은 규약). Settings UI 토글이
DB 를 쓰므로 env 만 보면 운영자가 켠 상태가 화면에 영원히 꺼짐으로 보인다.
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

    # cycle315 — enabled 는 DB 우선 / .env fallback (system_integrations._build_status 규약).
    # DB 조회 실패는 graceful — env 값으로 낙하한다.
    try:
        db_enabled = await sc.get_dkstock_regime_enabled()
    except Exception:
        db_enabled = None
    enabled = (
        bool(db_enabled) if db_enabled is not None
        else bool(settings.dkstock_regime_enabled)
    )

    # 사이클 I — 지수ETF 레짐 관찰 (E-1). boot 부착 싱글톤 (재계산 X) + 토글.
    etf_sig = mr_mod.get_current_etf_signal()
    try:
        etf_enabled = await sc.get_etf_regime_enabled()
    except Exception:
        etf_enabled = False

    # 사이클 I (2026-08-03) — 레짐 매수 게이트 제거 반영.
    # 레짐은 더 이상 매수를 차단하지 않으므로 buy_blocked 는 항상 False (정직 표시).
    # block_reason 은 관찰용 "레짐 경보 사유"로 유지 (regime.block_reason, 매수 미개입).
    # 레거시 `regime.buy_blocked` 프로퍼티(모드 무시)를 그대로 노출하던 표시 결함 시정.
    body = MarketRegimeCurrent(
        regime=regime.regime,
        regime_desc=regime.regime_desc,
        cycle_phase=regime.cycle_phase,
        vix=regime.vix,
        fear_greed_score=regime.fear_greed_score,
        buffett_ratio=regime.buffett_ratio,
        cash_min=regime.cash_min,
        buy_blocked=False,
        block_reason=regime.block_reason,
        auto_regime_adjust=auto,
        cash_usage_ratio=ratio,
        enabled=enabled,
        etf_kospi_stage=etf_sig.kospi_stage if etf_sig is not None else None,
        etf_kosdaq_stage=etf_sig.kosdaq_stage if etf_sig is not None else None,
        etf_defensive=etf_sig.etf_defensive if etf_sig is not None else None,
        etf_enabled=bool(etf_enabled),
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
