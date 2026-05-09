"""trade_history CRUD."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from src.db.supabase import supabase
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# supabase-py는 동기 client. 모든 .execute() 호출을 asyncio.to_thread()로 위임해
# 이벤트 루프 블로킹 차단(on_tick / 체결통보 핸들러가 매 호출 ms 단위로 밀리던 결함).


async def insert_trade(record: TradeRecord) -> None:
    """거래 기록을 삽입한다."""
    data = {
        "ticker": record.ticker,
        "ticker_name": record.ticker_name,
        "trade_type": record.trade_type.value,
        "price": float(record.price),
        "quantity": record.quantity,
        "profit_loss": float(record.profit_loss),
        "status": record.status.value,
        "strategy": record.strategy,
        "order_no": record.order_no,
        "timestamp": datetime.now(KST).isoformat(),
    }
    await asyncio.to_thread(
        lambda: supabase.table("trade_history").insert(data).execute()
    )
    logger.debug("거래 기록 삽입: %s %s (전략: %s)", record.trade_type.value, record.ticker, record.strategy)


async def update_trade_status(
    ticker: str,
    trade_type: TradeType,
    status: TradeStatus,
    strategy: str = "momentum",
    price: int | None = None,
    profit_loss: float | None = None,
) -> int:
    """최신 PENDING 거래 기록의 상태를 업데이트하고 영향받은 행 수를 반환한다."""
    update_data: dict = {"status": status.value}
    if price is not None:
        update_data["price"] = float(price)
    if profit_loss is not None:
        update_data["profit_loss"] = float(profit_loss)

    def _update():
        return (
            supabase.table("trade_history")
            .update(update_data)
            .eq("ticker", ticker)
            .eq("trade_type", trade_type.value)
            .eq("status", TradeStatus.PENDING.value)
            .eq("strategy", strategy)
            .execute()
        )

    result = await asyncio.to_thread(_update)
    affected = len(result.data or [])
    logger.debug("거래 상태 변경: %s %s -> %s (전략: %s, %d건)",
                 ticker, trade_type.value, status.value, strategy, affected)
    return affected


async def get_today_trades_for_settlement(strategy: str | None = None) -> list[dict]:
    """정산용 — 당일 체결 거래 전체(중복 dedup 없음, 매수+매도 합산용).

    COMPLETED + PARTIAL 상태만 포함. 매매 cashflow / 실현손익 합 계산에 사용.
    """
    from datetime import date
    today = date.today().isoformat()

    def _query():
        q = (
            supabase.table("trade_history")
            .select("*")
            .gte("timestamp", f"{today}T00:00:00")
            .in_("status", ["COMPLETED", "PARTIAL"])
            .order("timestamp", desc=False)
        )
        if strategy:
            q = q.eq("strategy", strategy)
        return q.execute()

    result = await asyncio.to_thread(_query)
    return result.data or []


async def get_today_buy_trades(strategy: str | None = None) -> list[dict]:
    """당일 매수 기록을 조회한다 (포지션 복구용)."""
    from datetime import date
    today = date.today().isoformat()

    def _query():
        q = (
            supabase.table("trade_history")
            .select("*")
            .eq("trade_type", "BUY")
            .gte("timestamp", f"{today}T00:00:00")
            .in_("status", ["PENDING", "COMPLETED", "PARTIAL"])
            .order("timestamp", desc=True)
        )
        if strategy:
            q = q.eq("strategy", strategy)
        return q.execute()

    result = await asyncio.to_thread(_query)
    # 같은 종목이 여러 번 매수된 경우 최신 기록만 사용
    seen: dict[str, dict] = {}
    for row in result.data:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


async def get_today_sell_trades(strategy: str | None = None) -> list[dict]:
    """당일 매도 기록을 조회한다 (동기화용)."""
    from datetime import date
    today = date.today().isoformat()

    def _query():
        q = (
            supabase.table("trade_history")
            .select("*")
            .eq("trade_type", "SELL")
            .gte("timestamp", f"{today}T00:00:00")
            .in_("status", ["COMPLETED", "PARTIAL"])
            .order("timestamp", desc=True)
        )
        if strategy:
            q = q.eq("strategy", strategy)
        return q.execute()

    result = await asyncio.to_thread(_query)
    seen: dict[str, dict] = {}
    for row in result.data:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


async def get_trades(
    limit: int = 50,
    offset: int = 0,
    ticker: str | None = None,
    strategy: str | None = None,
) -> tuple[list[dict], int]:
    """거래 내역을 조회한다. (데이터, 전체 건수) 반환."""
    def _count():
        q = supabase.table("trade_history").select("*", count="exact")
        if ticker:
            q = q.eq("ticker", ticker)
        if strategy:
            q = q.eq("strategy", strategy)
        return q.execute()

    def _data():
        q = (
            supabase.table("trade_history")
            .select("*")
            .order("timestamp", desc=True)
            .range(offset, offset + limit - 1)
        )
        if ticker:
            q = q.eq("ticker", ticker)
        if strategy:
            q = q.eq("strategy", strategy)
        return q.execute()

    count_result, result = await asyncio.gather(
        asyncio.to_thread(_count),
        asyncio.to_thread(_data),
    )
    total = count_result.count or 0
    return result.data, total


async def get_trades_in_range(
    start_date,
    end_date,
    strategy: str | None = None,
) -> list[dict]:
    """[start_date, end_date] 범위의 거래 기록을 timestamp 기준 inclusive하게 조회한다.

    파라미터 추천 모듈 등에서 N영업일치 통계 산출에 사용한다.
    """
    start_iso = f"{start_date.isoformat()}T00:00:00"
    end_iso = f"{end_date.isoformat()}T23:59:59.999999"

    def _query():
        q = (
            supabase.table("trade_history")
            .select("*")
            .gte("timestamp", start_iso)
            .lte("timestamp", end_iso)
            .order("timestamp", desc=False)
        )
        if strategy:
            q = q.eq("strategy", strategy)
        return q.execute()

    result = await asyncio.to_thread(_query)
    return result.data or []


async def get_trade_pairs(
    strategy: str | None = None,
    ticker: str | None = None,
) -> list[dict]:
    """매수/매도 페어 리스트를 반환한다 (매매손익 뷰용).

    페어링 모델: 같은 (ticker, strategy) 그룹 내에서 timestamp 오름차순으로
    누적 보유 수량(position)을 추적하다가 0으로 돌아오는 시점마다 한 페어 emit.
    분할 매수/매도가 한 사이클 안에 발생해도 매수가/매도가는 가중평균으로 한 행에 표현.
    매도 후에도 잔량이 남으면(보유 중) 'open' 페어 1행 추가 — 미실현 손익은
    `scanner.ticker_prices`의 현재가를 사용해 계산, 시세 미수신이면 None.

    Returns: 각 dict는 다음 키를 갖는다 —
        buy_date, buy_time, sell_date, sell_time, ticker, ticker_name,
        buy_price, buy_qty, sell_price, sell_qty,
        profit_loss, profit_rate, status('closed'|'open'), strategy
    """
    from collections import defaultdict
    from decimal import Decimal

    # 1) trade_history 전체 조회 (체결 또는 부분체결만 페어링 대상)
    def _query():
        q = (
            supabase.table("trade_history")
            .select("*")
            .in_("status", ["COMPLETED", "PARTIAL"])
            .order("timestamp", desc=False)
        )
        if strategy:
            q = q.eq("strategy", strategy)
        if ticker:
            q = q.eq("ticker", ticker)
        return q.execute()

    result = await asyncio.to_thread(_query)
    rows = result.data or []

    # 2) (ticker, strategy)별 그룹화
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("ticker") or "", r.get("strategy") or "")
        grouped[key].append(r)

    # 3) 시세 캐시 (open 페어 미실현 손익용) — read-only
    try:
        from src.engine.scanner import ticker_prices  # type: ignore
    except Exception:
        ticker_prices = {}  # 모듈 미로드 환경 fallback

    pairs: list[dict] = []

    for (tkr, strat), trades in grouped.items():
        ticker_name = ""
        for t in trades:
            if t.get("ticker_name"):
                ticker_name = t["ticker_name"]
                break

        position = 0
        buy_buf: list[tuple[str, Decimal, int]] = []   # (ts, price, qty)
        sell_buf: list[tuple[str, Decimal, int]] = []

        def emit_closed():
            buy_total_qty = sum(q for _, _, q in buy_buf)
            sell_total_qty = sum(q for _, _, q in sell_buf)
            if buy_total_qty <= 0:
                return
            buy_total_amt = sum(p * q for _, p, q in buy_buf)
            sell_total_amt = sum(p * q for _, p, q in sell_buf)
            buy_avg = buy_total_amt / buy_total_qty
            sell_avg = sell_total_amt / sell_total_qty if sell_total_qty else Decimal(0)
            pl = (sell_avg - buy_avg) * sell_total_qty
            rate = ((sell_avg - buy_avg) / buy_avg * 100) if buy_avg else Decimal(0)
            buy_ts = buy_buf[0][0]
            sell_ts = sell_buf[-1][0] if sell_buf else None
            pairs.append({
                "buy_date": buy_ts[:10] if buy_ts else None,
                "buy_time": buy_ts[11:19] if buy_ts and len(buy_ts) >= 19 else None,
                "sell_date": sell_ts[:10] if sell_ts else None,
                "sell_time": sell_ts[11:19] if sell_ts and len(sell_ts) >= 19 else None,
                "ticker": tkr,
                "ticker_name": ticker_name,
                "buy_price": float(round(buy_avg, 2)),
                "buy_qty": int(buy_total_qty),
                "sell_price": float(round(sell_avg, 2)),
                "sell_qty": int(sell_total_qty),
                "profit_loss": float(round(pl, 2)),
                "profit_rate": float(round(rate, 4)),
                "status": "closed",
                "strategy": strat,
            })

        for t in trades:
            ttype = t.get("trade_type")
            try:
                p = Decimal(str(t.get("price") or 0))
                q = int(t.get("quantity") or 0)
            except Exception:
                continue
            if q <= 0:
                continue
            ts = t.get("timestamp") or ""
            if ttype == "BUY":
                buy_buf.append((ts, p, q))
                position += q
            elif ttype == "SELL":
                sell_buf.append((ts, p, q))
                position -= q
                if position <= 0:
                    emit_closed()
                    buy_buf, sell_buf = [], []
                    position = 0  # 음수 케이스(데이터 이상) 방어

        # 그룹 끝: 잔여 보유분이 있으면 open 페어
        if position > 0 and buy_buf:
            buy_total_amt = sum(p * q for _, p, q in buy_buf)
            buy_total_qty = sum(q for _, _, q in buy_buf)
            buy_avg = buy_total_amt / buy_total_qty
            buy_ts = buy_buf[0][0]
            cur_price = ticker_prices.get(tkr, {}).get("current_price", 0) or 0
            if cur_price > 0:
                cur_dec = Decimal(str(cur_price))
                pl = (cur_dec - buy_avg) * position
                rate = ((cur_dec - buy_avg) / buy_avg * 100) if buy_avg else Decimal(0)
                pl_val: float | None = float(round(pl, 2))
                rate_val: float | None = float(round(rate, 4))
            else:
                pl_val = None
                rate_val = None
            pairs.append({
                "buy_date": buy_ts[:10] if buy_ts else None,
                "buy_time": buy_ts[11:19] if buy_ts and len(buy_ts) >= 19 else None,
                "sell_date": None,
                "sell_time": None,
                "ticker": tkr,
                "ticker_name": ticker_name,
                "buy_price": float(round(buy_avg, 2)),
                "buy_qty": int(position),
                "sell_price": None,
                "sell_qty": None,
                "profit_loss": pl_val,
                "profit_rate": rate_val,
                "status": "open",
                "strategy": strat,
            })

    # 4) 신규 매수가 위로 오도록 buy_date+buy_time DESC. open이 closed보다 우선
    def _sort_key(p: dict):
        # status=open(보유 중)을 먼저, 그 안에서 buy_date DESC
        return (0 if p["status"] == "open" else 1,
                -(int((p["buy_date"] or "0").replace("-", "") or 0)),
                -(int((p["buy_time"] or "00:00:00").replace(":", "") or 0)))

    pairs.sort(key=_sort_key)
    return pairs
