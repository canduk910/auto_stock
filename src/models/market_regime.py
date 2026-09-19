"""사이클 2 (2026-05-17): 시장 레짐 API 응답 모델."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MarketRegimeCurrent(BaseModel):
    """`/api/market-regime/current` 응답."""

    regime: Optional[str] = None
    regime_desc: Optional[str] = None
    cycle_phase: Optional[str] = None
    vix: Optional[float] = None
    fear_greed_score: Optional[float] = None
    buffett_ratio: Optional[float] = None
    cash_min: Optional[int] = None
    buy_blocked: bool = False
    block_reason: Optional[str] = None
    auto_regime_adjust: bool = True
    cash_usage_ratio: float = 1.0
    # 레짐 수집 활성 여부 — DB(`system_config.dkstock_regime_enabled`) 우선 / `.env` fallback.
    # 🔴 `.env` 값 그대로가 아니다. 운영자가 Settings 에서 끈 것이 곧바로 이 값에 반영돼야 한다.
    enabled: bool = False
    # 사이클 I (2026-08-03) — 지수ETF 고지로 스테이지 레짐 관찰 (E-1). 매수 미개입.
    etf_kospi_stage: Optional[int] = None
    etf_kosdaq_stage: Optional[int] = None
    etf_defensive: Optional[bool] = None
    etf_enabled: bool = False  # etf_regime_enabled 토글


class MarketRegimeSnapshotItem(BaseModel):
    """`/api/market-regime/history` 행."""

    snapshot_date: str  # ISO date
    regime: str
    regime_desc: Optional[str] = None
    cycle_phase: Optional[str] = None
    vix: Optional[float] = None
    fear_greed_score: Optional[float] = None
    buffett_ratio: Optional[float] = None
    computed_cash_usage_ratio: Optional[float] = None
    buy_blocked: bool
    block_reason: Optional[str] = None
    created_at: Optional[str] = None


class AutoAdjustRequest(BaseModel):
    """`PUT /api/market-regime/auto-adjust` 요청."""

    enabled: bool
