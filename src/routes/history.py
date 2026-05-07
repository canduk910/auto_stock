"""거래 내역 라우트: /api/history/*"""

from fastapi import APIRouter, Query

from src.db.trade_history import get_trade_pairs, get_trades
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=ApiResponse)
async def trade_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    ticker: str | None = None,
    strategy: str | None = None,
):
    """거래 내역을 페이징 조회한다."""
    offset = (page - 1) * size
    trades, total = await get_trades(limit=size, offset=offset, ticker=ticker, strategy=strategy)

    # DB에 종목명이 없는 기존 데이터는 scanner에서 보완
    from src.engine.scanner import ticker_names
    for trade in trades:
        if not trade.get("ticker_name"):
            trade["ticker_name"] = ticker_names.get(trade.get("ticker", ""), "")

    return ApiResponse(
        success=True,
        data={
            "trades": trades,
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size if size > 0 else 0,
        },
    )


@router.get("/pnl", response_model=ApiResponse)
async def trade_pnl(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    ticker: str | None = None,
    strategy: str | None = None,
):
    """매수/매도 페어를 묶어 매매손익 뷰로 반환한다.

    포지션 0 사이클 단위 1행 (분할 매수/매도는 가중평균). 보유 중 종목은
    open 페어로 별도 행 — 미실현 손익은 scanner.ticker_prices 현재가 사용.
    """
    pairs = await get_trade_pairs(strategy=strategy, ticker=ticker)

    # 종목명 fallback (DB에 없는 기존 데이터)
    from src.engine.scanner import ticker_names
    for p in pairs:
        if not p.get("ticker_name"):
            p["ticker_name"] = ticker_names.get(p.get("ticker", ""), "")

    total = len(pairs)
    offset = (page - 1) * size
    sliced = pairs[offset:offset + size]

    return ApiResponse(
        success=True,
        data={
            "pairs": sliced,
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size if size > 0 else 0,
        },
    )
