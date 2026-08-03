"""거래 내역 라우트: /api/history/*"""

from __future__ import annotations

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
    summary = _build_pnl_summary(pairs)
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
            "summary": summary,
        },
    )


def _build_pnl_summary(pairs: list[dict]) -> dict:
    """전체 pairs(슬라이스 전) 중 closed 만 집계한 실현손익 요약.

    open 페어는 미실현(profit_loss None 가능) 이므로 제외한다.
    Decimal/float 혼용 대비 최종 값은 float 로 정규화한다.
    """
    closed = [p for p in pairs if p.get("status") == "closed"]

    realized_total = 0.0
    buy_amount_total = 0.0
    win_count = 0
    loss_count = 0
    even_count = 0

    for p in closed:
        profit_loss = float(p.get("profit_loss") or 0)
        realized_total += profit_loss
        buy_amount_total += float(p.get("buy_price") or 0) * float(p.get("buy_qty") or 0)
        if profit_loss > 0:
            win_count += 1
        elif profit_loss < 0:
            loss_count += 1
        else:
            even_count += 1

    realized_rate_pct = round(realized_total / buy_amount_total * 100, 2) if buy_amount_total else 0.0
    win_loss_total = win_count + loss_count
    win_rate_pct = round(win_count / win_loss_total * 100, 1) if win_loss_total else 0.0

    return {
        "realized_total_krw": realized_total,
        "realized_rate_pct": realized_rate_pct,
        "win_count": win_count,
        "loss_count": loss_count,
        "even_count": even_count,
        "win_rate_pct": win_rate_pct,
        "closed_count": len(closed),
    }
