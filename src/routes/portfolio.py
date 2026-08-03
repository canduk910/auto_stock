"""포트폴리오 리스크 관찰 라우트 (사이클 H, 관찰 전용 Phase 1).

``GET /api/portfolio/risk`` — 전 전략 합산 오픈 리스크 + 섹터/전략별 노출 스냅샷.
관찰 전용(매수 차단 0). 외부(잔고/종목마스터) 실패 시 graceful **200 + 스냅샷**
(500 금지 — 관찰성 실패가 운영 화면을 죽이면 안 됨, 사이클 88 G-REJECT).

섹터명 소스(사이클 I 후속) = basics raw `bstp_kor_isnm`(KIS 업종 한글명 "유통"/"금융"
등, 사람이 읽는 명칭) 우선 → 부재 시 kojiro `_kojiro_sector_key`(master_raw KRX
산업지수 플래그 → 업종코드 → 미분류) 폴백. `_kojiro_sector_key` 무변경(kojiro 섹터
캡 그룹핑 보존, display 전용 변환). Phase 2b 인계 = SOFT 상한 + entry_atr 정밀 프록시.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.api.balance import get_balance
from src.db import stock_master
from src.engine.portfolio_risk import (
    compute_portfolio_risk_snapshot,
    extract_hard_stop_pct,
)
from src.engine.scheduler import trading_scheduler
from src.engine.strategies.kojiro import _kojiro_sector_key
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


async def _net_asset_graceful() -> int:
    """KIS 잔고 순자산 — 실패 시 0 (관찰 pct 만 0, 스냅샷은 보존)."""
    try:
        _holdings, summary = await get_balance()
        return int(getattr(summary, "net_asset", 0) or 0)
    except Exception:
        logger.debug("[portfolio_risk] get_balance 실패 graceful", exc_info=True)
        return 0


async def _sector_of_graceful(tickers) -> dict:
    """보유 ticker → 사람이 읽는 섹터명 사전. 개별 조회 실패는 `미분류-{ticker}` 독립 폴백.

    섹터명 소스 우선순위:
      1. `bstp_kor_isnm` (basics raw = CTPF1002R, KIS 업종 한글명 "유통"/"금융"/"전기·전자")
         — 전 종목 채워지는 사람이 읽는 명칭.
      2. 부재 시 `_kojiro_sector_key(master_raw)` — KRX 산업지수 플래그(반도체/바이오 등)
         → 업종 대분류코드 → 미분류. (kojiro 섹터 캡 로직과 동일 소스, 함수 무변경)
    """
    sector_of: dict[str, str] = {}
    for ticker in tickers:
        try:
            basics = await stock_master.get(ticker)
            raw = getattr(basics, "raw", None) if basics is not None else None
            name = ""
            if isinstance(raw, dict):
                name = str(raw.get("bstp_kor_isnm", "") or "").strip()
            if name:
                sector_of[ticker] = name
                continue
            # 폴백: master_raw KRX 산업지수 플래그 → 업종코드 → 미분류
            master_raw = await stock_master.get_master_raw(ticker)
            sector_of[ticker] = _kojiro_sector_key(
                master_raw if isinstance(master_raw, dict) else None, ticker
            )
        except Exception:
            logger.debug(
                "[portfolio_risk] 섹터 조회 실패 graceful: %s", ticker, exc_info=True
            )
            sector_of[ticker] = f"미분류-{ticker}"
    return sector_of


@router.get("/risk")
async def get_portfolio_risk() -> ApiResponse:
    """전 전략 포트폴리오 리스크 관찰 스냅샷 (Phase 1, 매수 차단 0)."""
    try:
        strategies = list(trading_scheduler.registry.all())
    except Exception:
        logger.debug("[portfolio_risk] registry 조회 실패 graceful", exc_info=True)
        strategies = []

    net_asset = await _net_asset_graceful()

    hard_stop_pcts: dict[str, float] = {}
    held_tickers: set[str] = set()
    for strat in strategies:
        sid = getattr(strat, "strategy_id", None) or "unknown"
        config = getattr(strat, "config", None)
        params = (
            getattr(config, "params", None)
            if config is not None
            else getattr(strat, "params", None)
        )
        hard_stop_pcts[sid] = extract_hard_stop_pct(
            params if isinstance(params, dict) else None
        )
        state = getattr(strat, "state", None)
        positions = getattr(state, "positions", None) if state is not None else None
        if isinstance(positions, dict):
            held_tickers.update(positions.keys())

    sector_of = await _sector_of_graceful(held_tickers)

    snapshot = compute_portfolio_risk_snapshot(
        strategies,
        net_asset=net_asset,
        hard_stop_pcts=hard_stop_pcts,
        sector_of=sector_of,
    )
    return ApiResponse(
        success=True, data=snapshot, message="포트폴리오 리스크 관찰 스냅샷"
    )
