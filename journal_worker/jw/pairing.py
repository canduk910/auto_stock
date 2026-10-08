"""로그 이벤트를 거래일지 행으로 짝짓는다(cycle412 계약 3.3절).

핵심 규약(계약 정본):
- 앵커 줄(접수·완료·폴백·재주문·수동)은 **한 회전 보류** 뒤 다음 ``drain()`` 에서 나간다.
- BUY 판단가(신호)는 **emission 시점**(보류가 끝난 뒤)에 그 시점의 링/로그 신호 이력으로 다시 찾는다
  — 신호가 보류 중에 도착해도 쓸 수 있게.
- SELL 쪽 사유·발동선·판단가·유효선은 전부 "접수 시각 이전" 만 보는 역방향 조회라 앵커 처리
  시점에 즉시 계산해도 결과가 같다.
"""
from __future__ import annotations

from collections import deque
from datetime import date, timedelta

from jw.config import BUY_SIGNAL_LOG_WINDOW_SECONDS, REASON_WINDOW_SECONDS, SIGNAL_RING_TTL_SECONDS

_CORRECTABLE = {"STOP_LOSS", "TRAILING_STOP", "TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT"}
_PATH_SOURCE = {"accept": "log_harvest", "manual": "manual_api", "fallback": "fallback_inferred",
                "reorder": "reorder_inferred"}
_SNAP_FIELDS = ("stop_price", "stop_kind", "target_price", "target_hit", "arm_price")
_G1_KEEP = ("stop_price", "stop_source", "buy_price", "buy_date", "order_no", "target_price", "target_source",
            "kk_arm_price")
_NON_PRICE_CODES = {"TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT"}
_HIST = 8
_KEEP = timedelta(seconds=SIGNAL_RING_TTL_SECONDS)


