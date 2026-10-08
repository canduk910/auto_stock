"""손절선 사건(R8, cycle412 계약 3.4절) — ``StopTracker``.

한 회전·한 (전략,종목)에 사건은 최대 1개, 우선순위 ``first > boot > paused > eod > change``.
"""
from __future__ import annotations

from datetime import date, time as dt_time

_FIELDS = ("stop_price", "stop_kind", "target_price", "target_hit", "arm_price")


def _parse_date(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    return date.fromisoformat(s)


def _differs_any(last, current):
    if last is None:
        return True
    return any(last.get(k) != current.get(k) for k in _FIELDS)


def _change_triggered(last, current):
    if last is None:
        return True
    lp, cp = last.get("stop_price"), current.get("stop_price")
    stop_changed = False
    if lp != cp:
        if lp is None or cp is None:
            stop_changed = True
        elif cp < lp:
            stop_changed = True
        else:
            base = abs(lp) if lp else None
            stop_changed = True if not base else (cp - lp) / base * 100 >= 0.5
    other_changed = (last.get("stop_kind") != current.get("stop_kind") or
                      last.get("target_price") != current.get("target_price") or
                      last.get("target_hit") != current.get("target_hit") or
                      last.get("arm_price") != current.get("arm_price"))
    return stop_changed or other_changed


class StopTracker:
    def __init__(self, *, last_rows: dict | None = None):
        self._last: dict = {}
        self._known_keys: set = set()
        self._last_arm_price: dict = {}
        for key, row in (last_rows or {}).items():
            self._last[key] = {
                "stop_price": row.get("stop_price"), "stop_kind": row.get("stop_kind"),
                "target_price": row.get("target_price"), "target_hit": bool(row.get("target_hit")),
                "arm_price": row.get("arm_price"),
            }
            self._known_keys.add(key)
            if row.get("arm_price") is not None:
                self._last_arm_price[key] = row["arm_price"]
        self._enabled_state: dict = {}
        self._eod_done: dict = {}
        self._post_boot_phase = None  # None | "skip" | "boot_next"

    def observe(self, *, observed_at, g0, g1, new_holding_keys=frozenset()) -> list:
        if g0 is None or not g0.get("running") or g0.get("phase") == "idle" or g1 is None:
            return []
        if g0.get("phase") == "booting":
            self._post_boot_phase = "skip"
            return []
        if self._post_boot_phase == "skip":
            self._post_boot_phase = "boot_next"
            for item in (g1.get("items") or []):
                self._known_keys.add((item["strategy_id"], item["ticker"]))
            return []
        boot_next = self._post_boot_phase == "boot_next"
        self._post_boot_phase = None

        enabled_map = {sid: s.get("enabled", True) for sid, s in (g0.get("strategies") or {}).items()}
        today = observed_at.date()
        events = []
        for item in (g1.get("items") or []):
            sid, ticker = item["strategy_id"], item["ticker"]
            key = (sid, ticker)
            enabled = enabled_map.get(sid, True)

            arm_price = item.get("kk_arm_price")
            if arm_price is not None:
                self._last_arm_price[key] = arm_price
            effective_arm = arm_price if arm_price is not None else self._last_arm_price.get(key)

            current = {
                "stop_price": item.get("stop_price"), "stop_kind": item.get("stop_source"),
                "target_price": item.get("target_price"),
                "target_hit": item.get("target_source") == "measured_move_hit",
                "arm_price": effective_arm,
            }
            is_new = key not in self._known_keys or key in new_holding_keys
            was_enabled = self._enabled_state.get(key, True)
            last = self._last.get(key)

            cond_first = is_new
            cond_paused = (not cond_first) and (not enabled) and was_enabled
            cond_eod = (not cond_first) and observed_at.time() >= dt_time(15, 30) and \
                self._eod_done.get(key) != today
            cond_boot = (not cond_first) and boot_next and _differs_any(last, current)
            cond_change = (not cond_first and not cond_paused and not cond_eod and not boot_next and
                           _change_triggered(last, current))

            if cond_eod:
                self._eod_done[key] = today

            chosen = None
            if cond_first:
                chosen = "first"
            elif cond_boot:
                chosen = "boot"
            elif cond_paused:
                chosen = "paused"
            elif cond_eod:
                chosen = "eod"
            elif cond_change:
                chosen = "change"

            self._known_keys.add(key)
            self._enabled_state[key] = enabled

            if chosen is not None:
                self._last[key] = current
                events.append({
                    "strategy": sid, "ticker": ticker, "buy_date": _parse_date(item.get("buy_date")),
                    "pos_order_no": item.get("order_no"), "observed_at": observed_at, "event": chosen,
                    "stop_price": current["stop_price"], "stop_kind": current["stop_kind"],
                    "target_price": current["target_price"], "target_hit": current["target_hit"],
                    "arm_price": current["arm_price"],
                    "inputs": {
                        "buy_price": item.get("buy_price"), "quantity": item.get("quantity"),
                        "high_since_buy": item.get("high_since_buy"), "entry_atr": item.get("entry_atr"),
                        "kk_armed": item.get("kk_armed"), "stop_source": item.get("stop_source"),
                        "target_source": item.get("target_source"),
                    },
                })
        return events
