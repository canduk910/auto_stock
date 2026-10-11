"""cycle446 — 사후 채움(설계 §5.3). 매일 아침 실행 첫 단계에서 돈다. **never-raise**."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 거래소가 체결했는데(확정 일봉) 통보가 유실돼 묶여 있을 수 있는 포지션은 10거래일
# 넘겨도 못 채우면 unknown 으로 접는다(설계 §5.3).
_UNKNOWN_AFTER_DAYS = 10


async def fill_next_open(db, *, today: date) -> int:
    """`act_date < 오늘` 이고 비어 있는 `next_open_won` 을 그날 시가로 채운다."""
    filled = 0
    try:
        rows = await db.list_open_missing_next_open(before=today)
    except Exception as exc:
        log.warning("[exit_ai_next_open_list_error] %s", exc)
        return 0
    for row in rows:
        try:
            open_price = await db.fetch_open_price(row["ticker"], row["act_date"])
            if open_price is None:
                continue
            await db.fill_next_open(row["id"], open_price, datetime.now(KST))
            filled += 1
        except Exception as exc:  # pragma: no cover — 행 단위 격리
            log.warning("[exit_ai_next_open_fill_error] id=%s err=%s", row.get("id"), exc)
            continue
    return filled


async def fill_outcomes(db, *, today: date, held_keys: set) -> int:
    """`outcome_status='open'` 인 포지션이 오늘 G1(`held_keys`)에 없으면 실제 매도를
    `trade_history` 로 찾아 닫는다. `held_keys` = `{(strategy_id, ticker, buy_date, buy_order_no)}`."""
    filled = 0
    try:
        rows = await db.list_open_evaluations()
    except Exception as exc:
        log.warning("[exit_ai_outcome_list_error] %s", exc)
        return 0
    for row in rows:
        key = (row["strategy_id"], row["ticker"], row["buy_date"], row["buy_order_no"] or "")
        if key in held_keys:
            continue
        try:
            n = await _fill_one_outcome(db, row, today=today)
            filled += n
        except Exception as exc:  # pragma: no cover — 행 단위 격리
            log.warning("[exit_ai_outcome_fill_error] id=%s err=%s", row.get("id"), exc)
            continue
    return filled


async def _fill_one_outcome(db, row: dict, *, today: date) -> int:
    act_date = row.get("act_date")
    quantity = row.get("quantity") or 0
    try:
        since = datetime.combine(act_date, datetime.min.time(), tzinfo=KST)
    except Exception:
        return 0
    trades = await db.fetch_sell_trades(row["strategy_id"], row["ticker"], since)
    if not trades:
        if act_date is not None and (today - act_date).days > _UNKNOWN_AFTER_DAYS:
            await db.fill_outcome(
                row["id"], outcome_status="unknown", exit_date=None, exit_vwap_after_won=None,
                sold_qty_after=None, exit_reason=None, exit_is_manual=None, now=datetime.now(KST),
            )
            return 1
        return 0

    total_qty = sum(float(t.get("quantity") or 0) for t in trades)
    if total_qty < quantity:
        if act_date is not None and (today - act_date).days > _UNKNOWN_AFTER_DAYS:
            await db.fill_outcome(
                row["id"], outcome_status="unknown", exit_date=None, exit_vwap_after_won=None,
                sold_qty_after=None, exit_reason=None, exit_is_manual=None, now=datetime.now(KST),
            )
            return 1
        return 0

    last_trade = trades[-1]
    exit_date = last_trade.get("timestamp").date() if isinstance(last_trade.get("timestamp"), datetime) else None
    exit_is_manual = None
    try:
        journal_row = await db.fetch_journal_order(exit_date, last_trade.get("order_no") or "", "SELL")
        if journal_row is not None:
            exit_is_manual = journal_row.get("source") in ("external", "unmatched")
    except Exception:
        exit_is_manual = None

    try:
        notional = sum(float(t.get("price") or 0) * float(t.get("quantity") or 0) for t in trades)
        exit_vwap = (notional / total_qty) if total_qty else None
    except Exception:
        exit_vwap = None

    await db.fill_outcome(
        row["id"], outcome_status="closed", exit_date=exit_date,
        exit_vwap_after_won=exit_vwap, sold_qty_after=int(total_qty),
        exit_reason=None, exit_is_manual=exit_is_manual, now=datetime.now(KST),
    )
    return 1
