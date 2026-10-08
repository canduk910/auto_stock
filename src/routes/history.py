"""거래 내역 라우트: /api/history/*"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Query

from src.db import trade_cost as trade_cost_db
from src.db.trade_history import get_trade_pairs, get_trades
from src.engine import cost_overlay
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


def _trade_date(ts) -> date | None:
    """`timestamp`(KST ISO 문자열, `_TS_SELECT`)에서 KST 날짜만 뽑는다."""
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        return datetime.fromisoformat(s).date()
    except (TypeError, ValueError):
        return None


async def _overlay_trade_costs(trades: list[dict]) -> None:
    """체결 행마다 `fee`·`tax`·`net_profit_loss`·`cost_status` 를 얹는다(cycle411).

    cycle411 보완 H2 — 배분(`cost_overlay.trade_costs`)은 항상 그 날짜 범위의 **전체**
    COMPLETED+PARTIAL 체결(`trade_cost_db.get_trades_by_status`)로 하고, 거기서 나온
    id 별 비용 중 화면에 보이는(페이지에 든) 행만 집어 쓴다 — 페이지·전략 필터는 배분
    **뒤에** 거른다(한 페이지만 보면 그 정산 1행 전부를 떠안는 결함을 막는다). 요율은
    화면 날짜 범위가 아니라 서버 오늘 기준 30일 창(M2) · ETF 판정은 stock_master 구분
    코드 우선(M3).

    비용 조회가 실패하면 기존 칸만 남기고 새 칸은 건너뛴다(사용자 결정 10-08 §2 —
    `[cost_overlay_unavailable]`, 기존 응답 200 유지).
    """
    dated = [(_trade_date(t.get("timestamp")), t) for t in trades]
    dates = [d for d, _ in dated if d]
    if not dates:
        return
    start, end = min(dates), max(dates)
    try:
        cost_rows = await trade_cost_db.get_daily_range(start, end)
        full_trades = await trade_cost_db.get_trades_by_status(start, end)
        rates = await cost_overlay.today_window_rates()
        etf_flags = await cost_overlay.stock_master_etf_flags(full_trades)
    except Exception:
        logger.warning("[cost_overlay_unavailable] /api/history 실비용 조회 실패", exc_info=True)
        return

    costs = cost_overlay.trade_costs(cost_rows, full_trades, rates, etf_flags=etf_flags)
    for t in trades:
        c = costs.get(t.get("id"))
        if c is None:
            continue
        t["fee"] = c["fee"]
        t["cost_status"] = c["cost_status"]
        if str(t.get("trade_type") or "").upper() == "SELL":
            t["tax"] = c["tax"]
            t["net_profit_loss"] = float(t.get("profit_loss") or 0.0) - c["fee"] - c["tax"]


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
        # NUMERIC → float 사영. `get_trades` 는 `SELECT t.*` raw 행을 돌려주므로
        # `price`·`profit_loss` 가 asyncpg Decimal 이고, pydantic v2 는 JSON 에서
        # Decimal 을 **문자열**로 직렬화한다. 프론트 계약은 숫자(`Trade.price: number`)라
        # 문자열이 가면 그리드가 그 열을 통째로 `-` 로 떨군다. 컬럼명을 박지 않고
        # Decimal 전체를 사영해 향후 `ALTER TABLE` 에도 계약이 유지되게 한다.
        # 형제 경로 `/api/history/pnl` 은 `get_trade_pairs` 가 `float()` 로 캐스트해 이미 숫자다.
        for key in [k for k, v in trade.items() if isinstance(v, Decimal)]:
            trade[key] = float(trade[key])

    await _overlay_trade_costs(trades)

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

    trades_by_id = await cost_overlay.overlay_pairs(pairs)

    total = len(pairs)
    summary = _build_pnl_summary(pairs, trades_by_id)
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


def _build_pnl_summary(pairs: list[dict], trades_by_id: dict[int, dict] | None = None) -> dict:
    """전체 pairs(슬라이스 전) 중 closed 만 집계한 실현손익 요약.

    open 페어는 미실현(profit_loss None 가능) 이므로 제외한다.
    Decimal/float 혼용 대비 최종 값은 float 로 정규화한다.

    cycle411 — `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`(closed
    페어 기준) · `slippage_n`(closed 페어가 가리키는 체결 행 중 `order_price` 덮인 수).

    cycle411 보완 M4 — 비용 조회가 실패했으면(`trades_by_id is None`) 위 네 칸은 **0 이
    아니라 `None`**(「모름」 ≠ 0, 기존 칸은 그대로 유지).
    """
    closed = [p for p in pairs if p.get("status") == "closed"]
    cost_available = trades_by_id is not None

    realized_total = 0.0
    buy_amount_total = 0.0
    win_count = 0
    loss_count = 0
    even_count = 0
    fee_sum = 0.0
    tax_sum = 0.0
    realized_net_total = 0.0

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
        if cost_available:
            fee_sum += float(p.get("fee") or 0.0)
            tax_sum += float(p.get("tax") or 0.0)
            realized_net_total += float(p.get("net_profit_loss") or 0.0)

    realized_rate_pct = round(realized_total / buy_amount_total * 100, 2) if buy_amount_total else 0.0
    if cost_available:
        realized_net_rate_pct = (
            round(realized_net_total / buy_amount_total * 100, 2) if buy_amount_total else 0.0
        )
    else:
        fee_sum = tax_sum = realized_net_total = realized_net_rate_pct = None
    win_loss_total = win_count + loss_count
    win_rate_pct = round(win_count / win_loss_total * 100, 1) if win_loss_total else 0.0

    slippage_n = 0
    if trades_by_id:
        seen: set[int] = set()
        for p in closed:
            for i in list(p.get("buy_trade_ids") or []) + list(p.get("sell_trade_ids") or []):
                if i in seen:
                    continue
                seen.add(i)
                t = trades_by_id.get(i)
                if t and t.get("order_price") is not None:
                    slippage_n += 1

    return {
        "realized_total_krw": realized_total,
        "realized_rate_pct": realized_rate_pct,
        "win_count": win_count,
        "loss_count": loss_count,
        "even_count": even_count,
        "win_rate_pct": win_rate_pct,
        "closed_count": len(closed),
        "fee_sum": fee_sum,
        "tax_sum": tax_sum,
        "realized_net_total_krw": realized_net_total,
        "realized_net_rate_pct": realized_net_rate_pct,
        "slippage_n": slippage_n,
    }
