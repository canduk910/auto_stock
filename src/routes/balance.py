"""잔고 조회 라우트: /api/balance/*"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.api.balance import get_balance, get_buyable
from src.db.stock_master import get as stock_master_get
from src.engine.position_exit_lines import build_exit_line_map
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

    # cycle339 — 종목별 청산선(손절가·목표가). in-memory registry 조회뿐이라
    # DB·KIS 왕복이 0 이다. 🔴 registry 를 못 읽어도 잔고는 그대로 나가야 하므로
    # graceful — 그때는 전 종목이 `—` 로 보인다(숫자를 지어내지 않는다).
    exit_lines: dict = {}
    try:
        from src.engine.scheduler import trading_scheduler

        exit_lines = build_exit_line_map(
            trading_scheduler.registry.all(), [h.ticker for h in holdings]
        )
    except Exception:
        logger.debug("[exit_lines] registry 조회 실패 graceful", exc_info=True)

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
        # cycle339 — 청산선 4필드. 판정 불가는 전부 None 이고 화면이 `—` 를 그린다.
        payload.update(
            exit_lines.get(h.ticker)
            or {
                "strategy_id": None,
                "stop_price": None,
                "stop_source": None,
                "target_price": None,
                "target_source": None,
            }
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
