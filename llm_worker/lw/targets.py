"""cycle446 — 대상 선정(설계 §2.1). 순수 함수. `src`·I/O·`await` 0."""
from __future__ import annotations

from datetime import date

from lw.config import EXIT_AI_STRATEGIES


def _parse_date(value) -> "date | None":
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    return None


def select_targets(g1_items, *, bar_date: date) -> list:
    """G1 `items` 중 — 허용 전략 ∧ `buy_date <= bar_date`(최소 한 번 장 마감 넘긴 보유) ∧
    `quantity > 0`. 멱등·never-raise(이상 item 은 건너뛴다)."""
    out = []
    for item in g1_items or []:
        try:
            if not isinstance(item, dict):
                continue
            sid = item.get("strategy_id")
            if sid not in EXIT_AI_STRATEGIES:
                continue
            qty = item.get("quantity")
            if not isinstance(qty, (int, float)) or qty <= 0:
                continue
            buy_date = _parse_date(item.get("buy_date"))
            if buy_date is None or buy_date > bar_date:
                continue
            out.append(item)
        except Exception:
            continue
    return out


def target_key(strategy_id: str, ticker: str, buy_date, buy_order_no: str) -> tuple:
    return (str(strategy_id), str(ticker), str(buy_date), str(buy_order_no or ""))
