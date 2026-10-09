"""거래 내역 라우트: /api/history/*"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.db import llm_buy_evaluations
from src.db import stock_master_daily
from src.db import trade_cost as trade_cost_db
from src.db import trade_history as trade_history_db
from src.db import trade_journal
from src.db.trade_history import get_trade_pairs, get_trades
from src.engine import cost_overlay
from src.engine import journal_view
from src.models.response import ApiResponse
from src.routes.costs import _parse_range

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])

_KST = timezone(timedelta(hours=9))
_JOURNAL_ERROR = "[journal_route_error]"


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
        # 3차 LOW 보완 — DB 조회뿐 아니라 순수 계산(`trade_costs`)의 코드 결함도 같은
        # try 안에서 삼킨다. 계산이 예외를 내도 기존 세전 응답은 그대로 두고 새 칸만
        # 건너뛴다(계약 결정 2) — 이 호출을 try 밖에 두면 그 예외가 라우트까지 전파돼
        # 200 이어야 할 응답이 500 이 된다.
        costs = cost_overlay.trade_costs(cost_rows, full_trades, rates, etf_flags=etf_flags)
    except Exception:
        logger.warning("[cost_overlay_unavailable] /api/history 실비용 조회 실패", exc_info=True)
        return

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

    # 3차 LOW 보완 — `overlay_pairs` 는 DB 조회 실패는 내부에서 이미 None 으로 삼키지만,
    # 그 뒤 순수 계산(페어별 귀속 루프)의 코드 결함까지는 못 삼킨다. 라우트 경계에서
    # 한 번 더 감싸, 계산 버그가 이 응답 전체를 500 으로 만들지 않게 한다(계약 결정 2).
    try:
        trades_by_id = await cost_overlay.overlay_pairs(pairs)
    except Exception:
        logger.warning("[cost_overlay_unavailable] /api/history/pnl 실비용 조회 실패", exc_info=True)
        trades_by_id = None

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
    아니라 `None`**(「모름」 ≠ 0, 기존 칸은 그대로 유지). 2차 보완 F4 — `slippage_n` 도
    같은 규약(종전엔 `if trades_by_id:` 가 실패(`None`)와 성공-빈 결과(`{}`)를 모두
    0 으로 뭉갰다 — `is None` 으로만 실패를 가른다).
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

    slippage_n: int | None
    if trades_by_id is None:
        slippage_n = None
    else:
        slippage_n = 0
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


# ════════════════════════════════════════════════════════════════════════════
# 거래일지 화면(1b, cycle413) — GET /journal · PUT /journal/notes/{id}
# ════════════════════════════════════════════════════════════════════════════
def _journal_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _pair_amount(pair: dict, basis: str):
    if basis == "net":
        v = pair.get("net_profit_loss")
        if v is not None:
            return v
    return pair.get("profit_loss")


def _period_overlap(pair: dict, start: date, end: date) -> bool:
    buy_d = _journal_date(pair.get("buy_date"))
    if buy_d is None or buy_d > end:
        return False
    if pair.get("status") == "open":
        return True
    sell_d = _journal_date(pair.get("sell_date"))
    return sell_d is not None and sell_d >= start


def _outcome_match(pair: dict, outcome: str, basis: str) -> bool:
    if outcome == "all":
        return True
    v = _pair_amount(pair, basis)
    if v is None:
        return False
    return v > 0 if outcome == "win" else v < 0


def _dt_rank(pair: dict, date_key: str, time_key: str) -> int:
    d = str(pair.get(date_key) or "").replace("-", "")
    t = str(pair.get(time_key) or "").replace(":", "")
    try:
        return int(d or "0") * 1_000_000 + int(t or "0")
    except ValueError:
        return 0


def _sort_pairs(pairs: list[dict], sort: str, basis: str) -> list[dict]:
    if sort == "recent":
        def key_recent(p):
            if p.get("status") == "open":
                return (0, -_dt_rank(p, "buy_date", "buy_time"))
            return (1, -_dt_rank(p, "sell_date", "sell_time"))
        return sorted(pairs, key=key_recent)

    def key_pnl(p):
        v = _pair_amount(p, basis)
        if v is None:
            return (1, 0.0)
        signed = float(v) if sort == "pnl_asc" else -float(v)
        return (0, signed)
    return sorted(pairs, key=key_pnl)


def _counts(pairs: list[dict]) -> dict:
    open_n = sum(1 for p in pairs if p.get("status") == "open")
    return {"total": len(pairs), "open": open_n, "closed": len(pairs) - open_n}


def _parse_kst_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        v = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)
        return dt.astimezone(_KST)
    except ValueError:
        return None


@router.get("/journal", response_model=ApiResponse)
async def trade_journal_view(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    strategy: str | None = Query(None),
    ticker: str | None = Query(None),
    status: Literal["all", "open", "closed"] = Query("all"),
    outcome: Literal["all", "win", "loss"] = Query("all"),
    basis: Literal["net", "gross"] = Query("net"),
    sort: Literal["recent", "pnl_asc", "pnl_desc"] = Query("recent"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """거래일지 카드 — 명세 `_workspace/red/cycle413/journal_view_spec.md` 1-1절."""
    today = datetime.now(_KST).date()
    to_ = to or today.isoformat()
    from_q = from_ or (today - timedelta(days=30)).isoformat()
    start, end = _parse_range(from_q, to_)

    try:
        record_start = await trade_journal.get_record_start()
    except Exception as exc:
        logger.warning("%s get_record_start 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
        record_start = {"orders_restored": None, "orders_live": None, "stops": None, "order_price": None}

    pairs = await get_trade_pairs(strategy=strategy, ticker=ticker)
    from src.engine.scanner import ticker_names
    for p in pairs:
        if not p.get("ticker_name"):
            p["ticker_name"] = ticker_names.get(p.get("ticker", ""), "")

    pairs = [p for p in pairs if _period_overlap(p, start, end)]
    if status != "all":
        pairs = [p for p in pairs if p.get("status") == status]

    # cycle413 보완 1차 F1 — `overlay_pairs` 의 비용 맵은 `get_trade_pairs`/
    # `get_trades_by_status` 가 돌려주는 네이티브 타입(uuid.UUID)으로 키가 걸린다.
    # 문자열화를 먼저 하면 하나도 맞지 않아 청산 카드 전부 수수료·세금 0 ·
    # 세후=세전·「추정」이 된다(판정 #1) — `/pnl` 과 같은 순서로 **먼저** 붙이고,
    # 그 뒤에 이 화면이 체결 행(문자열 id)·메모와 잇기 위해 한 번 문자열화한다.
    trades_by_id, cost_available = None, False
    try:
        trades_by_id = await cost_overlay.overlay_pairs(pairs)
        cost_available = trades_by_id is not None
    except Exception as exc:
        logger.warning("%s overlay_pairs 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)

    # `get_trade_pairs` 는 `trade_history.id`(UUID) 를 asyncpg 네이티브 타입(uuid.UUID)
    # 그대로 사영한다 — 이 화면은 그 id 로 체결 행(문자열 id)·메모를 잇고 응답
    # `anchor_trade_id` 도 문자열이어야 하므로 비용을 다 붙인 뒤 한 번 문자열화한다.
    for p in pairs:
        for key in ("buy_trade_ids", "sell_trade_ids", "partial_sell_trade_ids"):
            if p.get(key):
                p[key] = [str(i) for i in p[key]]

    pairs = [p for p in pairs if _outcome_match(p, outcome, basis)]
    counts = _counts(pairs)
    pairs = _sort_pairs(pairs, sort, basis)

    total = len(pairs)
    total_pages = (total + size - 1) // size if size > 0 else 0
    page_pairs = pairs[(page - 1) * size: page * size]

    # ── 페이지 카드 세부: 원천마다 1번 ────────────────────────────────────────
    fill_ids: set = set()
    order_nos: set[str] = set()
    anchor_ids: set = set()
    strategy_ticker_keys: set[tuple[str, str]] = set()
    tickers: set[str] = set()
    buy_dates: list[date] = []
    end_dates: list[date] = []
    opened_dts: list[datetime] = []
    now = datetime.now(_KST)

    for p in page_pairs:
        fill_ids |= {i for i in (p.get("buy_trade_ids") or [])}
        fill_ids |= {i for i in (p.get("sell_trade_ids") or [])}
        fill_ids |= {i for i in (p.get("partial_sell_trade_ids") or [])}
        order_nos |= {o for o in (p.get("buy_order_nos") or []) if o}
        order_nos |= {o for o in (p.get("sell_order_nos") or []) if o}
        if p.get("buy_trade_ids"):
            anchor_ids.add(p["buy_trade_ids"][0])
        strategy_ticker_keys.add((p.get("strategy"), p.get("ticker")))
        tickers.add(p.get("ticker"))
        bd = _journal_date(p.get("buy_date"))
        if bd:
            buy_dates.append(bd)
        sd = _journal_date(p.get("sell_date")) if p.get("status") == "closed" else today
        if sd:
            end_dates.append(sd)
        bdt = _parse_kst_dt(f"{p.get('buy_date')}T{p.get('buy_time') or '00:00:00'}+09:00") \
            if p.get("buy_date") else None
        if bdt:
            opened_dts.append(bdt)

    fills: list[dict] | None = []
    if fill_ids:
        try:
            fills = await trade_history_db.get_trades_by_ids(list(fill_ids))
        except Exception as exc:
            logger.warning("%s get_trades_by_ids 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
            # cycle413 보완 1차 F8 — 조회 실패를 빈 목록(0건)으로 위장하지 않는다.
            # `build_card(fills=None)` 이 페어로 시각·보유일을 채우고 MFE/MAE 를
            # lookup_failed 로 낸다.
            fills = None

    orders: list[dict] | None = []
    if order_nos:
        d_from = min(buy_dates) if buy_dates else start
        d_to = max(end_dates) if end_dates else end
        try:
            orders = await trade_journal.list_orders(list(order_nos), date_from=d_from, date_to=d_to)
        except Exception as exc:
            logger.warning("%s list_orders 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
            orders = None

    stops: list[dict] | None = []
    if strategy_ticker_keys:
        since = (min(opened_dts) - timedelta(seconds=60)) if opened_dts else now
        until = now + timedelta(seconds=120)
        try:
            stops = await trade_journal.list_stops(list(strategy_ticker_keys), since=since, until=until)
        except Exception as exc:
            logger.warning("%s list_stops 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
            stops = None

    notes_by_id: dict = {}
    if anchor_ids:
        try:
            note_rows = await trade_journal.list_notes(list(anchor_ids))
            notes_by_id = {n["anchor_trade_id"]: n for n in note_rows}
        except Exception as exc:
            logger.warning("%s list_notes 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)

    closes: list[dict] | None = []
    business_days: list[date] | None = []
    if tickers:
        c_from = min(buy_dates) if buy_dates else start
        c_to = max(end_dates + [today]) if end_dates else end
        try:
            closes = await stock_master_daily.get_closes_in_range(list(tickers), c_from, c_to)
        except Exception as exc:
            logger.warning("%s get_closes_in_range 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
            closes = None
        try:
            business_days = await stock_master_daily.list_business_days(c_from, c_to)
        except Exception as exc:
            logger.warning("%s list_business_days 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
            business_days = None

    llm_evals: list[dict] | None = []
    if order_nos:
        try:
            llm_evals = await llm_buy_evaluations.list_by_order_nos(list(order_nos))
        except Exception as exc:
            logger.warning("%s list_by_order_nos 실패: %r", _JOURNAL_ERROR, exc, exc_info=True)
            llm_evals = None

    per_fill_costs: dict | None = None
    if trades_by_id is not None:
        # `trades_by_id` 키는 `get_trades_by_status` 가 돌려주는 네이티브 타입(uuid.UUID)
        # 그대로다 — 이 화면의 체결 id(위에서 문자열화)와 잇기 위해 문자열화한다.
        per_fill_costs = {
            str(tid): {"fee": t.get("fee"), "tax": t.get("tax"), "cost_status": t.get("cost_status"),
                      "allocated": t.get("allocated")}
            for tid, t in trades_by_id.items()
        }

    cards = []
    for p in page_pairs:
        want_ids = set(p.get("buy_trade_ids") or []) | set(p.get("sell_trade_ids") or []) \
            | set(p.get("partial_sell_trade_ids") or [])
        pair_fills = None if fills is None else [f for f in fills if f.get("id") in want_ids]
        note = notes_by_id.get(p["buy_trade_ids"][0]) if p.get("buy_trade_ids") else None
        cards.append(journal_view.build_card(
            p, fills=pair_fills, orders=orders, stops=stops, note=note, closes=closes,
            business_days=business_days, llm_evals=llm_evals, costs=per_fill_costs,
            record_start=record_start, now=now,
        ))

    return ApiResponse(success=True, data={
        "record_start": record_start,
        "filters": {"from": start.isoformat(), "to": end.isoformat(), "strategy": strategy,
                   "ticker": ticker, "status": status, "outcome": outcome, "basis": basis, "sort": sort},
        "counts": counts, "page": page, "size": size, "total": total, "total_pages": total_pages,
        "cost_available": cost_available, "cards": cards,
    })


class _JournalNoteIn(BaseModel):
    body: str


@router.put("/journal/notes/{anchor_trade_id}", response_model=ApiResponse)
async def put_journal_note(anchor_trade_id: str, payload: _JournalNoteIn):
    """메모 upsert/삭제 — 명세 1-3절(D2)."""
    try:
        uuid.UUID(anchor_trade_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="anchor_trade_id 는 UUID 꼴이어야 한다")

    body = payload.body
    stripped = body.strip()
    if len(stripped) > 4000:
        raise HTTPException(status_code=422, detail="메모는 4,000자 이하여야 한다")

    rows = await trade_history_db.get_trades_by_ids([anchor_trade_id])
    buy_row = next((r for r in rows if str(r.get("trade_type") or "").upper() == "BUY"), None)
    if buy_row is None:
        raise HTTPException(status_code=404, detail="그 매수 체결 행이 없다")

    if not stripped:
        await trade_journal.delete_note(anchor_trade_id)
        return ApiResponse(success=True, data=None)

    strategy = buy_row.get("strategy")
    ticker = buy_row.get("ticker")
    buy_date = _journal_date(buy_row.get("timestamp"))
    saved = await trade_journal.upsert_note(anchor_trade_id, stripped, strategy=strategy, ticker=ticker,
                                            buy_date=buy_date)
    return ApiResponse(success=True, data=saved)