def _parse_date(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    return date.fromisoformat(s)


def _combine_time(observed_at, time_str):
    h, m, s = (int(x) for x in time_str.split(":"))
    return observed_at.replace(hour=h, minute=m, second=s, microsecond=0)


class Pairer:
    def __init__(self, *, source: str = "log_harvest"):
        self._source = source
        self._incoming: list[dict] = []
        self._ready: list[dict] = []
        self._last_trade_strategies: dict[str, str] = {}

        self._live = source == "log_harvest"
        self._ring: dict[tuple, list[dict]] = {}
        self._params_history: deque = deque(maxlen=_HIST)
        self._g1_history: deque = deque(maxlen=_HIST)

        self._buy_signal_events: list[dict] = []
        self._exit_reason_events: list[dict] = []
        self._ndc_defer_events: list[dict] = []
        self._status_exit_events: list[dict] = []

        self._order_notices: dict[str, list[dict]] = {}
        self._recent_done: list[dict] = []
        self._last_buy_accept: dict = {}
        self._anchor_order_nos: set = set()
        self._notice_new_order_nos: set = set()
        self._last_sell_resolved: dict[str, dict] = {}
        self._watermark = None
        self._day = None

    # ── 입력 ──────────────────────────────────────────────────────────────

    def feed_snapshot(self, g0, g1, observed_at) -> None:
        if g0 is not None:
            params = self._update_ring(g0, observed_at)
            self._params_history.append((observed_at, params))
        if g1 is not None:
            items = {(it["strategy_id"], it["ticker"]): {k: it.get(k) for k in _G1_KEEP}
                     for it in (g1.get("items") or [])}
            self._g1_history.append((observed_at, items))

    def _update_ring(self, g0, observed_at):
        cutoff = observed_at - timedelta(seconds=SIGNAL_RING_TTL_SECONDS)
        params_by_sid = {}
        for sid, strat in (g0.get("strategies") or {}).items():
            params_copy = dict(strat.get("params") or {})
            params_by_sid[sid] = params_copy
            for sig in strat.get("buy_signals") or []:
                ticker = sig.get("ticker")
                time_str = sig.get("time")
                signal_dt = _combine_time(observed_at, time_str)
                if signal_dt < cutoff:
                    continue
                lst = self._ring.setdefault((sid, ticker), [])
                if any(e["signal"].get("time") == time_str for e in lst):
                    continue
                lst.append({"signal_dt": signal_dt, "signal": dict(sig), "params": params_copy})
        for k in list(self._ring.keys()):
            kept = [e for e in self._ring[k] if e["signal_dt"] >= cutoff]
            if kept:
                self._ring[k] = kept
            else:
                del self._ring[k]
        return params_by_sid

    def _purge(self, ts):
        if not self._live:
            return
        if self._watermark is None or ts > self._watermark:
            self._watermark = ts
        if self._day != ts.date():
            self._day = ts.date()
            self._ndc_defer_events = [e for e in self._ndc_defer_events if e["ts"].date() == ts.date()]
            self._anchor_order_nos = set()
            self._notice_new_order_nos = set()
        cutoff = self._watermark - _KEEP
        if len(self._exit_reason_events) > 64 or len(self._buy_signal_events) > 64 or \
                len(self._status_exit_events) > 64 or len(self._recent_done) > 64 or len(self._order_notices) > 64:
            self._exit_reason_events = [e for e in self._exit_reason_events if e["ts"] >= cutoff]
            self._buy_signal_events = [e for e in self._buy_signal_events if e["ts"] >= cutoff]
            self._status_exit_events = [e for e in self._status_exit_events if e["ts"] >= cutoff]
            self._recent_done = [d for d in self._recent_done if not d["used"] and d["ts"] >= cutoff]
            self._order_notices = {k: v for k, v in self._order_notices.items() if v[-1]["ts"] >= cutoff}

    def feed_events(self, events) -> None:
        for ev in events:
            if ev.get("ts") is not None:
                self._purge(ev["ts"])
            kind = ev.get("kind")
            if kind == "buy_signal":
                self._buy_signal_events.append({"strategy": ev["strategy"], "ticker": ev["ticker"],
                                                 "ts": ev["ts"], "price": ev.get("price")})
            elif kind == "exit_reason":
                self._exit_reason_events.append(ev)
            elif kind == "ndc_defer":
                self._ndc_defer_events.append(ev)
            elif kind == "status_exit_fire":
                self._status_exit_events.append(ev)
            elif kind == "order_notice":
                self._order_notices.setdefault(ev["order_no"], []).append(ev)
                if ev.get("rctf") == "0":
                    self._notice_new_order_nos.add(ev["order_no"])
            elif kind == "order_done":
                self._recent_done.append(dict(ev, used=False))
            elif kind == "buy_accept":
                self._handle_buy_accept(ev)
            elif kind == "sell_accept":
                self._handle_sell_accept(ev)
            elif kind == "manual_sell_accept":
                self._handle_manual_sell_accept(ev)
            elif kind == "sell_fallback":
                self._handle_sell_fallback(ev)
            elif kind == "buy_fallback":
                self._handle_buy_fallback(ev)
            elif kind == "reorder":
                self._handle_reorder(ev)

    # ── 앵커 처리 ─────────────────────────────────────────────────────────

    def _pop_matching_done(self, *, side, ticker, ts, qty=None):
        best = None
        for d in self._recent_done:
            if d["used"] or d["side"] != side or d["ticker"] != ticker:
                continue
            if qty is not None and d["qty"] != qty:
                continue
            if best is None or abs((d["ts"] - ts).total_seconds()) <= abs((best["ts"] - ts).total_seconds()):
                best = d
        if best is not None:
            best["used"] = True
        return best

    def _mark_done(self, order_no):
        for d in self._recent_done:
            if d["order_no"] == order_no:
                d["used"] = True

    def _handle_buy_accept(self, ev):
        order_no = ev["order_no"]
        self._anchor_order_nos.add(order_no)
        self._mark_done(order_no)
        self._last_buy_accept[(ev["strategy"], ev["ticker"])] = {"price": ev["price"], "ts": ev["ts"]}
        self._incoming.append({
            "side": "BUY", "order_no": order_no, "ticker": ev["ticker"], "strategy": ev["strategy"],
            "order_price": ev["price"], "path": "accept", "ts": ev["ts"], "parent_order_no": None,
            "stop_event": None,
        })

    def _handle_buy_fallback(self, ev):
        match = self._pop_matching_done(side="BUY", ticker=ev["ticker"], ts=ev["ts"])
        if match is None:
            return
        order_no = match["order_no"]
        self._anchor_order_nos.add(order_no)
        self._incoming.append({
            "side": "BUY", "order_no": order_no, "ticker": ev["ticker"], "strategy": None,
            "order_price": ev["price"], "path": "fallback", "ts": ev["ts"], "parent_order_no": None,
            "stop_event": None,
        })

    def _handle_sell_accept(self, ev):
        order_no = ev["order_no"]
        self._anchor_order_nos.add(order_no)
        self._mark_done(order_no)
        anchor = self._build_sell_anchor(order_no=order_no, ticker=ev["ticker"], strategy=ev["strategy"],
                                          raw_name=ev["signal"], ts=ev["ts"], path="accept",
                                          order_price=None, parent_order_no=None)
        self._remember_sell(ev["ticker"], anchor)
        self._incoming.append(anchor)

    def _handle_manual_sell_accept(self, ev):
        order_no = ev["order_no"]
        self._anchor_order_nos.add(order_no)
        self._mark_done(order_no)
        anchor = self._build_sell_anchor(order_no=order_no, ticker=ev["ticker"], strategy=ev["strategy"],
                                          raw_name="MANUAL", ts=ev["ts"], path="manual",
                                          order_price=None, parent_order_no=None)
        self._incoming.append(anchor)

    def _handle_sell_fallback(self, ev):
        order_no = ev["order_no"]
        self._anchor_order_nos.add(order_no)
        self._mark_done(order_no)
        anchor = self._build_sell_anchor(order_no=order_no, ticker=ev["ticker"], strategy=ev["strategy"],
                                          raw_name=None, ts=ev["ts"], path="fallback",
                                          order_price=ev["price"], parent_order_no=None)
        self._remember_sell(ev["ticker"], anchor)
        self._incoming.append(anchor)

    def _handle_reorder(self, ev):
        ticker = ev["ticker"]
        match = self._pop_matching_done(side="SELL", ticker=ticker, ts=ev["ts"], qty=ev["qty"])
        if match is None:
            return
        order_no = match["order_no"]
        self._anchor_order_nos.add(order_no)
        parent = self._last_sell_resolved.get(ticker) or {}
        strategy = parent.get("strategy")
        reason_code = parent.get("reason_code")
        reason_sub = parent.get("reason_sub")
        parent_order_no = parent.get("order_no")

        effective_line, signal_extra, stop_event = self._snapshot_exit(strategy, ticker, ev["ts"],
                                                                         order_no)
        signal = {"signal_name": reason_code, "reason_line": None, "phrase": None, "judge_src": None}
        signal.update(signal_extra)
        self._incoming.append({
            "side": "SELL", "order_no": order_no, "ticker": ticker, "strategy": strategy, "ts": ev["ts"],
            "path": "reorder", "order_price": None, "parent_order_no": parent_order_no,
            "reason_code": reason_code, "reason_sub": reason_sub, "fired_line": None,
            "judge_price": None, "effective_line": effective_line, "signal": signal,
            "stop_event": stop_event,
        })

    def _remember_sell(self, ticker, anchor):
        self._last_sell_resolved[ticker] = {
            "order_no": anchor["order_no"], "strategy": anchor["strategy"],
            "reason_code": anchor["reason_code"], "reason_sub": anchor["reason_sub"],
        }

    # ── SELL 세부 해석 ────────────────────────────────────────────────────

    def _last_exit_reason(self, strategy, ticker, ts):
        window_start = ts - timedelta(seconds=REASON_WINDOW_SECONDS)
        cands = [e for e in self._exit_reason_events if e["strategy"] == strategy and e["ticker"] == ticker
                 and window_start <= e["ts"] <= ts]
        return max(cands, key=lambda e: e["ts"]) if cands else None

    def _last_ndc_defer(self, strategy, ticker, ts):
        cands = [e for e in self._ndc_defer_events if e["strategy"] == strategy and e["ticker"] == ticker
                 and e["ts"].date() == ts.date() and e["ts"] <= ts]
        return max(cands, key=lambda e: e["ts"]) if cands else None

    def _last_status_exit(self, strategy, ticker, ts):
        window_start = ts - timedelta(seconds=REASON_WINDOW_SECONDS)
        cands = [e for e in self._status_exit_events if e["strategy"] == strategy and e["ticker"] == ticker
                 and window_start <= e["ts"] <= ts]
        return max(cands, key=lambda e: e["ts"]) if cands else None

    def _last_g1_item_before(self, strategy, ticker, ts):
        for snap_ts, items in reversed(self._g1_history):
            if snap_ts <= ts and (strategy, ticker) in items:
                return snap_ts, items[(strategy, ticker)]
        return None

    def _last_params_before(self, ts, strategy):
        for snap_ts, params in reversed(self._params_history):
            if snap_ts <= ts:
                return params.get(strategy)
        return None

    def _resolve_buy_price(self, strategy, ticker, ts, exit_ev):
        if exit_ev and exit_ev.get("buy_price") is not None:
            return exit_ev["buy_price"]
        snap = self._last_g1_item_before(strategy, ticker, ts)
        if snap and snap[1].get("buy_price") is not None:
            return snap[1]["buy_price"]
        last = self._last_buy_accept.get((strategy, ticker))
        if last is not None and last["ts"] <= ts:
            return last["price"]
        return None

    def _compute_fired_line(self, strategy, ticker, ts, exit_ev, buy_price):
        if not exit_ev:
            return None
        if exit_ev.get("line") is not None:
            return exit_ev["line"]
        if exit_ev.get("threshold") is not None and exit_ev.get("buy_price") is not None:
            return round(exit_ev["buy_price"] * (1 + exit_ev["threshold"] / 100))
        if exit_ev.get("reason_code") in _NON_PRICE_CODES:
            return None
        if exit_ev.get("phrase") in ("ltv_intraday_stop", "ltv_limit_up_stop"):
            params = self._last_params_before(ts, strategy)
            if params is None or buy_price is None:
                return None
            key = "intraday_stop_loss" if exit_ev.get("mode") == "intraday" else "overnight_stop_loss"
            pct = params.get(key)
            if pct is None:
                return None
            return round(buy_price * (1 + pct / 100))
        snap = self._last_g1_item_before(strategy, ticker, ts)
        if snap is None:
            return None
        return snap[1].get("stop_price")

    def _compute_judge(self, exit_ev, buy_price):
        if not exit_ev:
            return None, None, None
        if exit_ev.get("current_price") is not None:
            return exit_ev["current_price"], "log_price", None
        if exit_ev.get("pct") is not None:
            if buy_price is None:
                return None, None, None
            return round(buy_price * (1 + exit_ev["pct"] / 100)), "log_pct", None
        if exit_ev.get("line") is not None:
            return None, None, exit_ev["line"]
        return None, None, None

    def _snapshot_exit(self, strategy, ticker, ts, order_no):
        """접수 시각 이전 마지막 G1 스냅샷에서 effective_line·signal 보강·exit 사건을 만든다."""
        snap = self._last_g1_item_before(strategy, ticker, ts)
        if snap is None:
            return None, {}, None
        snap_ts, item = snap
        effective_line = item.get("stop_price")
        snapshot_age_s = int((ts - snap_ts).total_seconds())
        stop_kind = item.get("stop_source")
        extra = {"snapshot_age_s": snapshot_age_s, "stop_kind": stop_kind}
        stop_event = {
            "strategy": strategy, "ticker": ticker, "buy_date": _parse_date(item.get("buy_date")),
            "pos_order_no": item.get("order_no"), "observed_at": ts, "event": "exit",
            "stop_price": effective_line, "stop_kind": stop_kind,
            "target_price": item.get("target_price"),
            "target_hit": item.get("target_source") == "measured_move_hit",
            "arm_price": item.get("kk_arm_price"),
            "inputs": {"snapshot_age_s": snapshot_age_s, "sell_order_no": order_no},
        }
        return effective_line, extra, stop_event

    def _resolve_sell_details(self, *, strategy, ticker, raw_name, ts, order_no):
        exit_ev = None
        reason_code = raw_name
        reason_sub = None
        gap = None
        gap_threshold = None
        if raw_name is None or raw_name in _CORRECTABLE:
            exit_ev = self._last_exit_reason(strategy, ticker, ts)
            if exit_ev:
                reason_code = exit_ev["reason_code"]
        elif raw_name == "NEXT_DAY_CLEAR":
            ndc = self._last_ndc_defer(strategy, ticker, ts)
            if ndc:
                reason_sub = ndc.get("reason_sub")
                gap = ndc.get("gap")
                gap_threshold = ndc.get("threshold")
        elif raw_name == "STATUS_EXIT":
            se = self._last_status_exit(strategy, ticker, ts)
            if se:
                reason_sub = se.get("reason")
        # FORCE_CLEAR / MANUAL: 사유 줄을 보지 않는다.

        buy_price = self._resolve_buy_price(strategy, ticker, ts, exit_ev)
        fired_line = self._compute_fired_line(strategy, ticker, ts, exit_ev, buy_price)
        judge_price, judge_src, judge_upper = self._compute_judge(exit_ev, buy_price)

        signal = {"signal_name": raw_name, "reason_line": exit_ev["raw"] if exit_ev else None,
                  "phrase": exit_ev["phrase"] if exit_ev else None, "judge_src": judge_src}
        if raw_name == "NEXT_DAY_CLEAR":
            signal["gap"] = gap
            signal["gap_threshold"] = gap_threshold
        if judge_upper is not None:
            signal["judge_upper"] = judge_upper
        if exit_ev:
            for k in ("buy_price", "pct", "threshold", "current_price", "line", "target", "mode"):
                if exit_ev.get(k) is not None:
                    signal[k] = exit_ev[k]

        effective_line, snap_extra, stop_event = self._snapshot_exit(strategy, ticker, ts, order_no)
        signal.update(snap_extra)

        return reason_code, reason_sub, fired_line, judge_price, effective_line, signal, stop_event

    def _build_sell_anchor(self, *, order_no, ticker, strategy, raw_name, ts, path, order_price,
                            parent_order_no):
        reason_code, reason_sub, fired_line, judge_price, effective_line, signal, stop_event = \
            self._resolve_sell_details(strategy=strategy, ticker=ticker, raw_name=raw_name, ts=ts,
                                        order_no=order_no)
        return {
            "side": "SELL", "order_no": order_no, "ticker": ticker, "strategy": strategy, "ts": ts,
            "path": path, "order_price": order_price, "parent_order_no": parent_order_no,
            "reason_code": reason_code, "reason_sub": reason_sub, "fired_line": fired_line,
            "judge_price": judge_price, "effective_line": effective_line, "signal": signal,
            "stop_event": stop_event,
        }

    # ── BUY 신호 해석(emission 시점에 다시 찾는다) ───────────────────────────

    def _resolve_buy_signal(self, strategy, ticker, ts):
        entries = self._ring.get((strategy, ticker), [])
        candidates = [e for e in entries if e["signal_dt"] <= ts]
        if candidates:
            chosen = max(candidates, key=lambda e: e["signal_dt"])
            sig = dict(chosen["signal"])
            sig["signal_src"] = "ring"
            return sig, dict(chosen["params"]), chosen["signal"].get("price")
        window_start = ts - timedelta(seconds=BUY_SIGNAL_LOG_WINDOW_SECONDS)
        cands = [e for e in self._buy_signal_events if e["strategy"] == strategy and e["ticker"] == ticker
                 and window_start <= e["ts"] <= ts]
        if cands:
            chosen = max(cands, key=lambda e: e["ts"])
            return {"signal_src": "log_only"}, None, chosen["price"]
        return {"signal_src": "none"}, None, None

    # ── 출력 ──────────────────────────────────────────────────────────────

    def _resolve_division(self, order_no):
        for n in self._order_notices.get(order_no, []):
            if n.get("rctf") == "0":
                return n.get("division")
        return None

    def _resolve_source(self, path):
        if self._source != "log_harvest":
            return self._source
        return _PATH_SOURCE.get(path, "log_harvest")

    def _finalize(self, anchor):
        order_division = self._resolve_division(anchor["order_no"])
        source = self._resolve_source(anchor["path"])
        strategy, strategy_src = anchor["strategy"], None
        if strategy is None:
            strategy = self._last_trade_strategies.get(anchor["order_no"])
            strategy_src = "trade_history" if strategy else "unknown"
            strategy = strategy or "unknown"
        if anchor["side"] == "BUY":
            signal, params, judge_price = self._resolve_buy_signal(strategy, anchor["ticker"],
                                                                     anchor["ts"])
            signal["path"] = anchor["path"]
            if strategy_src:
                signal["strategy_src"] = strategy_src
            return {
                "order_date": anchor["ts"].date(), "order_no": anchor["order_no"], "side": "BUY",
                "strategy": strategy, "ticker": anchor["ticker"], "source": source,
                "reason_code": "ENTRY", "reason_sub": None, "judge_price": judge_price,
                "order_price": anchor["order_price"], "order_division": order_division,
                "exchange": None, "parent_order_no": None, "fired_line": None, "effective_line": None,
                "signal": signal, "params": params, "noted_at": anchor["ts"],
            }
        signal = dict(anchor["signal"])
        signal["path"] = anchor["path"]
        if strategy_src:
            signal["strategy_src"] = strategy_src
        return {
            "order_date": anchor["ts"].date(), "order_no": anchor["order_no"], "side": "SELL",
            "strategy": strategy, "ticker": anchor["ticker"], "source": source,
            "reason_code": anchor["reason_code"], "reason_sub": anchor["reason_sub"],
            "judge_price": anchor["judge_price"], "order_price": anchor.get("order_price"),
            "order_division": order_division, "exchange": None,
            "parent_order_no": anchor.get("parent_order_no"), "fired_line": anchor["fired_line"],
            "effective_line": anchor["effective_line"], "signal": signal, "params": None,
            "noted_at": anchor["ts"],
        }

    def drain(self, *, final: bool = False, trade_strategies: dict | None = None) -> dict:
        self._last_trade_strategies = dict(trade_strategies or {})
        if final:
            pending = self._ready + self._incoming
            self._ready = []
            self._incoming = []
        else:
            pending = self._ready
            self._ready = self._incoming
            self._incoming = []
        orders = []
        stops = []
        for anchor in pending:
            orders.append(self._finalize(anchor))
            if anchor.get("stop_event"):
                stops.append(anchor["stop_event"])
        return {"orders": orders, "stops": stops}

    def external_notice_orders(self) -> set:
        return {o for o in self._notice_new_order_nos if o not in self._anchor_order_nos}
