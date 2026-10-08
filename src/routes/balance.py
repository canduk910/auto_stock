"""잔고 조회 라우트: /api/balance/*"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter

from src.api.balance import get_balance, get_buyable
from src.db import trade_cost as trade_cost_db
from src.db._kst import today_kst
from src.db.stock_master import get as stock_master_get
from src.engine import cost_overlay
from src.engine.etf_like import is_etf_like
from src.engine.position_buy_date import merge_buy_date, resolve_engine_buy_dates
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
    # cycle406 L2 — `get_balance()` 소진 예외(KIS 재시도 소진 등)를 ASGI 미처리 500 으로
    # 내보내지 않는다. 내부 호출부(`portfolio.py::_net_asset_graceful` 등)는 이미 흡수하지만
    # 이 라우트는 잔고 자체가 본문이라 200+빈 데이터로 꾸밀 수 없다 — `success=False` 로
    # 흡수한다(루트 CLAUDE.md API 응답 래퍼 규약).
    try:
        holdings, summary = await get_balance()
    except Exception as exc:  # noqa: BLE001 — 원인 불문 흡수, 메시지에 남긴다
        logger.warning("[balance] get_balance 실패 — success=False 로 흡수: %s", exc, exc_info=True)
        return ApiResponse(success=False, data=None, message=f"잔고 조회 실패: {exc}")

    # cycle411 — 예상 매도비용 요율(수수료율+세율, ETF 는 수수료율만). 최근 30달력일
    # 정산 표본이 없으면 기본값으로 떨어진다(`estimate_rates`) — DB 조회 실패도 같은
    # fail-open(「살까 말까」 가 아니라 화면 참고용 추정이라 전체 잔고를 막지 않는다).
    try:
        today = today_kst()
        cost_rows = await trade_cost_db.get_daily_range(today - timedelta(days=30), today)
    except Exception:
        logger.debug("[cost_overlay] 잔고 요율 조회 실패 graceful — 기본값", exc_info=True)
        cost_rows = []
    sell_rates = cost_overlay.estimate_rates(cost_rows)

    # cycle339 — 종목별 청산선(손절가·목표가). in-memory registry 조회뿐이라
    # DB·KIS 왕복이 0 이다. 🔴 registry 를 못 읽어도 잔고는 그대로 나가야 하므로
    # graceful — 그때는 전 종목이 `—` 로 보인다(숫자를 지어내지 않는다).
    exit_lines: dict = {}
    try:
        from src.engine.scheduler import trading_scheduler

        exit_lines = build_exit_line_map(
            trading_scheduler.registry.all(),
            [h.ticker for h in holdings],
            engine_running=bool(trading_scheduler.is_running),
        )
    except Exception:
        logger.debug("[exit_lines] registry 조회 실패 graceful", exc_info=True)

    # cycle397 — 매입일(최초 매입일). 1순위 = 엔진 포지션(엔진이 실제로 쓰는 값),
    # 2순위 = DB `positions.buy_date`(수동 보유·엔진 정지 중의 폴백). 두 출처가
    # 모두 있으면 더 이른 날짜(「최초」 규약). registry/DB 조회 실패는 모두
    # graceful — 그 종목 칸만 `None`(화면 `—`), 잔고 자체는 그대로 나간다.
    engine_buy_dates: dict[str, str] = {}
    try:
        from src.engine.scheduler import trading_scheduler

        engine_buy_dates = resolve_engine_buy_dates(trading_scheduler.registry.all())
    except Exception:
        logger.debug("[buy_date] registry 조회 실패 graceful", exc_info=True)

    db_buy_dates: dict = {}
    try:
        from src.db.positions import get_buy_dates

        db_buy_dates = await get_buy_dates([h.ticker for h in holdings])
    except Exception:
        logger.debug("[buy_date] DB 조회 실패 graceful", exc_info=True)

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
        # cycle411 — 예상 매도비용 요율(ETF 는 수수료율만). 화면이 평가금액에 곱한다.
        is_etf = is_etf_like(getattr(basics, "raw", None) if basics is not None else None, h.name)
        payload["sell_cost_rate"] = (
            sell_rates["fee_rate"] if is_etf else sell_rates["fee_rate"] + sell_rates["tax_rate"]
        )
        payload["cost_status"] = "estimated"
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
        # cycle397 — 매입일(최초 매입일). 판정 불가는 None(화면 `—`) — 오늘
        # 날짜로 채우지 않는다.
        payload["buy_date"] = merge_buy_date(
            engine_buy_dates.get(h.ticker), db_buy_dates.get(h.ticker)
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
