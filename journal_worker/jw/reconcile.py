"""대사 — 항등식 점검(cycle412 계약 3.5절)."""
from __future__ import annotations

from datetime import timedelta

from jw.config import RECONCILE_MIN_AGE_SECONDS

_NOT_COUNTED_SOURCES = {"external", "unmatched"}


def check_identities(events: list, rows: list) -> dict:
    sell_done = sum(1 for e in events if e.get("kind") == "order_done" and e.get("side") == "SELL")
    buy_done = sum(1 for e in events if e.get("kind") == "order_done" and e.get("side") == "BUY")
    sell_rows = [r for r in rows if r.get("side") == "SELL" and r.get("source") not in _NOT_COUNTED_SOURCES]
    buy_rows = [r for r in rows if r.get("side") == "BUY" and r.get("source") not in _NOT_COUNTED_SOURCES]
    unknown_reason_sells = sum(1 for r in sell_rows if r.get("reason_code") is None)
    ok = (sell_done == len(sell_rows)) and (buy_done == len(buy_rows)) and unknown_reason_sells == 0
    return {
        "sell_done": sell_done, "sell_rows": len(sell_rows), "buy_done": buy_done,
        "buy_rows": len(buy_rows), "unknown_reason_sells": unknown_reason_sells, "ok": ok,
    }


def emit_gap(result: dict, logger) -> bool:
    if result.get("ok"):
        return False
    logger.warning(
        "[journal_gap] sell_done=%s sell_rows=%s buy_done=%s buy_rows=%s unknown_reason_sells=%s",
        result["sell_done"], result["sell_rows"], result["buy_done"], result["buy_rows"],
        result["unknown_reason_sells"],
    )
    return True


def rows_from_trade_history(trade_rows: list, journal_keys: set, notice_orders: set, *, now) -> list:
    cutoff = now - timedelta(seconds=RECONCILE_MIN_AGE_SECONDS)
    out = []
    for t in trade_rows:
        if t.get("status") not in ("COMPLETED", "PARTIAL"):
            continue
        ts = t["timestamp"]
        if ts > cutoff:
            continue
        key = (ts.date(), t["order_no"], t["trade_type"])
        if key in journal_keys:
            continue
        source = "external" if t["order_no"] in notice_orders else "unmatched"
        out.append({
            "order_no": t["order_no"], "side": t["trade_type"], "strategy": t.get("strategy"),
            "ticker": t.get("ticker"), "source": source, "reason_code": None,
            "order_date": ts.date(), "noted_at": ts,
        })
    return out
