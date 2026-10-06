"""실거래 층(K4) — ``trade_history`` 체결 행 → 왕복 거래.

동결본 §1.2 규칙:
- D-1 손익은 매수 체결가 · 매도 체결가로만. 보유 구간에 권리락·분할(DB ``flng_cls_code`` ≠ '00' 이거나
  원본 종가 전일 대비 |수익률| > 30%)이 낀 왕복은 ``ca_flag`` 로 표시하고 판정 표본에서 뺀다.
- D-2 날짜는 KST — ``datetime.fromisoformat(ts).astimezone(KST).date()``(``ts[:10]`` 금지).
- D-4 판정 창 = KST 매수일 ≥ 2026-04-29.
- D-7 ``COMPLETED``·``PARTIAL`` 만. ``PENDING``·``CANCELLED`` 는 빼고 개수를 센다. 같은 ``order_no`` 의
  여러 행은 한 주문으로 묶는다(수량 합 · 금액 가중 가격).
- D-8 현 설정 구간 = 전략별 시작일(``current_start``) 이후 매수분만 판정. 그 전은 「참고」.

왕복 = (전략, 종목)별로 시간순으로 걸으며, 보유 수량이 0 에서 처음 사는 순간 시작해 다시 0 이 되는 매도에서
끝난다(분할 매수·분할 매도는 한 왕복). 매도가 보유보다 많으면 ``orphan_sell`` 로 센다(추출 범위 밖 매수 등).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
JUDGE_STATUSES = ("COMPLETED", "PARTIAL")


def kst_date(ts: str) -> date:
    return datetime.fromisoformat(ts).astimezone(KST).date()


def _collapse_orders(rows: list) -> list:
    """같은 (전략, 종목, 매수/매도, order_no) 체결 행을 한 주문으로. order_no 가 비면 행 그대로."""
    out, by = [], {}
    for r in rows:
        on = (r.get("order_no") or "").strip()
        if not on:
            out.append(dict(r, n_rows=1))
            continue
        key = (r["strategy"], r["ticker"], r["trade_type"], on, kst_date(r["timestamp"]))
        if key in by:
            a = by[key]
            q = a["quantity"] + r["quantity"]
            a["price"] = (a["price"] * a["quantity"] + r["price"] * r["quantity"]) / q if q else a["price"]
            a["quantity"] = q
            a["n_rows"] += 1
            a["timestamp_last"] = r["timestamp"]
        else:
            a = dict(r, n_rows=1, timestamp_last=r["timestamp"])
            by[key] = a
            out.append(a)
    return out


def round_trips(rows: "list[dict]", *, cost_rt: float, ca_days: "dict | None" = None,
                live_start: str = "2026-04-29") -> dict:
    """rows: trade_history 행(dict). ``ca_days[ticker]`` = 권리락·분할 의심일 집합(KST date).

    반환 = {"trips": [...], "open": [...], "excluded": Counter, "orphan_sells": [...]}"""
    excluded = Counter()
    kept = []
    for r in rows:
        st = r["status"]
        if st in JUDGE_STATUSES:
            kept.append(r)
        else:
            excluded[(r["strategy"], r["trade_type"], st)] += 1
    kept.sort(key=lambda r: (r["timestamp"], r["trade_type"] != "BUY"))
    orders = _collapse_orders(kept)
    by = defaultdict(list)
    for o in orders:
        by[(o["strategy"], o["ticker"])].append(o)
    trips, opens, orphans = [], [], []
    for (strat, tk), evs in by.items():
        evs.sort(key=lambda r: r["timestamp"])
        cur = None
        for e in evs:
            q = int(e["quantity"])
            if q <= 0:
                excluded[(strat, e["trade_type"], "qty0")] += 1
                continue
            if e["trade_type"] == "BUY":
                if cur is None:
                    cur = {"strategy": strat, "ticker": tk, "name": e.get("ticker_name") or "",
                           "buy_ts": e["timestamp"], "buy_qty": 0, "buy_amt": 0.0, "sell_qty": 0,
                           "sell_amt": 0.0, "open_qty": 0, "n_buy": 0, "n_sell": 0, "buy_orders": []}
                cur["buy_qty"] += q
                cur["buy_amt"] += q * float(e["price"])
                cur["open_qty"] += q
                cur["n_buy"] += 1
                cur["buy_orders"].append((kst_date(e["timestamp"]).isoformat(), q, float(e["price"])))
            else:
                if cur is None or cur["open_qty"] <= 0:
                    orphans.append({"strategy": strat, "ticker": tk, "ts": e["timestamp"], "qty": q})
                    continue
                take = min(q, cur["open_qty"])
                if take < q:
                    orphans.append({"strategy": strat, "ticker": tk, "ts": e["timestamp"], "qty": q - take})
                cur["sell_qty"] += take
                cur["sell_amt"] += take * float(e["price"])
                cur["open_qty"] -= take
                cur["n_sell"] += 1
                cur["sell_ts"] = e["timestamp"]
                if cur["open_qty"] == 0:
                    trips.append(_finish(cur, cost_rt, ca_days, live_start))
                    cur = None
        if cur is not None:
            opens.append({k: cur[k] for k in ("strategy", "ticker", "buy_ts", "buy_qty", "open_qty",
                                              "sell_qty")})
    trips.sort(key=lambda t: (t["strategy"], t["buy_date"], t["ticker"]))
    return {"trips": trips, "open": opens, "excluded": excluded, "orphan_sells": orphans}


def _finish(cur: dict, cost_rt: float, ca_days, live_start: str) -> dict:
    bd = kst_date(cur["buy_ts"])
    sd = kst_date(cur["sell_ts"])
    bp = cur["buy_amt"] / cur["buy_qty"]
    sp = cur["sell_amt"] / cur["sell_qty"]
    gross = sp / bp - 1.0
    ca = False
    if ca_days and cur["ticker"] in ca_days:
        ca = any(bd < d <= sd for d in ca_days[cur["ticker"]])
    return {"strategy": cur["strategy"], "ticker": cur["ticker"], "name": cur["name"],
            "buy_date": bd.isoformat(), "sell_date": sd.isoformat(), "qty": cur["buy_qty"],
            "buy_px": bp, "sell_px": sp, "buy_amt": cur["buy_amt"], "gross": gross, "net": gross - cost_rt,
            "hold_days_cal": (sd - bd).days, "n_buy": cur["n_buy"], "n_sell": cur["n_sell"],
            "one_share": cur["buy_qty"] == 1, "ca_flag": ca, "in_window": bd.isoformat() >= live_start,
            "buy_orders": cur["buy_orders"]}


# KIS 락 구분: 01 권리락 · 02 배당락 · 03 분배락 · 04 권배락 · 05 중간(분기)배당락 · 06 권리중간배당락 · 07 권리분기배당락.
# D-1 은 「권리락·분할」 — 권리 계열(01·04·06·07)만 잡고 배당·분배락은 잡지 않는다.
RIGHTS_CODES = frozenset({"01", "04", "06", "07"})
JUMP = 0.30 + 1e-6          # 상한가 +30.0% 는 「30% 초과」 가 아니다(부동소수 1.3−1 = 0.30000000000000004)


def ca_days_from_db(daily_cols: list, daily_rows: list, codes=RIGHTS_CODES) -> dict:
    """DB 일봉 → 종목별 권리락·분할 의심일(KST date). 락 구분 ∈ ``codes`` 또는 원본 종가 |Δ| > 30%."""
    ix = {c: i for i, c in enumerate(daily_cols)}
    by = defaultdict(list)
    for r in daily_rows:
        by[r[ix["ticker"]]].append(r)
    out = defaultdict(set)
    for t, rs in by.items():
        rs.sort(key=lambda r: r[ix["bas_dd"]])
        prev = None
        for r in rs:
            d = date.fromisoformat(r[ix["bas_dd"]][:10])
            code = (r[ix["flng_cls_code"]] or "").strip()
            c = r[ix["close_price"]]
            if code in codes:
                out[t].add(d)
            if prev and c and prev > 0 and abs(c / prev - 1) > JUMP:
                out[t].add(d)
            prev = c if c else prev
    return dict(out)
