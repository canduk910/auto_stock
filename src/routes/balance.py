"""잔고 조회 라우트: /api/balance/*"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.api.balance import get_balance, get_buyable
from src.db.stock_master import get as stock_master_get
from src.engine.sector_naming import resolve_sector_name
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/balance", tags=["balance"])


@router.get("", response_model=ApiResponse)
async def balance():
    """보유종목 + 계좌 요약을 반환한다.

    J1 (2026-05-11): 각 holding 에 stock_master(CTPF1002R 캐시) 필드
    `nxt_tradable / krx_halted / excg_dvsn_cd` 를 join 한다.
    보유 종목 수는 통상 10 미만이라 sequential await 비용 무시 가능.
    캐시 miss → None / 조회 예외 → 종목별 흡수 후 None.
    """
    holdings, summary = await get_balance()

    enriched_holdings: list[dict] = []
    for h in holdings:
        payload = h.model_dump()
        try:
            basics = await stock_master_get(h.ticker)
        except Exception as exc:  # noqa: BLE001 — 종목별 흡수, 나머지 계속
            logger.warning(
                "stock_master 조회 실패 (ticker=%s): %s — None 으로 응답", h.ticker, exc
            )
            basics = None
        if basics is not None:
            payload["nxt_tradable"] = bool(basics.nxt_tradable)
            payload["krx_halted"] = bool(basics.krx_halted)
            payload["excg_dvsn_cd"] = basics.excg_dvsn_cd or None
        # basics is None: payload 의 nxt_tradable/krx_halted/excg_dvsn_cd 기본 None 유지
        # 섹터명 — 위에서 이미 조회한 basics.raw 를 주입해 재조회를 막는다
        # (`sector_naming` 단일 진실원: bstp_kor_isnm → master_raw → 미분류).
        payload["sector"] = await resolve_sector_name(
            h.ticker,
            basics_raw=(getattr(basics, "raw", None) if basics is not None else None),
        )
        enriched_holdings.append(payload)

    return ApiResponse(
        success=True,
        data={
            "holdings": enriched_holdings,
            "summary": summary.model_dump(),
        },
    )


@router.get("/buyable", response_model=ApiResponse)
async def buyable(ticker: str = "", price: int = 0):
    """매수 가능 금액/수량을 반환한다."""
    info = await get_buyable(ticker, price)
    return ApiResponse(success=True, data=info.model_dump())
