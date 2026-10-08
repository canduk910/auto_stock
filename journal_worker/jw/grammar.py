"""운영 로그 한 줄 → 이벤트 dict(cycle412 계약 3.2절). 문법 리터럴은 이 모듈 1곳에만 둔다.

``parse_line(line)`` 이 전부다 — 모르는 줄·다른 로거는 ``None``.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

OE = "src.engine.order_engine"
API_ORDER = "src.api.order"
REALTIME = "src.realtime.handler"
ROUTES = "src.routes.trading"
SCHEDULER = "src.engine.scheduler"
STATUS_EXIT = "src.engine.status_exit_watch"
STRAT_PREFIX = "src.engine.strategies."

_SIGNAL_NAMES = {"STOP_LOSS", "TRAILING_STOP", "TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT",
                 "FORCE_CLEAR", "NEXT_DAY_CLEAR", "STATUS_EXIT"}

_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[(\S+)\s*\] (\S+) — (.*)$"
)


def _ticker_name(token: str):
    """끝의 ``(코드)`` 를 ticker 로, 그 앞을 name 으로. 괄호 없으면 (token, None)."""
    m = re.search(r"\(([^()]*)\)$", token)
    if not m:
        return token, None
    name = token[:m.start()]
    return m.group(1), (name or None)


def _kv(text: str) -> dict:
    return dict(re.findall(r"(\w+)=(\S*)", text))


def _as_int(s):
    return int(s) if s not in (None, "") else None


# ── 접수·완료·폴백·재주문 (OE / API_ORDER / ROUTES) ──────────────────────────

_BUY_ACCEPT_RE = re.compile(
    r"^매수 주문 접수: (?P<nt>.+) (?P<qty>\d+)주 @ (?P<price>\d+) "
    r"\(주문번호: (?P<order_no>\S+), 전략: (?P<strategy>\S+)\)$"
)
_SELL_ACCEPT_RE = re.compile(
    r"^(?P<signal>\S+) 매도 주문 접수: (?P<nt>.+) (?P<qty>\d+)주 "
    r"\(주문번호: (?P<order_no>\S+), 전략: (?P<strategy>\S+)\)$"
)
_MANUAL_SELL_RE = re.compile(
    r"^수동 매도 주문 접수: (?P<nt>.+) (?P<qty>\d+)주 "
    r"\(주문번호: (?P<order_no>\S+), 전략: (?P<strategy>\S+)\)(?:\s.*)?$"
)
_ORDER_DONE_RE = re.compile(
    r"^(?P<side>BUY|SELL) 주문 완료: (?P<ticker>\S+) (?P<qty>\d+)주 @ (?P<price>\d+) "
    r"\(주문번호: (?P<order_no>\S+)\)$"
)
_BUY_FALLBACK_RE = re.compile(
    r"^시장가 거부 → 지정가 5호가 폴백: (?P<nt>.+) @ (?P<price>\d+) \(원인 \[.+?\] .+\)$"
)
_SELL_FALLBACK_RE = re.compile(
    r"^매도 시장가 거부 → 지정가 5호가 폴백: (?P<nt>.+) @ (?P<price>\d+) "
    r"\(원인 \[.+?\] .+?, 주문번호: (?P<order_no>\S+), 전략: (?P<strategy>\S+)\)$"
)
_REORDER_RE = re.compile(r"^손절 잔여 재주문: (?P<nt>.+) (?P<qty>\d+)주$")


def _h_buy_accept(logger, msg):
    if logger != OE:
        return None
    m = _BUY_ACCEPT_RE.match(msg)
    if not m:
        return None
    ticker, name = _ticker_name(m["nt"])
    return "buy_accept", {"ticker": ticker, "name": name, "qty": int(m["qty"]), "price": int(m["price"]),
                           "order_no": m["order_no"], "strategy": m["strategy"]}


def _h_sell_accept(logger, msg):
    if logger != OE:
        return None
    m = _SELL_ACCEPT_RE.match(msg)
    if not m or m["signal"] not in _SIGNAL_NAMES:
        return None
    ticker, name = _ticker_name(m["nt"])
    return "sell_accept", {"ticker": ticker, "name": name, "qty": int(m["qty"]),
                            "order_no": m["order_no"], "strategy": m["strategy"], "signal": m["signal"]}


def _h_manual_sell_accept(logger, msg):
    if logger != ROUTES:
        return None
    m = _MANUAL_SELL_RE.match(msg)
    if not m:
        return None
    ticker, name = _ticker_name(m["nt"])
    return "manual_sell_accept", {"ticker": ticker, "name": name, "qty": int(m["qty"]),
                                   "order_no": m["order_no"], "strategy": m["strategy"]}


def _h_order_done(logger, msg):
    if logger != API_ORDER:
        return None
    m = _ORDER_DONE_RE.match(msg)
    if not m:
        return None
    return "order_done", {"side": m["side"], "ticker": m["ticker"], "qty": int(m["qty"]),
                           "price": int(m["price"]), "order_no": m["order_no"]}


def _h_order_notice(logger, msg):
    if logger != REALTIME or not msg.startswith("[order_notice] "):
        return None
    kv = _kv(msg[len("[order_notice] "):])
    orig = kv.get("orig_order_no") or None
    return "order_notice", {
        "order_no": kv.get("order_no"), "orig_order_no": orig, "side": kv.get("side"),
        "rctf": kv.get("rctf"), "division": kv.get("kind"), "ticker": kv.get("ticker"),
        "qty": _as_int(kv.get("qty")), "price": _as_int(kv.get("price")), "acpt": kv.get("acpt"),
    }


def _h_buy_fallback(logger, msg):
    if logger != OE:
        return None
    m = _BUY_FALLBACK_RE.match(msg)
    if not m:
        return None
    ticker, name = _ticker_name(m["nt"])
    return "buy_fallback", {"ticker": ticker, "name": name, "price": int(m["price"])}


def _h_sell_fallback(logger, msg):
    if logger != OE:
        return None
    m = _SELL_FALLBACK_RE.match(msg)
    if not m:
        return None
    ticker, name = _ticker_name(m["nt"])
    return "sell_fallback", {"ticker": ticker, "name": name, "price": int(m["price"]),
                              "order_no": m["order_no"], "strategy": m["strategy"]}


def _h_reorder(logger, msg):
    if logger != OE:
        return None
    m = _REORDER_RE.match(msg)
    if not m:
        return None
    ticker, name = _ticker_name(m["nt"])
    return "reorder", {"ticker": ticker, "name": name, "qty": int(m["qty"])}


def _h_status_exit_fire(logger, msg):
    if logger != STATUS_EXIT or not msg.startswith("[status_exit_fire] "):
        return None
    kv = _kv(msg[len("[status_exit_fire] "):])
    return "status_exit_fire", {"ticker": kv.get("ticker"), "strategy": kv.get("strategy"),
                                 "reason": kv.get("reason")}


# ── 익일청산 보류 (SCHEDULER) ────────────────────────────────────────────────

_NDC_KRX_ONLY_RE = re.compile(
    r"^stock_master nxt_tradable=False — 익일 청산 보류 \(09:00 KRX 시장가 청산 예약\): "
    r"(?P<nt>.+) \(전략: (?P<strategy>\S+)\)$"
)
_NDC_NXT_OPEN_RE = re.compile(
    r"^NXT 시가 미수신 — 익일 청산 보류 \(KRX 시가 확정 후 재시도\): "
    r"(?P<nt>.+) \(전략: (?P<strategy>\S+)\)$"
)
_NDC_GAP_RE = re.compile(
    r"^익일 청산 보류 \(갭 (?P<gap>-?\d+\.\d+)% < 임계 (?P<threshold>-?\d+\.\d+)%, "
    r"09:00 KRX 시장가 청산 예약\): (?P<nt>.+) \(전략: (?P<strategy>\S+)\)$"
)


def _h_ndc_defer(logger, msg):
    if logger != SCHEDULER:
        return None
    for rx, sub in ((_NDC_KRX_ONLY_RE, "krx_only"), (_NDC_NXT_OPEN_RE, "nxt_open_missing"),
                    (_NDC_GAP_RE, "gap_below")):
        m = rx.match(msg)
        if not m:
            continue
        ticker, name = _ticker_name(m["nt"])
        gap = float(m["gap"]) if sub == "gap_below" else None
        threshold = float(m["threshold"]) if sub == "gap_below" else None
        return "ndc_defer", {"ticker": ticker, "name": name, "strategy": m["strategy"],
                              "reason_sub": sub, "gap": gap, "threshold": threshold}
    return None


# ── 전략 로거(exit_reason · buy_signal) ──────────────────────────────────────

def _strategy_from_logger(logger):
    if not logger.startswith(STRAT_PREFIX):
        return None
    return logger[len(STRAT_PREFIX):]


_EXIT_PATTERNS = [
    ("kojiro_hard_stop", re.compile(
        r"^\[kojiro_hard_stop\] (?P<ticker>\S+) 매수가\((?P<buy_price>-?\d+)\) 대비 "
        r"(?P<pct>-?\d+\.\d+)% ≤ (?P<threshold>-?\d+\.\d+)%$"), "STOP_LOSS"),
    ("kojiro_atr_stop", re.compile(
        r"^\[kojiro_atr_stop\] (?P<ticker>\S+) 손절선\((?P<line>-?\d+)\) = "
        r"매수가\((?P<buy_price>-?\d+)\) .*$"), "STOP_LOSS"),
    ("kojiro_trailing", re.compile(
        r"^\[kojiro_trailing\] (?P<ticker>\S+) 고점\(-?\d+\) .*= (?P<line>-?\d+) / "
        r"현재가 (?P<current_price>\d+)$"), "TRAILING_STOP"),
    ("kojiro_stage3_exit", re.compile(
        r"^\[kojiro_stage3_exit\] (?P<ticker>\S+) 스테이지3 진입 .*$"), "TREND_EXIT"),
    ("bfb_turtle_stop", re.compile(
        r"^\[bfb_turtle_stop\] (?P<ticker>\S+) 손절선\((?P<line>-?\d+)\) = "
        r"매수가\((?P<buy_price>-?\d+)\) [−-] .*$"), "STOP_LOSS"),
    ("bfb_turtle_backstop", re.compile(
        r"^\[bfb_turtle_backstop\] (?P<ticker>\S+) 매수가\((?P<buy_price>-?\d+)\) 대비 "
        r"(?P<pct>-?\d+\.\d+)% ≤ (?P<threshold>-?\d+\.\d+)%$"), "STOP_LOSS"),
    ("bfb_pullback_stop", re.compile(
        r"^눌림목 손절: (?P<ticker>\S+) 매수가\((?P<buy_price>-?\d+)\) 대비 (?P<pct>-?\d+\.\d+)%$"),
     "STOP_LOSS"),
    ("bfb_measured_target", re.compile(
        r"^눌림목 측정된 이동 도달: (?P<ticker>\S+) 현재가\((?P<current_price>\d+)\) ≥ "
        r"타겟\((?P<target>\d+)\) .*$"), "TAKE_PROFIT"),
    ("bfb_time_exit", re.compile(r"^눌림목 시간 청산: (?P<ticker>\S+) buy_date=.*$"), "TIME_EXIT"),
    ("ltv_intraday_stop", re.compile(r"^롱테일VB 당일 손절: (?P<nt>.+) (?P<pct>-?\d+\.\d+)%$"),
     "STOP_LOSS"),
    ("ltv_limit_up_stop", re.compile(
        r"^롱테일VB 손절\(상한가 모드\): (?P<nt>.+) (?P<pct>-?\d+\.\d+)%$"), "STOP_LOSS"),
    ("vb_stop", re.compile(
        r"^변동성돌파 손절: (?P<nt>.+) 매수가\((?P<buy_price>-?\d+)\) 대비 (?P<pct>-?\d+\.\d+)% "
        r"\(현재가: (?P<current_price>\d+)\)$"), "STOP_LOSS"),
    ("momentum_stop", re.compile(
        r"^손절 신호: (?P<nt>.+) 매수가\((?P<buy_price>-?\d+)\) 대비 (?P<pct>-?\d+\.\d+)% "
        r"\(임계: (?P<threshold>-?\d+\.\d+)%, 현재가: (?P<current_price>\d+)\)$"), "STOP_LOSS"),
    ("donchian_time_exit", re.compile(
        r"^\[donchian_time_exit\] ticker=(?P<ticker>\S+) reason=.*$"), "TIME_EXIT"),
    ("donchian_time_exit_legacy", re.compile(
        r"^도치안 시간 기반 청산: (?P<ticker>\S+) 보유 \d+영업일 ≥ \d+, "
        r"현재가\((?P<current_price>\d+)\) < 돌파선\(-?\d+\)$"), "TIME_EXIT"),
    ("donchian_trailing_legacy", re.compile(
        r"^도치안 스윙 트레일링: (?P<ticker>\S+) 고점\(-?\d+\) - ATR×[\d.]+ = (?P<line>-?\d+) / "
        r"현재가 (?P<current_price>\d+)$"), "TRAILING_STOP"),
]

_MODE_PHRASES = {"ltv_intraday_stop": "intraday", "ltv_limit_up_stop": "limit_up"}
_NUMERIC_INT_KEYS = ("buy_price", "line", "current_price", "target")
_NUMERIC_FLOAT_KEYS = ("pct", "threshold")


def _h_exit_reason(logger, msg):
    strategy = _strategy_from_logger(logger)
    if strategy is None:
        return None
    for phrase, rx, code in _EXIT_PATTERNS:
        m = rx.match(msg)
        if not m:
            continue
        gd = m.groupdict()
        fields = {"strategy": strategy, "phrase": phrase, "reason_code": code}
        token = gd.pop("nt", None)
        if token is None:
            token = gd.pop("ticker")
        ticker, name = _ticker_name(token)
        fields["ticker"], fields["name"] = ticker, name
        for k in _NUMERIC_INT_KEYS:
            if gd.get(k) is not None:
                fields[k] = int(gd[k])
        for k in _NUMERIC_FLOAT_KEYS:
            if gd.get(k) is not None:
                fields[k] = float(gd[k])
        if phrase in _MODE_PHRASES:
            fields["mode"] = _MODE_PHRASES[phrase]
        return "exit_reason", fields
    return None


_BUY_SIGNAL_PATTERNS = [
    re.compile(r"^\[bfb_vol_gate_pass\] ticker=(?P<ticker>\S+) .*$"),
    re.compile(r"^\[vcp_vol_gate_pass\] ticker=(?P<ticker>\S+) .*$"),
    re.compile(r"^고지로 매수 신호: (?P<ticker>\S+) 현재가\((?P<price>\d+)\) — .*$"),
    re.compile(r"^도치안 스윙 매수 신호: (?P<ticker>\S+) 현재가\((?P<price>\d+)\) — .*$"),
    re.compile(r"^변동성돌파 매수 신호 \[\S+\]: (?P<nt>.+) 현재가\((?P<price>\d+)\) >= .*$"),
    re.compile(r"^롱테일 변동성 돌파 매수 신호 \[\S+\]: (?P<nt>.+) 현재가\((?P<price>\d+)\) >= .*$"),
    re.compile(r"^매수 신호: (?P<nt>.+) 전일종가\(-?\d+\) 대비 -?[\d.]+% \(현재가: (?P<price>\d+), .*\)$"),
]


def _h_buy_signal(logger, msg):
    strategy = _strategy_from_logger(logger)
    if strategy is None:
        return None
    for rx in _BUY_SIGNAL_PATTERNS:
        m = rx.match(msg)
        if not m:
            continue
        gd = m.groupdict()
        price = int(gd["price"]) if gd.get("price") else None
        token = gd.get("nt")
        if token is None:
            token = gd.get("ticker")
        ticker, name = _ticker_name(token)
        return "buy_signal", {"strategy": strategy, "ticker": ticker, "name": name, "price": price}
    return None


_HANDLERS = (
    _h_buy_accept, _h_sell_accept, _h_manual_sell_accept, _h_order_done, _h_order_notice,
    _h_buy_fallback, _h_sell_fallback, _h_reorder, _h_status_exit_fire, _h_ndc_defer,
    _h_exit_reason, _h_buy_signal,
)


def parse_line(line: str):
    line = line.rstrip("\n")
    m = _LINE_RE.match(line)
    if not m:
        return None
    date_s, time_s, level, logger, msg = m.groups()
    ts = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    common = {"ts": ts, "level": level, "logger": logger, "raw": msg}
    for handler in _HANDLERS:
        result = handler(logger, msg)
        if result is not None:
            kind, fields = result
            event = dict(common)
            event["kind"] = kind
            event.update(fields)
            return event
    return None
