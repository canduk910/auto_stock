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
from src.engine.sector_naming import resolve_sector_names
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
    return await resolve_sector_names(tickers)


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

    # cycle233 — 척도 병기: 전략 노출 실효 손절선 주입 (fail-open, 프록시 폴백)
    strat_by_id = {
        (getattr(s, "strategy_id", None) or "unknown"): s for s in strategies
    }

    def _stop_of(sid: str, ticker: str):
        fn = getattr(strat_by_id.get(sid), "get_effective_stop_price", None)
        if not callable(fn):
            return None
        try:
            return fn(ticker)
        except Exception:
            return None

    snapshot = compute_portfolio_risk_snapshot(
        strategies,
        net_asset=net_asset,
        hard_stop_pcts=hard_stop_pcts,
        sector_of=sector_of,
        stop_price_of=_stop_of,
    )
    # cycle233 — 1주 폴백 notional 초과 + 계좌 게이트 상태 관측 노출
    # cycle259 카드 ⑥ — 조립은 watcher 단일 소유 `get_gate_snapshot()`(8키 +
    # `eval_timeouts_today`)로 위임한다. 20:10 리포트 빌더와 같은 형상을 낸다.
    try:
        from src.engine.account_risk_watcher import get_gate_snapshot
        from src.engine.portfolio_risk import compute_over_cap_positions
        snapshot["over_cap_positions"] = compute_over_cap_positions(strategies)
        snapshot["account_gate"] = get_gate_snapshot()
    except Exception:
        logger.debug("[portfolio_risk] over_cap/gate 관측 실패 graceful", exc_info=True)
    return ApiResponse(
        success=True, data=snapshot, message="포트폴리오 리스크 관찰 스냅샷"
    )
