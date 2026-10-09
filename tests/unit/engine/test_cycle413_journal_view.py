"""cycle413 Red — 거래일지 카드 조립 순수 leaf `src/engine/journal_view.py::build_card`.

명세 = `_workspace/red/cycle413/journal_view_spec.md`(domain-expert) · 계약 = `_workspace/red/cycle413/journal_view_contract.md`.
이 파일과 명세가 갈리면 이 파일이 정본이다.

| # | 계약 (명세 9절 T1~T7) |
|---|---|
| T1 | 「모름 ≠ 0」 — 값이 None 이면 짝 `*_na` 가 있고, 값이 있으면 `*_na` 는 None. 비용 실패·시세 대기·일지 표 실패·종가 0개 |
| T2 | 체결오차 부호(매수 = 체결 − 기준 · 매도 = 기준 − 체결, 불리하면 +) · bp 소수 1자리 · 판단가 = 주문가면 `slip_judge=None` · 상한만이면 `bound='upper'` · C2(판단가에 주문가를 옮겨 적지 않는다) |
| T3 | 패리티 — 주문가 기준(`ref_src='trade'`) 합 = `pair.slippage_won` · 진입+청산 수수료 = `pair.fee` · 청산 세금 = `pair.tax` · 보유 중 낸 비용 + 예상 청산비용 = fee+tax+partial_fee+partial_tax |
| T4 | MFE/MAE — 15:30 에 들고 있던 영업일 종가만 · 애프터 매도일 포함 · 15:30 뒤 매수는 다음 날부터 · 분할 매도 날 수량 · 결측 k/n · 잠정·락 · 당일 청산 해당 없음 |
| T5 | 최초 손절 — 매수일 관측만 최초 · 다음 날 첫 관측 = 기록 전/모름 + `first_seen` · LTV 모드 의존 · 행 0 |
| T6 | 손절선 변화 — 값 그대로 eod 숨김·카운트 · 방향 · 원인 13줄 · 최대 2개 · 다른 보유 행 배제 |
| T7 | 이유 문장 — 3-1 전략 8개 · 키 빠진 절 생략 · log_only/none · AI평가 보강(09-17 전 BFB 제외) · 3-3 표 · renamed_from · 경로 꼬리 · 발동선 출처 |

입력은 DB 함수가 돌려주는 모양 그대로다(계약 1절): 시각 = KST ISO 문자열, 날짜 = `date`, 금액 = `Decimal`/int.
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 9, 10, 0, tzinfo=KST)

#: 기록 시작일(합성) — 손절선·주문가 기록이 10-01 부터 있는 세계.
RS = {"orders_restored": "2026-09-17", "orders_live": "2026-10-01", "stops": "2026-10-01",
      "order_price": "2026-10-01"}
#: 실제 운영과 같은 기록 시작일 — 손절선 10-12, 주문가 10-07.
RS_REAL = {"orders_restored": "2026-09-17", "orders_live": "2026-10-12", "stops": "2026-10-12",
           "order_price": "2026-10-07"}

NA_KINDS = {"unknown", "before_record", "not_applicable", "pending", "lookup_failed"}


@pytest.fixture(scope="module")
def jv():
    return importlib.import_module("src.engine.journal_view")


def _ts(s: str) -> str:
    """'YYYY-MM-DDTHH:MM:SS' → trade_history `_TS_SELECT` 꼴 KST ISO."""
    return f"{s}.000000+09:00"


def _k(s: str) -> str:
    """'YYYY-MM-DDTHH:MM:SS' → `to_char(...,'+09:00')` 꼴 KST ISO."""
    return f"{s}+09:00"


def _fill(tid, side, at, price, qty, *, order_no, order_price=None, pl="auto"):
    if pl == "auto":
        pl = Decimal(0) if side == "BUY" else None
    return {
        "id": tid, "order_no": order_no, "trade_type": side, "timestamp": _ts(at),
        "price": Decimal(str(price)), "quantity": qty,
        "order_price": None if order_price is None else Decimal(str(order_price)),
        "profit_loss": None if pl is None else Decimal(str(pl)),
    }


def _order(day, order_no, side, strategy, ticker, *, source="log_harvest", reason_code=None,
           reason_sub=None, judge_price=None, order_price=None, division=None, parent=None,
           fired=None, eff=None, signal=None, params=None, noted_at=None):
    return {
        "order_date": day, "order_no": order_no, "side": side, "strategy": strategy, "ticker": ticker,
        "source": source, "reason_code": reason_code if reason_code is not None or side == "SELL" else "ENTRY",
        "reason_sub": reason_sub, "judge_price": judge_price, "order_price": order_price,
        "order_division": division, "exchange": None, "parent_order_no": parent,
        "fired_line": fired, "effective_line": eff, "signal": signal, "params": params,
        "noted_at": noted_at or _k(f"{day.isoformat()}T09:00:00"),
    }


def _stop(strategy, ticker, at, event, price, *, kind="effective", target=None, hit=None, arm=None,
          inputs=None, pos="B1", buy_date=None):
    return {
        "strategy": strategy, "ticker": ticker, "buy_date": buy_date, "pos_order_no": pos,
        "observed_at": _k(at), "event": event, "stop_price": price, "stop_kind": kind,
        "target_price": target, "target_hit": hit, "arm_price": arm, "inputs": inputs,
    }


def _close(ticker, d, px, *, upd=None, flng="00", prtt=0):
    return {
        "ticker": ticker, "bas_dd": d, "close_price": px,
        "updated_at": upd or _k(f"{(d + timedelta(days=1)).isoformat()}T07:50:00"),
        "flng_cls_code": flng, "prtt_rate": Decimal(str(prtt)),
    }


def _est_costs(fills, rate=0.00142, tax_rate=0.00199):
    out = {}
    for f in fills:
        amt = float(f["price"]) * f["quantity"]
        tax = amt * tax_rate if f["trade_type"] == "SELL" else 0.0
        out[f["id"]] = {"fee": amt * rate, "tax": tax, "cost_status": "estimated", "allocated": False}
    return out


def _pair_from(fills, strategy, ticker, name="종목", *, costs=None, open_pl=None):
    """`get_trade_pairs` 한 사이클 + `overlay_pairs` 칸(닫힌 페어만 비용 합)을 흉내 낸다."""
    fs = sorted(fills, key=lambda f: f["timestamp"])
    buys = [f for f in fs if f["trade_type"] == "BUY"]
    sells = [f for f in fs if f["trade_type"] == "SELL"]
    bq = sum(f["quantity"] for f in buys)
    sq = sum(f["quantity"] for f in sells)
    bamt = sum(float(f["price"]) * f["quantity"] for f in buys)
    avg = bamt / bq
    closed = sq >= bq
    buy_onos = [f["order_no"] for f in buys if f["order_no"]]
    p = {
        "buy_date": buys[0]["timestamp"][:10], "buy_time": buys[0]["timestamp"][11:19],
        "ticker": ticker, "ticker_name": name, "buy_price": int(avg), "strategy": strategy,
        "buy_order_nos": list(dict.fromkeys(buy_onos)),
        "pair_key": f"{strategy}:{ticker}:{buy_onos[0]}" if buy_onos else None,
        "buy_trade_ids": [f["id"] for f in buys],
    }
    if closed:
        pl = sum((f["profit_loss"] or Decimal(0)) for f in sells)
        samt = sum(float(f["price"]) * f["quantity"] for f in sells)
        p.update({
            "sell_date": sells[-1]["timestamp"][:10], "sell_time": sells[-1]["timestamp"][11:19],
            "buy_qty": bq, "sell_price": int(samt / sq), "sell_qty": sq, "profit_loss": int(pl),
            "profit_rate": round(float(pl) / (avg * sq) * 100, 4), "status": "closed",
            "sell_order_nos": list(dict.fromkeys(f["order_no"] for f in sells if f["order_no"])),
            "sell_trade_ids": [f["id"] for f in sells], "partial_sell_trade_ids": [],
        })
        if costs is not None:
            fee = sum(costs[f["id"]]["fee"] for f in fs)
            tax = sum(costs[f["id"]]["tax"] for f in fs)
            net = float(pl) - fee - tax
            statuses = {costs[f["id"]]["cost_status"] for f in fs}
            slip, covered = 0.0, False
            for f in buys:
                if f["order_price"] is not None:
                    covered = True
                    slip += (float(f["price"]) - float(f["order_price"])) * f["quantity"]
            for f in sells:
                if f["order_price"] is not None:
                    covered = True
                    slip += (float(f["order_price"]) - float(f["price"])) * f["quantity"]
            p.update({
                "fee": fee, "tax": tax, "net_profit_loss": net,
                "net_profit_rate": round(net / (int(avg) * bq) * 100, 4),
                "cost_status": statuses.pop() if len(statuses) == 1 else "mixed",
                "allocated": False, "slippage_won": slip if covered else None,
            })
    else:
        p.update({
            "sell_date": None, "sell_time": None, "buy_qty": bq - sq, "sell_price": None,
            "sell_qty": None, "profit_loss": open_pl,
            "profit_rate": None if open_pl is None else round(open_pl / (avg * (bq - sq)) * 100, 4),
            "status": "open", "sell_order_nos": [], "sell_trade_ids": [],
            "partial_sell_trade_ids": [f["id"] for f in sells],
        })
    return p


def _kw(pair, fills, **over):
    kw = {
        "fills": fills, "orders": [], "stops": [], "note": None, "closes": [], "business_days": [],
        "llm_evals": [], "costs": _est_costs(fills), "record_start": RS, "now": NOW,
    }
    kw.update(over)
    return kw


def _uuid(prefix: str, n: int) -> str:
    return f"{prefix * 8}-0000-4000-8000-{n:012d}"


# ════════════════════════════════════════════════════════════════════════════
# 시나리오 A — 추세 눌림목 돌파(BFB) 닫힌 페어 · 실시간 진입(ring) · 익절 (명세 8-2 와이어)
# ════════════════════════════════════════════════════════════════════════════
A_BUY, A_SELL = _uuid("a", 1), _uuid("a", 2)
A_FILLS = [
    _fill(A_BUY, "BUY", "2026-10-05T09:12:03", 12350, 40, order_no="B1", order_price=12340),
    _fill(A_SELL, "SELL", "2026-10-08T14:31:20", 13450, 40, order_no="S1", order_price=13450, pl=44000),
]
A_COSTS = {
    A_BUY: {"fee": 701.0, "tax": 0.0, "cost_status": "settled", "allocated": False},
    A_SELL: {"fee": 764.0, "tax": 1071.0, "cost_status": "settled", "allocated": False},
}
_BFB, _TK = "bull_flag_breakout", "247540"
A_ORDERS = [
    _order(date(2026, 10, 5), "B1", "BUY", _BFB, _TK, judge_price=12340, order_price=12340, division="01",
           signal={"flag_high": 12300, "target_price": 13450, "atr": 410, "price": 12340,
                   "time": "09:12:01", "signal_src": "ring", "path": "accept"},
           params={"atr_period": 20}, noted_at=_k("2026-10-05T09:12:03")),
    _order(date(2026, 10, 8), "S1", "SELL", _BFB, _TK, reason_code="TAKE_PROFIT", judge_price=13460,
           division="01", eff=12350,
           signal={"signal_name": "TAKE_PROFIT",
                   "reason_line": "눌림목 측정된 이동 도달: 에코프로비엠(247540) 현재가(13460) ≥ 타겟(13450)",
                   "phrase": "bfb_measured_target", "judge_src": "log_price", "current_price": 13460,
                   "target": 13450, "snapshot_age_s": 8, "stop_kind": "effective", "path": "accept"},
           noted_at=_k("2026-10-08T14:31:20")),
]
_IN0 = {"buy_price": 12350, "quantity": 40, "high_since_buy": 12350, "entry_atr": 410, "kk_armed": None,
        "stop_source": "effective", "target_source": "measured_move"}
_IN1 = {**_IN0, "high_since_buy": 12900}


def _a_stop(at, event, price, **kw):
    kw.setdefault("target", 13450)
    kw.setdefault("hit", False)
    kw.setdefault("buy_date", date(2026, 10, 5))
    return _stop(_BFB, _TK, at, event, price, **kw)


A_STOPS = [
    _a_stop("2026-10-02T10:00:00", "first", 9000, inputs=_IN0, pos="B0"),        # 이전 보유 — 창 밖
    _a_stop("2026-10-05T09:12:20", "first", 11530, inputs=_IN0),
    _a_stop("2026-10-05T15:31:00", "eod", 11530, inputs=_IN0),                   # 값 그대로 → 숨김
    _a_stop("2026-10-06T11:00:00", "change", 5000, inputs=_IN0, pos="B9"),       # 다른 보유 → 배제
    _a_stop("2026-10-06T15:31:00", "eod", 11980, inputs=_IN1),                   # ↑ 고점 갱신
    _a_stop("2026-10-07T09:00:30", "boot", 11900, inputs=_IN1),                  # ↓ 재시작 재계산
    _a_stop("2026-10-07T10:41:00", "change", 12350, inputs=_IN1),                # ↑ 본전 승격
    _a_stop("2026-10-07T15:31:00", "eod", 12350, inputs=_IN1),                   # 값 그대로 → 숨김
    _a_stop("2026-10-08T14:31:20", "exit", 12350, hit=True,
            inputs={"snapshot_age_s": 8, "sell_order_no": "S1"}),
    _a_stop("2026-10-08T14:40:00", "first", 8000, inputs=_IN0, pos=None),        # 청산 +120초 뒤 — 창 밖
]
A_DAYS = [date(2026, 10, d) for d in (1, 2, 5, 6, 7, 8)]
A_CLOSES = [
    _close(_TK, date(2026, 10, 2), 11000),
    _close(_TK, date(2026, 10, 5), 12450),
    _close(_TK, date(2026, 10, 6), 12900),
    _close(_TK, date(2026, 10, 7), 13120),
    _close(_TK, date(2026, 10, 8), 13500),   # 14:31 에 다 팔았다 — 15:30 보유 아님(포함하면 MFE 가 바뀐다)
]
A_NOTE = {"anchor_trade_id": A_BUY, "body": "목표 도달 — 계획대로", "created_at": _k("2026-10-08T15:00:00"),
          "updated_at": _k("2026-10-08T15:05:00")}


def _a_pair(**over):
    p = _pair_from(A_FILLS, _BFB, _TK, "에코프로비엠", costs=A_COSTS)
    p.update(over)
    return p


def _a_kw(**over):
    kw = _kw(_a_pair(), A_FILLS, orders=A_ORDERS, stops=A_STOPS, note=A_NOTE, closes=A_CLOSES,
             business_days=A_DAYS, costs=A_COSTS)
    kw.update(over)
    return kw


@pytest.fixture(scope="module")
def card_a(jv):
    kw = _a_kw()
    return jv.build_card(_a_pair(), **{k: v for k, v in kw.items()})


def test_a_head_identity_and_pnl(card_a):
    c = card_a
    assert c["pair_key"] == "bull_flag_breakout:247540:B1"
    assert c["anchor_trade_id"] == A_BUY
    assert (c["strategy"], c["ticker"], c["ticker_name"], c["status"]) == (_BFB, _TK, "에코프로비엠", "closed")
    assert c["opened_at"].startswith("2026-10-05T09:12:03") and c["opened_at"].endswith("+09:00")
    assert c["closed_at"].startswith("2026-10-08T14:31:20") and c["closed_at"].endswith("+09:00")
    assert c["held_days"] == 3
    assert c["record_notice"] is None
    pnl = c["pnl"]
    assert pnl["gross_krw"] == 44000
    assert pnl["net_krw"] == pytest.approx(41464, abs=0.5)
    assert pnl["net_rate_pct"] == pytest.approx(8.3935, abs=1e-3)
    assert pnl["unrealized"] is False
    assert pnl["gross_na"] is None and pnl["net_na"] is None
    assert c["note"] == {"body": "목표 도달 — 계획대로", "updated_at": _k("2026-10-08T15:05:00")}


def test_a_entry_line_and_slip_by_order_price(card_a):
    e = card_a["entry"]
    assert e["avg_price"] == 12350 and e["qty"] == 40
    assert len(e["orders"]) == 1
    ln = e["orders"][0]
    assert ln["side"] == "BUY" and ln["order_no"] == "B1" and ln["trade_ids"] == [A_BUY]
    assert ln["at"].startswith("2026-10-05T09:12:03") and ln["at"].endswith("+09:00")
    assert ln["price"] == 12350 and ln["qty"] == 40
    assert (ln["division"], ln["division_na"]) == ("01", None)
    assert (ln["source"], ln["source_na"], ln["path"]) == ("log_harvest", None, "accept")
    assert ln["judge"] == {"price": 12340, "upper": None, "src": "signal", "na": None}
    s = ln["slip_order"]
    assert s["ref_price"] == 12340 and s["ref_src"] == "trade"
    assert s["per_share_won"] == 10 and s["bp"] == 8.1 and s["total_won"] == 400 and s["bound"] == "exact"
    assert ln["slip_order_na"] is None
    # 판단가 = 주문가(시장가 매수) — 판단가 기준을 따로 보내지 않는다.
    assert ln["slip_judge"] is None


def test_a_entry_reason_initial_stop_target(card_a):
    e = card_a["entry"]
    r = e["reason"]
    assert r["code"] == "ENTRY"
    assert r["text"] == "깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410"
    assert (r["src"], r["signal_src"], r["na"]) == ("live", "ring", None)
    st = e["initial_stop"]
    assert st["price"] == 11530 and st["kind"] == "effective"
    assert st["pct_from_entry"] == pytest.approx(-6.64, abs=1e-9)
    assert st["observed_at"].startswith("2026-10-05T09:12:20")
    assert st["delay_s"] == 17 and st["na"] is None and st["first_seen"] is None
    t = e["target"]
    assert t["kind"] == "measured_move" and t["price"] == 13450 and t["hit"] is True
    assert t["signal_price"] == 13450 and t["na"] is None
    assert t["text"].startswith("측정 목표 13,450 (+8.91%)")
    assert "도달" in t["text"] and "미도달" not in t["text"]


def test_a_exit_line_reason_lines_and_judge_slip(card_a):
    assert len(card_a["exits"]) == 1
    x = card_a["exits"][0]
    assert x["side"] == "SELL" and x["order_no"] == "S1" and x["trade_ids"] == [A_SELL]
    assert x["price"] == 13450 and x["qty"] == 40
    assert x["realized_gross_krw"] == 44000
    r = x["reason"]
    assert (r["code"], r["sub"], r["phrase"], r["renamed_from"]) == ("TAKE_PROFIT", None, "bfb_measured_target", None)
    assert r["text"] == "측정 목표 13,450 도달 — 전량 익절 (현재가 13,460)"
    assert r["src"] == "live" and r["na"] is None
    assert x["line_role"] == "target"
    assert x["effective_line"] == 12350 and x["snapshot_age_s"] == 8 and x["line_na"] is None
    assert x["judge"] == {"price": 13460, "upper": None, "src": "log_price", "na": None}
    so = x["slip_order"]
    assert (so["ref_price"], so["ref_src"], so["per_share_won"], so["bp"], so["total_won"]) == (13450, "trade", 0, 0.0, 0)
    sj = x["slip_judge"]
    assert sj["ref_price"] == 13460 and sj["ref_src"] == "live"
    assert sj["per_share_won"] == 10 and sj["bp"] == 7.4 and sj["total_won"] == 400 and sj["bound"] == "exact"


def test_a_stop_track_rows_hidden_eod_directions_causes(card_a):
    """T6 — 값 그대로 eod 2건 숨김 · 이전 보유(창 밖)·다른 보유(pos_order_no)·청산 +120초 뒤 행 배제."""
    tr = card_a["stop_track"]
    assert tr["na"] is None
    assert (tr["first"], tr["last"], tr["ups"], tr["downs"], tr["paused"], tr["hidden_eod"]) == (
        11530, 12350, 2, 1, False, 2)
    rows = tr["rows"]
    assert [r["event"] for r in rows] == ["first", "eod", "boot", "change", "exit"]
    assert [r["price"] for r in rows] == [11530, 11980, 11900, 12350, 12350]
    assert [r["direction"] for r in rows] == [None, "up", "down", "up", "flat"]
    assert [r["delta_won"] for r in rows] == [None, 450, -80, 450, 0]
    assert [r["cause"] for r in rows[:4]] == ["첫 관측", "고점 갱신", "재시작 재계산", "본전 승격"]
    assert rows[4]["cause"].startswith("청산 직전 스냅샷 (8초 전)")
    # 청산 스냅샷의 inputs 에는 수량 칸이 없다 — 없는 값은 「바뀜」이 아니다.
    assert "수량" not in rows[4]["cause"]
    assert rows[4]["snapshot_age_s"] == 8
    assert all(r["snapshot_age_s"] is None for r in rows[:4])
    assert all(r["at"].endswith("+09:00") for r in rows)
    # 청산 직전 행 값 = 청산 줄의 유효선
    assert rows[-1]["price"] == card_a["exits"][0]["effective_line"]


def test_a_costs_split_entry_exit(card_a):
    co = card_a["costs"]
    assert co["na"] is None
    assert co["entry_fee"] == pytest.approx(701) and co["entry_status"] == "settled"
    assert co["entry_allocated"] is False
    assert len(co["exits"]) == 1
    ex = co["exits"][0]
    assert ex["order_no"] == "S1" and ex["at"].startswith("2026-10-08T14:31:20")
    assert ex["fee"] == pytest.approx(764) and ex["tax"] == pytest.approx(1071)
    assert ex["status"] == "settled" and ex["allocated"] is False
    assert co["fee_total"] == pytest.approx(1465) and co["tax_total"] == pytest.approx(1071)
    assert co["paid_total"] == pytest.approx(2536)
    assert co["expected_exit"] is None and co["expected_exit_na"] == "not_applicable"
    assert co["status"] == "settled" and co["allocated"] is False


def test_a_excursion_closes_held_at_1530_only(card_a):
    ex = card_a["excursion"]
    assert ex["basis_price"] == 12350 and ex["na"] is None
    assert (ex["closes_k"], ex["closes_n"]) == (3, 3)
    assert ex["mfe"] == {"pct": 6.23, "krw": 30800, "date": "2026-10-07", "close": 13120, "qty": 40,
                         "provisional": False}
    # 손실 구간 없음(최저 +0.81%) — 값은 그대로 보낸다(문구는 화면이 고른다).
    assert ex["mae"] == {"pct": 0.81, "krw": 4000, "date": "2026-10-05", "close": 12450, "qty": 40,
                         "provisional": False}
    assert ex["provisional_dates"] == [] and ex["lock_dates"] == []


def test_t3_closed_parity_with_overlay(card_a):
    """T3 — (a) 주문가 기준 체결오차 합 = `pair.slippage_won` (b) 진입+청산 수수료 = fee, 청산 세금 = tax."""
    pair = _a_pair()
    lines = card_a["entry"]["orders"] + card_a["exits"]
    trade_slip = sum(ln["slip_order"]["total_won"] for ln in lines
                     if ln["slip_order"] and ln["slip_order"]["ref_src"] == "trade")
    assert trade_slip == pytest.approx(pair["slippage_won"], abs=1)
    co = card_a["costs"]
    assert co["entry_fee"] + sum(x["fee"] for x in co["exits"]) == pytest.approx(pair["fee"], abs=0.01)
    assert sum(x["tax"] for x in co["exits"]) == pytest.approx(pair["tax"], abs=0.01)
    assert card_a["pnl"]["net_krw"] == pytest.approx(pair["net_profit_loss"], abs=0.01)


# ════════════════════════════════════════════════════════════════════════════
# 시나리오 C — 고지로 보유 중 · 분할 진입 2건 · 애프터 분할 매도 · 추정 비용 · 손절 정지
# ════════════════════════════════════════════════════════════════════════════
C_B1, C_B2, C_S1 = _uuid("c", 1), _uuid("c", 2), _uuid("c", 3)
_KJ, _CT = "kojiro", "005930"
C_FILLS = [
    _fill(C_B1, "BUY", "2026-10-05T10:00:00", 50000, 10, order_no="B1", order_price=49950),
    _fill(C_B2, "BUY", "2026-10-06T10:00:00", 52000, 10, order_no="B2", order_price=52100),
    _fill(C_S1, "SELL", "2026-10-07T16:02:10", 55000, 5, order_no="S1", order_price=55000, pl=20000),
]
C_COSTS = {
    C_B1: {"fee": 710.0, "tax": 0.0, "cost_status": "estimated", "allocated": False},
    C_B2: {"fee": 738.4, "tax": 0.0, "cost_status": "estimated", "allocated": False},
    C_S1: {"fee": 390.5, "tax": 547.25, "cost_status": "estimated", "allocated": False},
}


def _c_pair(**over):
    p = _pair_from(C_FILLS, _KJ, _CT, "삼성전자", open_pl=45000)
    # overlay_pairs 보유 중 공식(현재가 54,000 역산 · 요율 0.142%/0.199%) 결과를 그대로 싣는다.
    p.update({"buy_price": 51000, "profit_rate": 5.8824, "fee": 2236.5, "tax": 1611.9,
              "net_profit_loss": 41151.6, "net_profit_rate": 5.3793, "cost_status": "estimated",
              "allocated": False, "slippage_won": -500.0, "partial_fee": 752.6, "partial_tax": 547.25})
    p.update(over)
    return p


_INC0 = {"buy_price": 50000, "quantity": 10, "high_since_buy": 50000, "entry_atr": 1500, "kk_armed": None,
         "stop_source": "effective", "target_source": None}
_INC1 = {**_INC0, "buy_price": 51000, "quantity": 20}
_INC2 = {**_INC1, "quantity": 15}
C_STOPS = [
    _stop(_KJ, _CT, "2026-10-05T10:00:15", "first", 47000, inputs=_INC0),
    _stop(_KJ, _CT, "2026-10-06T10:00:20", "change", 48000, inputs=_INC1),
    _stop(_KJ, _CT, "2026-10-07T11:00:00", "paused", 48000, inputs=_INC1),
    _stop(_KJ, _CT, "2026-10-07T16:02:30", "change", 47500, inputs=_INC2),
]
C_ORDERS = [
    _order(date(2026, 10, 5), "B1", "BUY", _KJ, _CT, judge_price=49950, order_price=49950, division="01",
           signal={"stage": 2, "atr": 1500, "price": 49950, "signal_src": "ring", "path": "accept"},
           params={"atr_period": 20}),
    _order(date(2026, 10, 7), "S1", "SELL", _KJ, _CT, source="manual_api", reason_code="MANUAL",
           order_price=55000, division="41", eff=48000,
           signal={"signal_name": "MANUAL", "reason_line": None, "phrase": None, "judge_src": None,
                   "snapshot_age_s": 12, "stop_kind": "effective", "path": "manual"}),
]
C_DAYS = [date(2026, 10, d) for d in (5, 6, 7, 8)]
C_CLOSES = [
    _close(_CT, date(2026, 10, 5), 49000, upd=_k("2026-10-05T20:31:00")),   # 잠정(다음 아침 확정 전)
    _close(_CT, date(2026, 10, 6), 53000, prtt=0.5),                         # 락
    _close(_CT, date(2026, 10, 7), 56100),
    # 10-08 결측
]
NOW_C = datetime(2026, 10, 9, 11, 0, tzinfo=KST)


def _c_kw(**over):
    kw = _kw(_c_pair(), C_FILLS, orders=C_ORDERS, stops=C_STOPS, closes=C_CLOSES, business_days=C_DAYS,
             costs=C_COSTS, now=NOW_C)
    kw.update(over)
    return kw


@pytest.fixture(scope="module")
def card_c(jv):
    return jv.build_card(_c_pair(), **_c_kw())


def test_c_open_head_partial_realized(card_c):
    c = card_c
    assert c["status"] == "open" and c["closed_at"] is None
    assert c["held_days"] == 4
    p = c["pnl"]
    assert p["unrealized"] is True
    assert p["gross_krw"] == 45000 and p["net_krw"] == pytest.approx(41151.6, abs=0.01)
    assert p["partial_gross_krw"] == 20000
    assert p["partial_net_krw"] == pytest.approx(20000 - 752.6 - 547.25, abs=0.01)


def test_c_entry_two_orders_qty_is_all_buys(card_c):
    e = card_c["entry"]
    assert e["avg_price"] == 51000
    assert e["qty"] == 20, "보유 중 pair.buy_qty(잔량 15)가 아니라 매수 체결 합"
    assert [ln["order_no"] for ln in e["orders"]] == ["B1", "B2"]
    b1, b2 = e["orders"]
    assert b1["slip_order"]["per_share_won"] == 50 and b1["slip_order"]["bp"] == 10.0
    assert b1["slip_order"]["total_won"] == 500 and b1["slip_judge"] is None
    # 유리한 체결은 음수(매수 체결 < 주문가)
    assert b2["slip_order"]["per_share_won"] == -100 and b2["slip_order"]["bp"] == -19.2
    assert b2["slip_order"]["total_won"] == -1000
    # B2 는 일지 행이 없다(기록 기간 안) → 모름
    assert (b2["source"], b2["source_na"]) == (None, "unknown")
    assert (b2["division"], b2["division_na"]) == (None, "unknown")
    assert b2["judge"]["price"] is None and b2["judge"]["na"] == "unknown"
    assert e["reason"]["text"] == "스테이지2 신규 진입 · 이평 정배열 · ATR 1,500"
    assert e["target"]["kind"] == "none" and e["target"]["price"] is None
    assert e["target"]["na"] == "not_applicable"
    assert e["target"]["text"] == "없음 — 샹들리에 트레일·스테이지3 청산"


def test_c_partial_exit_is_manual_reference_line(card_c):
    assert len(card_c["exits"]) == 1
    x = card_c["exits"][0]
    assert x["order_no"] == "S1" and x["qty"] == 5 and x["realized_gross_krw"] == 20000
    assert (x["source"], x["path"], x["division"]) == ("manual_api", "manual", "41")
    assert x["reason"]["code"] == "MANUAL" and x["reason"]["text"] == "수동 매도(화면)"
    assert x["line_role"] == "reference"
    assert x["effective_line"] == 48000 and x["snapshot_age_s"] == 12 and x["line_na"] is None
    assert x["judge"]["price"] is None and x["judge"]["na"] is not None


def test_c_costs_open_paid_plus_expected_equals_overlay(card_c):
    """T3(보유 중) — 낸 비용(진입 전부 + 분할 매도) + 예상 청산비용 = fee + tax + partial_fee + partial_tax."""
    co = card_c["costs"]
    pair = _c_pair()
    assert co["entry_fee"] == pytest.approx(710 + 738.4, abs=0.01)
    assert co["entry_status"] == "estimated"
    assert len(co["exits"]) == 1 and co["exits"][0]["order_no"] == "S1"
    assert co["exits"][0]["fee"] == pytest.approx(390.5) and co["exits"][0]["tax"] == pytest.approx(547.25)
    assert co["paid_total"] == pytest.approx(1448.4 + 390.5 + 547.25, abs=0.01)
    assert co["expected_exit_na"] is None
    total = pair["fee"] + pair["tax"] + pair["partial_fee"] + pair["partial_tax"]
    assert co["paid_total"] + co["expected_exit"] == pytest.approx(total, abs=0.01)
    assert co["status"] == "estimated"


def test_c_stop_track_paused_quantity_and_buy_price_causes(card_c):
    tr = card_c["stop_track"]
    assert tr["paused"] is True
    assert (tr["first"], tr["last"], tr["ups"], tr["downs"]) == (47000, 47500, 1, 1)
    rows = tr["rows"]
    assert [r["event"] for r in rows] == ["first", "change", "paused", "change"]
    assert rows[1]["cause"] == "수량 변화(추가 체결·분할 매도) · 매수가 변화(추가 체결)"
    assert rows[2]["cause"] == "전략 꺼짐 — 손절 평가 정지"
    assert rows[3]["direction"] == "down" and rows[3]["delta_won"] == -500
    assert rows[3]["cause"] == "수량 변화(추가 체결·분할 매도)"
    st = card_c["entry"]["initial_stop"]
    assert st["price"] == 47000 and st["pct_from_entry"] == pytest.approx(-7.84, abs=1e-9)
    assert st["delay_s"] == 15


def test_c_excursion_partial_sell_after_hours_missing_provisional_lock(card_c):
    """T4 — 16:02 애프터 분할 매도일(10-07)은 포함·그날 수량 20 · 10-08 종가 결측 → 3/4 · 잠정·락 배지."""
    ex = card_c["excursion"]
    assert (ex["closes_k"], ex["closes_n"]) == (3, 4)
    assert ex["mfe"] == {"pct": 10.0, "krw": 102000, "date": "2026-10-07", "close": 56100, "qty": 20,
                         "provisional": False}
    assert ex["mae"] == {"pct": -3.92, "krw": -20000, "date": "2026-10-05", "close": 49000, "qty": 10,
                         "provisional": True}
    assert ex["provisional_dates"] == ["2026-10-05"]
    assert ex["lock_dates"] == ["2026-10-06"]
    assert ex["na"] is None


# ════════════════════════════════════════════════════════════════════════════
# 시나리오 D — 롱테일 복원분(09-22) · 신호가만 + AI평가 보강 · 당일 손절 · 발동선 없음(C4)
# ════════════════════════════════════════════════════════════════════════════
D_B, D_S = _uuid("d", 1), _uuid("d", 2)
_LTV, _DT = "long_tail_volatility", "123456"
D_FILLS = [
    _fill(D_B, "BUY", "2026-09-22T09:05:10", 10000, 50, order_no="B7"),
    _fill(D_S, "SELL", "2026-09-22T10:31:00", 9690, 50, order_no="S7", pl=-15500),
]
D_COSTS = {D_B: {"fee": 70.0, "tax": 0.0, "cost_status": "settled", "allocated": False},
           D_S: {"fee": 70.0, "tax": 965.0, "cost_status": "settled", "allocated": False}}
D_ORDERS = [
    _order(date(2026, 9, 22), "B7", "BUY", _LTV, _DT, source="log_restore", judge_price=9990, order_price=9990,
           signal={"signal_src": "log_only", "path": "accept"}),
    _order(date(2026, 9, 22), "S7", "SELL", _LTV, _DT, source="log_restore", reason_code="STOP_LOSS",
           judge_price=9700,
           signal={"signal_name": "STOP_LOSS", "reason_line": "롱테일VB 당일 손절: 롱테일(123456) -3.0%",
                   "phrase": "ltv_intraday_stop", "judge_src": "log_pct", "pct": -3.0, "mode": "intraday",
                   "path": "accept"}),
]
D_LLM = [{"trade_date": date(2026, 9, 22), "ticker": _DT, "order_no": "B7", "strategy_id": _LTV,
          "target_won": 9980, "k": Decimal("0.5000"), "strategy_board": "main", "signal_price_won": 9990}]


@pytest.fixture(scope="module")
def card_d(jv):
    pair = _pair_from(D_FILLS, _LTV, _DT, "롱테일", costs=D_COSTS)
    return jv.build_card(pair, **_kw(pair, D_FILLS, orders=D_ORDERS, llm_evals=D_LLM, costs=D_COSTS,
                                     closes=[_close(_DT, date(2026, 9, 22), 9800)],
                                     business_days=[date(2026, 9, 22)], record_start=RS_REAL))


def test_d_restored_entry_ai_augmented(card_d):
    assert card_d["record_notice"] == "before_stops"
    assert card_d["held_days"] == 0
    r = card_d["entry"]["reason"]
    assert "돌파선 9,980 돌파" in r["text"] and "K 0.5" in r["text"]
    assert (r["src"], r["signal_src"], r["na"]) == ("restored_ai", "log_only", None)
    ln = card_d["entry"]["orders"][0]
    assert ln["source"] == "log_restore"
    assert (ln["division"], ln["division_na"]) == (None, "before_record")   # 09-28 전 접수 기록 없음
    assert ln["judge"] == {"price": 9990, "upper": None, "src": "signal", "na": None}
    s = ln["slip_order"]
    # trade_history.order_price 는 10-07 전이라 없다 → 일지 접수가(복원)로 잰다
    assert (s["ref_price"], s["ref_src"], s["per_share_won"], s["bp"], s["total_won"]) == (
        9990, "restored", 10, 10.0, 500)
    assert ln["slip_judge"] is None


def test_d_restored_ltv_stop_without_fired_line(card_d):
    """C4 — 복원 LTV 손절은 발동선이 없다(당시 파라미터 없음) → 지금 파라미터로 채우지 않고 모름."""
    x = card_d["exits"][0]
    r = x["reason"]
    assert r["code"] == "STOP_LOSS" and r["phrase"] == "ltv_intraday_stop" and r["src"] == "restored"
    assert r["text"].startswith("당일 모드 손절 — ") and "3.0%" in r["text"]
    assert " · 선" not in r["text"] and "None" not in r["text"]
    assert x["line_role"] == "fired"
    assert x["fired_line"] is None and x["fired_src"] is None and x["line_na"] == "unknown"
    assert x["judge"] == {"price": 9700, "upper": None, "src": "log_pct", "na": None}
    assert x["slip_order"] is None and x["slip_order_na"] == "before_record"
    sj = x["slip_judge"]
    assert (sj["ref_price"], sj["ref_src"], sj["per_share_won"], sj["bp"], sj["total_won"], sj["bound"]) == (
        9700, "derived", 10, 10.3, 500, "exact")


def test_d_same_day_exit_has_no_excursion_and_stops_before_record(card_d):
    ex = card_d["excursion"]
    assert ex["na"] == "not_applicable" and ex["mfe"] is None and ex["mae"] is None
    assert ex["closes_n"] == 0
    assert card_d["entry"]["initial_stop"]["price"] is None
    assert card_d["entry"]["initial_stop"]["na"] == "before_record"
    assert card_d["stop_track"]["na"] == "before_record" and card_d["stop_track"]["rows"] == []
    t = card_d["entry"]["target"]
    assert t["kind"] == "none" and t["na"] == "not_applicable" and t["text"] == "없음 — 15:20·익일 청산"


# ════════════════════════════════════════════════════════════════════════════
# 시나리오 E — 기록 시작 전(05-12) 변동성돌파 · 15:20 강제청산 · 일지 행 0
# ════════════════════════════════════════════════════════════════════════════
E_B, E_S = _uuid("e", 1), _uuid("e", 2)
E_FILLS = [
    _fill(E_B, "BUY", "2026-05-12T09:01:00", 30000, 10, order_no="B3"),
    _fill(E_S, "SELL", "2026-05-12T15:20:05", 30500, 10, order_no="S3", pl=5000),
]


@pytest.fixture(scope="module")
def card_e(jv):
    pair = _pair_from(E_FILLS, "volatility_breakout", "000660", "SK하이닉스", costs=_est_costs(E_FILLS))
    return jv.build_card(pair, **_kw(pair, E_FILLS, record_start=RS_REAL,
                                     business_days=[date(2026, 5, 12)],
                                     closes=[_close("000660", date(2026, 5, 12), 30400)]))


def test_e_before_orders_card(card_e):
    assert card_e["record_notice"] == "before_orders"
    r = card_e["entry"]["reason"]
    assert r["text"] is None and r["na"] == "before_record"
    ln = card_e["entry"]["orders"][0]
    assert (ln["source"], ln["source_na"]) == (None, "before_record")
    assert (ln["division"], ln["division_na"]) == (None, "before_record")
    assert ln["judge"]["price"] is None and ln["judge"]["na"] == "before_record"
    assert ln["slip_order"] is None and ln["slip_order_na"] == "before_record"
    x = card_e["exits"][0]
    assert x["reason"]["code"] is None and x["reason"]["text"] is None
    assert x["reason"]["na"] == "before_record"
    assert card_e["entry"]["initial_stop"]["na"] == "before_record"
    assert card_e["excursion"]["na"] == "not_applicable"
    t = card_e["entry"]["target"]
    assert t["na"] == "not_applicable" and t["text"] == "없음 — 15:20 당일 청산"
    # 기록 전이어도 일자·가격·비용·평가손익은 있다
    assert card_e["pnl"]["gross_krw"] == 5000 and card_e["costs"]["paid_total"] is not None


# ════════════════════════════════════════════════════════════════════════════
# T1 — 「모름 ≠ 0」 (값이 None ⇔ *_na 있음) — 전 시나리오 + 실패 4경우
# ════════════════════════════════════════════════════════════════════════════
def _pairs_of(card):
    """(경로, 값, na) — 값이 None 이면 na 가 있어야 하고, 값이 있으면 na 는 None."""
    out = [("pnl.gross", card["pnl"]["gross_krw"], card["pnl"]["gross_na"]),
           ("pnl.net", card["pnl"]["net_krw"], card["pnl"]["net_na"])]
    lines = [("entry", ln) for ln in card["entry"]["orders"]] + [("exit", ln) for ln in card["exits"]]
    for tag, ln in lines:
        out += [(f"{tag}.division", ln["division"], ln["division_na"]),
                (f"{tag}.source", ln["source"], ln["source_na"]),
                (f"{tag}.slip_order", ln["slip_order"], ln["slip_order_na"]),
                (f"{tag}.judge", ln["judge"]["price"], ln["judge"]["na"])]
        if tag == "exit":
            out.append(("exit.reason", ln["reason"]["text"], ln["reason"]["na"]))
            if ln["line_role"] in ("fired", "reference"):
                has = ln["fired_line"] is not None or ln["effective_line"] is not None
                out.append(("exit.line", True if has else None, ln["line_na"]))
    e = card["entry"]
    out += [("entry.reason", e["reason"]["text"], e["reason"]["na"]),
            ("initial_stop", e["initial_stop"]["price"], e["initial_stop"]["na"]),
            ("target", e["target"]["price"] if e["target"]["kind"] != "none" else None, e["target"]["na"]),
            ("costs", card["costs"]["entry_fee"], card["costs"]["na"]),
            ("costs.expected_exit", card["costs"]["expected_exit"], card["costs"]["expected_exit_na"]),
            ("excursion.mfe", card["excursion"]["mfe"], card["excursion"]["na"]),
            ("excursion.mae", card["excursion"]["mae"], card["excursion"]["na"]),
            ("stop_track", card["stop_track"]["rows"] or None, card["stop_track"]["na"])]
    return out


def _assert_na_rule(card):
    bad = []
    for path, val, na in _pairs_of(card):
        if na is not None and na not in NA_KINDS:
            bad.append(f"{path}: na={na!r} (5종 밖)")
        if (val is None) != (na is not None):
            bad.append(f"{path}: value={val!r} na={na!r}")
    assert not bad, "「모름 ≠ 0」 위반:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("name", ["card_a", "card_c", "card_d", "card_e"])
def test_t1_na_rule_holds_on_every_scenario(name, request):
    _assert_na_rule(request.getfixturevalue(name))


def test_t1_cost_lookup_failed(jv):
    pair = _a_pair()
    for k in ("fee", "tax", "net_profit_loss", "net_profit_rate", "cost_status", "allocated", "slippage_won",
              "cost_bp"):
        pair.pop(k, None)
    card = jv.build_card(pair, **_a_kw(costs=None))
    co = card["costs"]
    assert co["na"] == "lookup_failed"
    assert co["entry_fee"] is None and co["paid_total"] is None
    assert co["fee_total"] is None and co["tax_total"] is None and co["status"] is None
    assert all(x["fee"] is None and x["tax"] is None for x in co["exits"])
    assert card["pnl"]["net_krw"] is None and card["pnl"]["net_na"] == "lookup_failed"
    assert card["pnl"]["gross_krw"] == 44000   # 세전은 거래기록이라 그대로
    assert card["entry"]["orders"][0]["slip_order"]["total_won"] == 400   # 체결오차는 비용 원천과 무관
    _assert_na_rule(card)


def test_t1_open_pair_price_pending(jv):
    """보유 중 시세 미수신 — overlay 가 fee·tax·net 을 None 으로 둔 페어(2차 보완 B1)."""
    pair = _c_pair(profit_loss=None, profit_rate=None, fee=None, tax=None, net_profit_loss=None,
                   net_profit_rate=None)
    card = jv.build_card(pair, **_c_kw())
    p = card["pnl"]
    assert p["gross_krw"] is None and p["gross_na"] == "pending"
    assert p["net_krw"] is None and p["net_na"] == "pending"
    co = card["costs"]
    assert co["expected_exit"] is None and co["expected_exit_na"] == "pending"
    assert co["paid_total"] == pytest.approx(1448.4 + 390.5 + 547.25, abs=0.01)   # 낸 비용은 안다
    _assert_na_rule(card)


def test_t1_journal_tables_lookup_failed(jv):
    """047 표 조회 실패 — 일지에 기대는 칸만 「조회 실패」, 거래기록·비용·종가는 그대로."""
    card = jv.build_card(_a_pair(), **_a_kw(orders=None, stops=None))
    e = card["entry"]
    assert e["reason"]["text"] is None and e["reason"]["na"] == "lookup_failed"
    ln = e["orders"][0]
    assert (ln["source"], ln["source_na"]) == (None, "lookup_failed")
    assert (ln["division"], ln["division_na"]) == (None, "lookup_failed")
    assert ln["judge"]["price"] is None and ln["judge"]["na"] == "lookup_failed"
    assert ln["slip_order"]["ref_src"] == "trade"   # 주문가 기준은 거래기록이라 그대로
    assert card["exits"][0]["reason"]["na"] == "lookup_failed"
    assert e["initial_stop"]["na"] == "lookup_failed"
    assert e["target"]["price"] is None and e["target"]["na"] == "lookup_failed"
    assert card["stop_track"]["na"] == "lookup_failed" and card["stop_track"]["rows"] == []
    assert card["excursion"]["mfe"] is not None and card["costs"]["na"] is None
    _assert_na_rule(card)


def test_t1_zero_closes_is_unknown_not_zero(jv):
    card = jv.build_card(_a_pair(), **_a_kw(closes=[]))
    ex = card["excursion"]
    assert ex["na"] == "unknown" and ex["mfe"] is None and ex["mae"] is None
    assert (ex["closes_k"], ex["closes_n"]) == (0, 3)


@pytest.mark.parametrize("over", [{"closes": None}, {"business_days": None}])
def test_t1_closes_or_days_lookup_failed(jv, over):
    card = jv.build_card(_a_pair(), **_a_kw(**over))
    assert card["excursion"]["na"] == "lookup_failed"
    assert card["excursion"]["mfe"] is None and card["excursion"]["mae"] is None


# ════════════════════════════════════════════════════════════════════════════
# T2 — 체결오차 부호·판단가·상한·C2
# ════════════════════════════════════════════════════════════════════════════
def _two_leg(jv, *, strategy="momentum", ticker="005930", buy=(10000, None), sell=(10100, None), qty=10,
             buy_row=None, sell_row=None, rs=RS, day="2026-10-05", sell_day=None, sell_time="14:00:00",
             stops=None, llm=None, extra_fills=()):
    """매수 1·매도 1 닫힌 페어. buy/sell = (체결가, trade_history.order_price)."""
    sd = sell_day or day
    b, s = _uuid("f", 1), _uuid("f", 2)
    fills = [
        _fill(b, "BUY", f"{day}T09:30:00", buy[0], qty, order_no="BX", order_price=buy[1]),
        _fill(s, "SELL", f"{sd}T{sell_time}", sell[0], qty, order_no="SX", order_price=sell[1],
              pl=(sell[0] - buy[0]) * qty),
        *extra_fills,
    ]
    orders = [r for r in (buy_row, sell_row) if r is not None]
    pair = _pair_from(fills, strategy, ticker, "종목", costs=_est_costs(fills))
    return jv.build_card(pair, **_kw(pair, fills, orders=orders, stops=stops or [], record_start=rs,
                                     llm_evals=llm or []))


def test_t2_buy_worse_fill_is_positive_sell_worse_fill_is_positive(jv):
    card = _two_leg(jv, buy=(10050, 10000), sell=(9950, 10000))
    b = card["entry"]["orders"][0]["slip_order"]
    s = card["exits"][0]["slip_order"]
    assert (b["per_share_won"], b["bp"], b["total_won"]) == (50, 50.0, 500)
    assert (s["per_share_won"], s["bp"], s["total_won"]) == (50, 50.0, 500)


def test_t2_favorable_fills_are_negative_and_bp_one_decimal(jv):
    card = _two_leg(jv, buy=(9997, 10000), sell=(10011, 10000))
    b = card["entry"]["orders"][0]["slip_order"]
    s = card["exits"][0]["slip_order"]
    assert b["per_share_won"] == -3 and b["bp"] == -3.0 and b["total_won"] == -30
    assert s["per_share_won"] == -11 and s["bp"] == -11.0 and s["total_won"] == -110
    card2 = _two_leg(jv, buy=(12351, 12340))
    assert card2["entry"]["orders"][0]["slip_order"]["bp"] == 8.9   # 11/12340×1e4 = 8.914…


def test_t2_upper_bound_judge_kojiro_atr_stop(jv):
    """kojiro ATR 손절은 판단가 상한(손절선)만 안다 → `bound='upper'`(화면 「≤」)."""
    row = _order(date(2026, 10, 5), "SX", "SELL", "kojiro", "005930", reason_code="STOP_LOSS", fired=47000,
                 signal={"signal_name": "STOP_LOSS", "phrase": "kojiro_atr_stop", "line": 47000,
                         "buy_price": 51000, "judge_src": None, "judge_upper": 47000, "path": "accept"})
    card = _two_leg(jv, strategy="kojiro", buy=(51000, None), sell=(46800, None), sell_row=row)
    j = card["exits"][0]["judge"]
    assert j["price"] is None and j["upper"] == 47000
    sj = card["exits"][0]["slip_judge"]
    assert sj["ref_price"] == 47000 and sj["bound"] == "upper"
    assert sj["per_share_won"] == 200 and sj["bp"] == 42.6 and sj["total_won"] == 2000


def test_t2_c2_sell_order_price_is_not_copied_into_judge(jv):
    """C2 — 매도 판단가가 없으면 주문가로 채우지 않는다(주문가는 접수 뒤 시세)."""
    row = _order(date(2026, 10, 5), "SX", "SELL", "momentum", "005930", reason_code="FORCE_CLEAR",
                 signal={"signal_name": "FORCE_CLEAR", "reason_line": None, "phrase": None, "judge_src": None,
                         "path": "accept"})
    card = _two_leg(jv, sell=(10100, 10120), sell_row=row)
    x = card["exits"][0]
    assert x["judge"]["price"] is None and x["judge"]["upper"] is None and x["judge"]["na"] is not None
    assert x["slip_judge"] is None
    assert x["slip_order"]["ref_price"] == 10120 and x["slip_order"]["ref_src"] == "trade"


def test_t2_order_ref_falls_back_to_journal_accept_price(jv):
    """주문가 기준: trade_history.order_price 없으면 일지 행 order_price(src = 일지 출처)."""
    brow = _order(date(2026, 10, 5), "BX", "BUY", "momentum", "005930", order_price=10000, judge_price=9990,
                  signal={"signal_src": "log_only", "path": "accept"})
    card = _two_leg(jv, buy=(10010, None), buy_row=brow)
    ln = card["entry"]["orders"][0]
    assert ln["slip_order"]["ref_price"] == 10000 and ln["slip_order"]["ref_src"] == "live"
    assert ln["slip_order"]["per_share_won"] == 10
    # 판단가(9,990) ≠ 주문가(10,000) → 판단가 기준을 따로 보낸다
    sj = ln["slip_judge"]
    assert sj["ref_price"] == 9990 and sj["per_share_won"] == 20 and sj["ref_src"] == "live"


def test_t2_no_order_ref_inside_record_period_is_unknown(jv):
    card = _two_leg(jv, buy=(10010, None), rs={**RS, "order_price": "2026-10-01"})
    ln = card["entry"]["orders"][0]
    assert ln["slip_order"] is None and ln["slip_order_na"] == "unknown"


def test_order_line_groups_partial_fills_weighted_floor(jv):
    """한 주문의 체결 여러 행 = 1줄 — 수량 가중평균 체결가(원 내림)·첫 행 시각·id 전부."""
    b1, b2, s1 = _uuid("g", 1), _uuid("g", 2), _uuid("g", 3)
    fills = [
        _fill(b1, "BUY", "2026-10-05T09:30:00", 10000, 10, order_no="BQ", order_price=10000),
        _fill(b2, "BUY", "2026-10-05T09:30:02", 10010, 5, order_no="BQ", order_price=10000),
        _fill(s1, "SELL", "2026-10-05T14:00:00", 10100, 15, order_no="SQ", pl=1450),
    ]
    pair = _pair_from(fills, "momentum", "005930", costs=_est_costs(fills))
    card = jv.build_card(pair, **_kw(pair, fills))
    assert len(card["entry"]["orders"]) == 1
    ln = card["entry"]["orders"][0]
    assert ln["trade_ids"] == [b1, b2] and ln["qty"] == 15
    assert ln["price"] == 10003                     # (100000 + 50050) / 15 = 10003.33…
    assert ln["at"].startswith("2026-10-05T09:30:00")
    assert ln["slip_order"]["total_won"] == 50      # 0×10 + 10×5


def test_division_before_record_vs_unknown_by_0928(jv):
    def row(d):
        return _order(d, "BX", "BUY", "momentum", "005930", source="log_restore", judge_price=10000,
                      signal={"signal_src": "log_only", "path": "accept"})
    before = _two_leg(jv, day="2026-09-25", buy_row=row(date(2026, 9, 25)), rs=RS_REAL)
    after = _two_leg(jv, day="2026-09-29", buy_row=row(date(2026, 9, 29)), rs=RS_REAL)
    assert before["entry"]["orders"][0]["division_na"] == "before_record"
    assert after["entry"]["orders"][0]["division_na"] == "unknown"


# ════════════════════════════════════════════════════════════════════════════
# T4 — MFE/MAE 날짜 규칙
# ════════════════════════════════════════════════════════════════════════════
def _ex_card(jv, fills, closes, days, *, ticker="005930"):
    pair = _pair_from(fills, "donchian_swing", ticker, costs=_est_costs(fills))
    return jv.build_card(pair, **_kw(pair, fills, closes=closes, business_days=days))["excursion"]


def test_t4_after_hours_full_exit_same_day_includes_that_day(jv):
    fills = [_fill(_uuid("h", 1), "BUY", "2026-10-05T10:00:00", 10000, 10, order_no="B"),
             _fill(_uuid("h", 2), "SELL", "2026-10-05T16:02:00", 10200, 10, order_no="S", pl=2000)]
    ex = _ex_card(jv, fills, [_close("005930", date(2026, 10, 5), 10150)], [date(2026, 10, 5)])
    assert (ex["closes_k"], ex["closes_n"]) == (1, 1) and ex["na"] is None
    assert ex["mfe"]["date"] == "2026-10-05" and ex["mfe"]["pct"] == 1.5 and ex["mfe"]["krw"] == 1500


def test_t4_buy_after_1530_starts_next_business_day(jv):
    fills = [_fill(_uuid("h", 3), "BUY", "2026-10-05T16:30:00", 10000, 10, order_no="B"),
             _fill(_uuid("h", 4), "SELL", "2026-10-07T10:00:00", 10300, 10, order_no="S", pl=3000)]
    closes = [_close("005930", date(2026, 10, d), px) for d, px in ((5, 9000), (6, 10400), (7, 11000))]
    ex = _ex_card(jv, fills, closes, [date(2026, 10, d) for d in (5, 6, 7)])
    assert (ex["closes_k"], ex["closes_n"]) == (1, 1)
    assert ex["mfe"]["date"] == ex["mae"]["date"] == "2026-10-06"


def test_t4_partial_sell_before_1530_reduces_that_day_qty(jv):
    fills = [_fill(_uuid("h", 5), "BUY", "2026-10-05T10:00:00", 10000, 20, order_no="B"),
             _fill(_uuid("h", 6), "SELL", "2026-10-06T11:00:00", 10500, 5, order_no="S1", pl=2500),
             _fill(_uuid("h", 7), "SELL", "2026-10-07T16:10:00", 10400, 15, order_no="S2", pl=6000)]
    closes = [_close("005930", date(2026, 10, d), px) for d, px in ((5, 10000), (6, 11000), (7, 10500))]
    ex = _ex_card(jv, fills, closes, [date(2026, 10, d) for d in (5, 6, 7)])
    assert (ex["closes_k"], ex["closes_n"]) == (3, 3)
    assert ex["mfe"] == {"pct": 10.0, "krw": 15000, "date": "2026-10-06", "close": 11000, "qty": 15,
                         "provisional": False}
    assert ex["mae"]["date"] == "2026-10-05" and ex["mae"]["qty"] == 20 and ex["mae"]["pct"] == 0.0


def test_t4_tie_picks_earlier_day(jv):
    fills = [_fill(_uuid("h", 8), "BUY", "2026-10-05T10:00:00", 10000, 10, order_no="B"),
             _fill(_uuid("h", 9), "SELL", "2026-10-08T10:00:00", 10000, 10, order_no="S", pl=0)]
    closes = [_close("005930", date(2026, 10, d), px) for d, px in ((5, 9500), (6, 11000), (7, 11000))]
    ex = _ex_card(jv, fills, closes, [date(2026, 10, d) for d in (5, 6, 7, 8)])
    assert ex["mfe"]["date"] == "2026-10-06"
    assert ex["mae"]["date"] == "2026-10-05" and ex["mae"]["pct"] == -5.0


def test_t4_close_of_other_ticker_is_ignored(jv):
    fills = [_fill(_uuid("h", 10), "BUY", "2026-10-05T10:00:00", 10000, 10, order_no="B"),
             _fill(_uuid("h", 11), "SELL", "2026-10-06T10:00:00", 10100, 10, order_no="S", pl=1000)]
    closes = [_close("999999", date(2026, 10, 5), 50000), _close("005930", date(2026, 10, 5), 10200)]
    ex = _ex_card(jv, fills, closes, [date(2026, 10, 5), date(2026, 10, 6)])
    assert ex["mfe"]["close"] == 10200 and (ex["closes_k"], ex["closes_n"]) == (1, 1)


# ════════════════════════════════════════════════════════════════════════════
# T5 — 최초 손절
# ════════════════════════════════════════════════════════════════════════════
def _stop_card(jv, stops, *, strategy="donchian_swing", rs=RS, buy_at="2026-10-05T09:12:03"):
    fills = [_fill(_uuid("s", 1), "BUY", buy_at, 10000, 10, order_no="B1")]
    pair = _pair_from(fills, strategy, "005930", open_pl=1000)
    return jv.build_card(pair, **_kw(pair, fills, stops=stops, record_start=rs))


def test_t5_next_day_first_row_is_not_initial_stop(jv):
    rows = [_stop("donchian_swing", "005930", "2026-10-06T09:05:00", "first", 9600)]
    card = _stop_card(jv, rows, rs={**RS, "stops": "2026-10-06"})
    st = card["entry"]["initial_stop"]
    assert st["price"] is None and st["na"] == "before_record"
    assert st["first_seen"]["price"] == 9600 and st["first_seen"]["observed_at"].startswith("2026-10-06T09:05:00")
    card2 = _stop_card(jv, rows, rs=RS)   # 기록 기간 안인데 매수일 관측이 없다 → 모름
    assert card2["entry"]["initial_stop"]["price"] is None
    assert card2["entry"]["initial_stop"]["na"] == "unknown"
    assert card2["entry"]["initial_stop"]["first_seen"]["price"] == 9600


def test_t5_ltv_mode_dependent_has_no_price(jv):
    rows = [_stop("long_tail_volatility", "005930", "2026-10-05T09:12:20", "first", None, kind="mode_dependent")]
    st = _stop_card(jv, rows, strategy="long_tail_volatility")["entry"]["initial_stop"]
    assert st["price"] is None and st["kind"] == "mode_dependent" and st["na"] == "unknown"


@pytest.mark.parametrize("rs,na", [(RS, "unknown"), (RS_REAL, "before_record")])
def test_t5_no_rows(jv, rs, na):
    card = _stop_card(jv, [], rs=rs)
    assert card["entry"]["initial_stop"]["na"] == na
    assert card["stop_track"]["na"] == na and card["stop_track"]["rows"] == []


def test_t5_delay_seconds(jv):
    rows = [_stop("donchian_swing", "005930", "2026-10-05T09:20:03", "first", 9500)]
    st = _stop_card(jv, rows)["entry"]["initial_stop"]
    assert st["price"] == 9500 and st["delay_s"] == 480 and st["pct_from_entry"] == -5.0


# ════════════════════════════════════════════════════════════════════════════
# T6 — 변화 원인 13줄 (직전에 보인 행과 비교 · 최대 2개)
# ════════════════════════════════════════════════════════════════════════════
_BASE_IN = {"buy_price": 10500, "quantity": 10, "high_since_buy": 10500, "entry_atr": 300, "kk_armed": False,
            "stop_source": "effective", "target_source": None}


def _second_row_cause(jv, *, strategy="donchian_swing", event="change", price, inputs, kind="effective",
                      target=None, hit=None, first_target=None, first_hit=None):
    rows = [
        _stop(strategy, "005930", "2026-10-05T09:12:20", "first", 10000, target=first_target, hit=first_hit,
              inputs=_BASE_IN),
        _stop(strategy, "005930", "2026-10-06T10:00:00", event, price, kind=kind, target=target, hit=hit,
              inputs=inputs),
    ]
    fills = [_fill(_uuid("t", 1), "BUY", "2026-10-05T09:12:03", 10500, 10, order_no="B1")]
    pair = _pair_from(fills, strategy, "005930", open_pl=0)
    card = jv.build_card(pair, **_kw(pair, fills, stops=rows))
    vis = card["stop_track"]["rows"]
    assert len(vis) == 2, vis
    return vis[1]


@pytest.mark.parametrize("label,kw,expect", [
    ("quantity", dict(price=10050, inputs={**_BASE_IN, "quantity": 12}), "수량 변화(추가 체결·분할 매도)"),
    ("buy_price", dict(price=10050, inputs={**_BASE_IN, "buy_price": 10600}), "매수가 변화(추가 체결)"),
    ("stop_kind", dict(price=10050, kind="hard_pct", inputs=_BASE_IN), "손절선 출처 바뀜"),
    ("high", dict(price=10200, inputs={**_BASE_IN, "high_since_buy": 11000}), "고점 갱신"),
    ("atr", dict(price=9950, inputs={**_BASE_IN, "entry_atr": 350}), "ATR 변화"),
    ("nothing", dict(price=10100, inputs=_BASE_IN), "입력 그대로 — 파라미터 변경·일봉 재계산 추정"),
])
def test_t6_single_cause(jv, label, kw, expect):
    assert _second_row_cause(jv, **kw)["cause"] == expect, label


def test_t6_kk_armed_cause_first(jv):
    row = _second_row_cause(jv, price=10500, inputs={**_BASE_IN, "kk_armed": True})
    assert row["cause"].startswith("3R 도달 — 본전 무장")


def test_t6_breakeven_promotion(jv):
    row = _second_row_cause(jv, price=10500, inputs=_BASE_IN)
    assert row["cause"] == "본전 승격" and row["direction"] == "up" and row["delta_won"] == 500


def test_t6_target_update_and_hit(jv):
    up = _second_row_cause(jv, strategy="bull_flag_breakout", price=10000, target=11500, hit=False,
                           first_target=11000, first_hit=False, inputs=_BASE_IN)
    assert up["cause"] == "목표 갱신"
    hit = _second_row_cause(jv, strategy="bull_flag_breakout", price=10000, target=11000, hit=True,
                            first_target=11000, first_hit=False, inputs=_BASE_IN)
    assert hit["cause"] == "목표 도달"


def test_t6_ltv_boot_adds_limit_up_note(jv):
    row = _second_row_cause(jv, strategy="long_tail_volatility", event="boot", price=10000, inputs=_BASE_IN)
    assert row["cause"].startswith("재시작 재계산") and "상한가 모드 소실 가능" in row["cause"]


def test_t6_at_most_two_causes(jv):
    row = _second_row_cause(jv, price=10400, inputs={**_BASE_IN, "quantity": 12, "buy_price": 10600,
                                                     "high_since_buy": 11500, "entry_atr": 350})
    assert row["cause"] == "수량 변화(추가 체결·분할 매도) · 매수가 변화(추가 체결)"


def test_t6_unchanged_change_row_is_hidden_but_not_counted_as_eod(jv):
    rows = [
        _stop("donchian_swing", "005930", "2026-10-05T09:12:20", "first", 10000, inputs=_BASE_IN),
        _stop("donchian_swing", "005930", "2026-10-05T11:00:00", "change", 10000, inputs={**_BASE_IN, "quantity": 12}),
        _stop("donchian_swing", "005930", "2026-10-05T15:31:00", "eod", 10000, inputs=_BASE_IN),
    ]
    fills = [_fill(_uuid("t", 2), "BUY", "2026-10-05T09:12:03", 10500, 10, order_no="B1")]
    pair = _pair_from(fills, "donchian_swing", "005930", open_pl=0)
    tr = jv.build_card(pair, **_kw(pair, fills, stops=rows))["stop_track"]
    assert [r["event"] for r in tr["rows"]] == ["first"]
    assert tr["hidden_eod"] == 1


# ════════════════════════════════════════════════════════════════════════════
# T7 — 진입 이유 문장 (3-1 · 3-2)
# ════════════════════════════════════════════════════════════════════════════
def _entry_text(jv, strategy, signal, *, params=None, source="log_harvest", judge=None, day="2026-10-05",
                llm=None, rs=RS):
    row = _order(date.fromisoformat(day), "BX", "BUY", strategy, "005930", source=source, judge_price=judge,
                 order_price=judge, signal=signal, params=params)
    card = _two_leg(jv, strategy=strategy, day=day, buy_row=row, llm=llm, rs=rs)
    return card["entry"]


@pytest.mark.parametrize("strategy,signal,params,expect", [
    ("bull_flag_breakout", {"flag_high": 12300, "target_price": 13450, "atr": 410}, None,
     "깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410"),
    ("vcp_breakout", {"base_high": 22000, "atr": 800}, None, "베이스 고점 22,000 돌파 · ATR 800"),
    ("kojiro", {"stage": 2, "atr": 1500}, None, "스테이지2 신규 진입 · 이평 정배열 · ATR 1,500"),
    ("etf_trend", {"line": 10500, "open_price": 10550, "atr": 120}, None,
     "돌파선 10,500 종가 돌파(전일) · 시가 10,550 진입 · N 120"),
    ("donchian_swing", {"donchian_high": 45000, "atr": 1200}, {"donchian_period": 20},
     "20일 신고가 45,000 돌파 · ATR 1,200"),
    # 키가 빠진 절은 뺀다(0·None 을 찍지 않는다)
    ("donchian_swing", {"donchian_high": 45000, "atr": 1200}, None, "신고가 45,000 돌파 · ATR 1,200"),
    ("bull_flag_breakout", {"flag_high": 12300, "atr": 410}, None, "깃발 상단 12,300 돌파 · ATR 410"),
])
def test_t7_ring_entry_sentence_exact(jv, strategy, signal, params, expect):
    e = _entry_text(jv, strategy, {**signal, "signal_src": "ring", "path": "accept"}, params=params)
    assert e["reason"]["text"] == expect
    assert e["reason"]["signal_src"] == "ring" and e["reason"]["src"] == "live"


@pytest.mark.parametrize("strategy,signal,params,parts", [
    ("momentum", {"prev_close": 10000, "change_rate": 5.2}, {"buy_threshold": 5.0},
     ["전일 종가 10,000 대비 ", "5.2% 급등", " · 기준 ", "5.0%"]),
    ("volatility_breakout", {"board": "main", "target_price": 30500, "k": 0.5, "change_rate": 2.1}, None,
     ["돌파선 30,500 돌파", " · K 0.50", " · 시가 대비 ", "2.1%"]),
    ("long_tail_volatility", {"board": "pre_nxt", "target_price": 8120, "k": 0.45, "change_rate": 3.4}, None,
     ["돌파선 8,120 돌파", " · K 0.45", "3.4%"]),
])
def test_t7_ring_entry_sentence_parts(jv, strategy, signal, params, parts):
    text = _entry_text(jv, strategy, {**signal, "signal_src": "ring", "path": "accept"}, params=params)["reason"]["text"]
    for part in parts:
        assert part in text, (part, text)
    assert "None" not in text


def test_t7_vb_trigger_price_is_not_take_profit_target(jv):
    e = _entry_text(jv, "volatility_breakout", {"board": "main", "target_price": 30500, "k": 0.5,
                                                "signal_src": "ring", "path": "accept"})
    assert e["target"]["price"] is None and e["target"]["kind"] == "none"
    assert e["target"]["text"] == "없음 — 15:20 당일 청산"


@pytest.mark.parametrize("strategy,judge,source,signal,expect,src", [
    ("momentum", 10520, "log_restore", {"signal_src": "log_only"}, "매수 신호 · 신호가 10,520 — 구조값 기록 없음",
     "restored"),
    ("bull_flag_breakout", None, "log_restore", {"signal_src": "log_only"}, "거래량 관문 통과 매수 — 구조값 기록 없음",
     "restored"),
    ("vcp_breakout", None, "log_harvest", {"signal_src": "none"}, "매수 신호 기록 없음", "live"),
])
def test_t7_fallback_entry_sentences(jv, strategy, judge, source, signal, expect, src):
    e = _entry_text(jv, strategy, {**signal, "path": "accept"}, source=source, judge=judge, day="2026-09-22")
    assert e["reason"]["text"] == expect and e["reason"]["src"] == src
    assert e["reason"]["signal_src"] == signal["signal_src"]


def _llm(day, strategy, **kw):
    row = {"trade_date": day, "ticker": "005930", "order_no": "BX", "strategy_id": strategy, "target_won": None,
           "k": None, "strategy_board": None, "signal_price_won": None}
    row.update(kw)
    return [row]


def test_t7_ai_augments_bfb_after_0917_and_fills_judge(jv):
    d = date(2026, 9, 22)
    e = _entry_text(jv, "bull_flag_breakout", {"signal_src": "log_only", "path": "accept"}, source="log_restore",
                    day="2026-09-22", llm=_llm(d, "bull_flag_breakout", target_won=12300, strategy_board="main",
                                               signal_price_won=12340))
    assert e["reason"]["text"].startswith("깃발 상단 12,300 돌파")
    assert "K " not in e["reason"]["text"]
    assert e["reason"]["src"] == "restored_ai"
    assert e["orders"][0]["judge"]["price"] == 12340 and e["orders"][0]["judge"]["src"] == "restored_ai"


def test_t7_ai_before_0917_only_vb_ltv(jv):
    """🔴 `target_won` 은 09-17(cycle297) 전엔 측정 목표가였다 — 그 전 BFB 는 보강하지 않는다."""
    d = date(2026, 9, 16)
    rs = {**RS_REAL, "orders_restored": "2026-09-10"}
    bfb = _entry_text(jv, "bull_flag_breakout", {"signal_src": "log_only", "path": "accept"}, source="log_restore",
                      day="2026-09-16", rs=rs, llm=_llm(d, "bull_flag_breakout", target_won=13450))
    assert bfb["reason"]["text"] == "거래량 관문 통과 매수 — 구조값 기록 없음"
    assert bfb["reason"]["src"] == "restored"
    vb = _entry_text(jv, "volatility_breakout", {"signal_src": "log_only", "path": "accept"}, source="log_restore",
                     judge=30500, day="2026-09-16", rs=rs,
                     llm=_llm(d, "volatility_breakout", target_won=30400, k=Decimal("0.5"), strategy_board="main"))
    assert "돌파선 30,400 돌파" in vb["reason"]["text"] and "K 0.5" in vb["reason"]["text"]
    assert vb["reason"]["src"] == "restored_ai"


def test_t7_ai_join_key_and_strategies_without_target(jv):
    # 다른 날짜의 같은 주문번호는 잇지 않는다(KIS ODNO 는 하루 단위로만 유일).
    other_day = _entry_text(jv, "bull_flag_breakout", {"signal_src": "log_only", "path": "accept"},
                            source="log_restore", day="2026-09-22",
                            llm=_llm(date(2026, 9, 23), "bull_flag_breakout", target_won=12300))
    assert other_day["reason"]["src"] == "restored"
    # momentum 은 target_won 이 없어 보강하지 않는다.
    mom = _entry_text(jv, "momentum", {"signal_src": "log_only", "path": "accept"}, source="log_restore",
                      judge=10520, day="2026-09-22", llm=_llm(date(2026, 9, 22), "momentum"))
    assert mom["reason"]["text"] == "매수 신호 · 신호가 10,520 — 구조값 기록 없음"


# ════════════════════════════════════════════════════════════════════════════
# T7 — 청산 이유 문장 (3-3) · 발동선 출처 · 선 역할 · 경로 꼬리 · renamed_from
# ════════════════════════════════════════════════════════════════════════════
def _exit(jv, strategy, *, code, signal=None, sub=None, fired=None, eff=None, judge=None, source="log_harvest",
          parent=None, buy=10000, sell=9800):
    sig = {"signal_name": code, "reason_line": None, "phrase": None, "judge_src": None, "path": "accept"}
    sig.update(signal or {})
    row = _order(date(2026, 10, 5), "SX", "SELL", strategy, "005930", source=source, reason_code=code,
                 reason_sub=sub, fired=fired, eff=eff, judge_price=judge, parent=parent, signal=sig)
    return _two_leg(jv, strategy=strategy, buy=(buy, None), sell=(sell, None), sell_row=row)["exits"][0]


_EXACT_EXITS = [
    ("kojiro_atr", "kojiro", "STOP_LOSS", dict(signal={"phrase": "kojiro_atr_stop", "line": 47000, "buy_price": 51000},
                                               fired=47000), "ATR 손절 — 손절선 47,000 이탈"),
    ("bfb_turtle", "bull_flag_breakout", "STOP_LOSS",
     dict(signal={"phrase": "bfb_turtle_stop", "line": 11800, "buy_price": 12350}, fired=11800),
     "터틀 손절(E−2N) — 손절선 11,800 이탈"),
    ("stop_no_phrase", "donchian_swing", "STOP_LOSS", dict(eff=48200), "손절선 48,200 이탈"),
    ("kojiro_trailing", "kojiro", "TRAILING_STOP",
     dict(signal={"phrase": "kojiro_trailing", "line": 55000, "current_price": 54900}, fired=55000),
     "샹들리에 트레일 — 선 55,000 이탈 (현재가 54,900)"),
    ("donchian_trailing_legacy", "donchian_swing", "TRAILING_STOP",
     dict(signal={"phrase": "donchian_trailing_legacy", "line": 44000, "current_price": 43900}, fired=44000),
     "트레일(옛 규칙) — 선 44,000 이탈 (현재가 43,900)"),
    ("trailing_no_phrase", "vcp_breakout", "TRAILING_STOP", dict(eff=60000), "트레일선 60,000 이탈"),
    ("donchian_no_1r", "donchian_swing", "TIME_EXIT",
     dict(signal={"phrase": "donchian_time_exit",
                  "reason_line": "[donchian_time_exit] ticker=005930 reason=no_1r held=10"}),
     "+1R 미도달 — 시간 청산"),
    ("donchian_max_hold", "donchian_swing", "TIME_EXIT",
     dict(signal={"phrase": "donchian_time_exit",
                  "reason_line": "[donchian_time_exit] ticker=005930 reason=max_hold held=20"}),
     "최대 보유 기간 도달 — 시간 청산"),
    ("donchian_time_unreadable", "donchian_swing", "TIME_EXIT", dict(signal={"phrase": "donchian_time_exit"}),
     "시간 청산"),
    ("bfb_time", "bull_flag_breakout", "TIME_EXIT", dict(signal={"phrase": "bfb_time_exit"}),
     "보유 기한 초과 — 시간 청산"),
    ("donchian_time_legacy", "donchian_swing", "TIME_EXIT",
     dict(signal={"phrase": "donchian_time_exit_legacy", "current_price": 30000}),
     "돌파선 아래 — 시간 청산(옛 규칙) (현재가 30,000)"),
    ("kojiro_stage3", "kojiro", "TREND_EXIT", dict(signal={"phrase": "kojiro_stage3_exit"}),
     "스테이지3 진입 — 추세 종료"),
    ("etf_trend", "etf_trend", "TREND_EXIT", {}, "15:20 돌파선 아래 — 돌파 실패 정리"),
    ("vcp_trend", "vcp_breakout", "TREND_EXIT", {}, "추세 이탈 청산"),
    ("force_clear", "volatility_breakout", "FORCE_CLEAR", {}, "15:20 강제청산"),
    ("ndc_krx_only", "long_tail_volatility", "NEXT_DAY_CLEAR", dict(sub="krx_only"),
     "익일 청산 — KRX 전용 종목, 09:00 시장가"),
    ("ndc_nxt_missing", "long_tail_volatility", "NEXT_DAY_CLEAR", dict(sub="nxt_open_missing"),
     "익일 청산 — NXT 시가 미수신, KRX 시가 뒤"),
    ("ndc_plain", "momentum", "NEXT_DAY_CLEAR", {}, "익일 청산"),
    ("status_overheat", "kojiro", "STATUS_EXIT", dict(sub="overheat"), "단기과열 지정 — 보유 청산"),
    ("status_both", "kojiro", "STATUS_EXIT", dict(sub="managed+overheat"), "관리·과열 지정 — 보유 청산"),
    ("manual", "kojiro", "MANUAL", dict(source="manual_api", signal={"path": "manual"}), "수동 매도(화면)"),
]


@pytest.mark.parametrize("label,strategy,code,kw,expect", _EXACT_EXITS, ids=[c[0] for c in _EXACT_EXITS])
def test_t7_exit_sentence_exact(jv, label, strategy, code, kw, expect):
    assert _exit(jv, strategy, code=code, **kw)["reason"]["text"] == expect


@pytest.mark.parametrize("label,strategy,code,kw,parts", [
    ("kojiro_hard", "kojiro", "STOP_LOSS",
     dict(signal={"phrase": "kojiro_hard_stop", "buy_price": 51000, "pct": -10.2, "threshold": -10.0}, fired=45900),
     ["하드 손절 — 매수가 대비 ", "10.2%", " (기준 ", "10.0%)"]),
    ("bfb_backstop", "bull_flag_breakout", "STOP_LOSS",
     dict(signal={"phrase": "bfb_turtle_backstop", "buy_price": 12350, "pct": -8.1, "threshold": -8.0}, fired=11362),
     ["받침선 손절 — 매수가 대비 ", "8.1%", " (기준 ", "8.0%)"]),
    ("momentum_stop", "momentum", "STOP_LOSS",
     dict(signal={"phrase": "momentum_stop", "buy_price": 10000, "pct": -5.2, "threshold": -5.0,
                  "current_price": 9480}, fired=9500),
     ["고정 손절 — 매수가 대비 ", "5.2%", " (기준 ", "5.0%)"]),
    ("bfb_pullback", "bull_flag_breakout", "STOP_LOSS",
     dict(signal={"phrase": "bfb_pullback_stop", "buy_price": 12350, "pct": -4.1}, fired=11800),
     ["눌림목 손절 — 매수가 대비 ", "4.1%", " · 선 11,800"]),
    ("vb_stop", "volatility_breakout", "STOP_LOSS",
     dict(signal={"phrase": "vb_stop", "buy_price": 30000, "pct": -3.0, "current_price": 29100}, fired=29100),
     ["고정 손절 — 매수가 대비 ", "3.0%", " · 선 29,100"]),
    ("ltv_limit_up", "long_tail_volatility", "STOP_LOSS",
     dict(signal={"phrase": "ltv_limit_up_stop", "pct": -3.5, "mode": "limit_up"}, fired=9650),
     ["상한가 모드 손절 — ", "3.5%", " · 선 9,650"]),
    ("ndc_gap", "long_tail_volatility", "NEXT_DAY_CLEAR",
     dict(sub="gap_below", signal={"gap": 0.4, "gap_threshold": 1.0}), ["익일 청산 — 갭 ", "0.4% < 기준 ", "1.0%"]),
])
def test_t7_exit_sentence_parts(jv, label, strategy, code, kw, parts):
    text = _exit(jv, strategy, code=code, **kw)["reason"]["text"]
    for part in parts:
        assert part in text, (label, part, text)
    assert "None" not in text


@pytest.mark.parametrize("source,expect", [
    ("external", "엔진 밖 주문(HTS·MTS) — 사유 기록 없음"),
    ("unmatched", "사유 매핑 없음"),
])
def test_t7_no_reason_rows(jv, source, expect):
    row = _order(date(2026, 10, 5), "SX", "SELL", "kojiro", "005930", source=source, reason_code=None, signal=None)
    row["reason_code"] = None
    x = _two_leg(jv, strategy="kojiro", sell_row=row)["exits"][0]
    assert x["reason"]["code"] is None and x["reason"]["text"] == expect
    assert x["source"] == source


def test_t7_path_tails(jv):
    fb = _exit(jv, "momentum", code="STOP_LOSS", source="fallback_inferred",
               signal={"phrase": "momentum_stop", "buy_price": 10000, "pct": -5.2, "threshold": -5.0,
                       "path": "fallback"}, fired=9500)
    assert fb["reason"]["text"].endswith(" · 5호가 폴백") and fb["path"] == "fallback"
    ro = _exit(jv, "kojiro", code="STOP_LOSS", source="reorder_inferred", parent="S0",
               signal={"phrase": "kojiro_atr_stop", "line": 47000, "path": "reorder"}, fired=47000)
    assert "· 잔여 재주문(원주문 S0)" in ro["reason"]["text"]
    assert ro["parent_order_no"] == "S0" and ro["path"] == "reorder"


def test_t7_renamed_from_only_when_accept_name_differs(jv):
    renamed = _exit(jv, "kojiro", code="STOP_LOSS",
                    signal={"signal_name": "TRAILING_STOP", "phrase": "kojiro_hard_stop", "buy_price": 51000,
                            "pct": -10.2, "threshold": -10.0}, fired=45900)
    assert renamed["reason"]["renamed_from"] == "TRAILING_STOP"
    same = _exit(jv, "kojiro", code="STOP_LOSS", signal={"phrase": "kojiro_atr_stop", "line": 47000}, fired=47000)
    assert same["reason"]["renamed_from"] is None


@pytest.mark.parametrize("label,strategy,kw,source,fired_src", [
    ("line", "kojiro", dict(signal={"phrase": "kojiro_atr_stop", "line": 47000}, fired=47000), "log_harvest", "live"),
    ("line_restored", "kojiro", dict(signal={"phrase": "kojiro_atr_stop", "line": 47000}, fired=47000),
     "log_restore", "restored"),
    ("threshold", "momentum", dict(signal={"phrase": "momentum_stop", "buy_price": 10000, "pct": -5.2,
                                           "threshold": -5.0}, fired=9500), "log_harvest", "derived"),
    ("ltv", "long_tail_volatility", dict(signal={"phrase": "ltv_intraday_stop", "pct": -3.0}, fired=9700),
     "log_harvest", "derived"),
    ("snapshot", "bull_flag_breakout", dict(signal={"phrase": "bfb_pullback_stop", "buy_price": 12350,
                                                    "pct": -4.1}, fired=11800), "log_harvest", "snapshot"),
])
def test_t7_fired_src_regrading(jv, label, strategy, kw, source, fired_src):
    """C3 — 워커 `fired_line` 한 칸에 섞인 정확도 4종을 `signal` 키로 다시 가른다."""
    x = _exit(jv, strategy, code="STOP_LOSS", source=source, **kw)
    assert x["fired_src"] == fired_src, label
    assert x["line_role"] == "fired"


def test_t7_fired_and_effective_lines_stay_separate(jv):
    """🔴 발동선이 유효선보다 낮을 수 있다(kojiro 하드 → 2ATR → 샹들리에) — 둘을 합치지 않는다."""
    x = _exit(jv, "kojiro", code="STOP_LOSS", eff=47000,
              signal={"phrase": "kojiro_hard_stop", "buy_price": 51000, "pct": -10.2, "threshold": -10.0,
                      "snapshot_age_s": 6}, fired=45900)
    assert (x["fired_line"], x["effective_line"]) == (45900, 47000)
    assert x["snapshot_age_s"] == 6 and x["line_na"] is None


@pytest.mark.parametrize("code,eff,role,line_na", [
    ("FORCE_CLEAR", 9500, "reference", None),
    ("FORCE_CLEAR", None, "reference", "unknown"),
    ("NEXT_DAY_CLEAR", 9400, "reference", None),
    ("STOP_LOSS", None, "fired", "unknown"),
])
def test_t7_line_role(jv, code, eff, role, line_na):
    x = _exit(jv, "momentum", code=code, eff=eff)
    assert x["line_role"] == role and x["line_na"] == line_na


# ════════════════════════════════════════════════════════════════════════════
# 3-4 익절 목표 — donchian 3R 무장가·1R 면제선 · BFB 재탐색 목표 · 복원 BFB 기록 전 · 비용 배분 배지
# ════════════════════════════════════════════════════════════════════════════
def test_target_donchian_arm_and_one_r(jv):
    """3R 무장가 = 무장 전 값(무장 뒤엔 마지막 무장가 유지) · 1R 면제선 = 2E − 무장 전 손절선 · 무장 시각."""
    base = {"buy_price": 10000, "quantity": 10, "high_since_buy": 10000, "entry_atr": 250, "kk_armed": False,
            "stop_source": "effective", "target_source": None}
    rows = [
        _stop("donchian_swing", "005930", "2026-10-05T09:12:20", "first", 9500, arm=11500, inputs=base),
        _stop("donchian_swing", "005930", "2026-10-07T10:00:00", "change", 10000, arm=11500,
              inputs={**base, "high_since_buy": 11600, "kk_armed": True}),
    ]
    fills = [_fill(_uuid("k", 1), "BUY", "2026-10-05T09:12:03", 10000, 10, order_no="B1")]
    pair = _pair_from(fills, "donchian_swing", "005930", open_pl=5000)
    t = jv.build_card(pair, **_kw(pair, fills, stops=rows))["entry"]["target"]
    assert t["kind"] == "none" and t["price"] is None and t["na"] == "not_applicable"
    assert t["arm_price"] == 11500 and t["one_r_price"] == 10500
    assert t["armed_at"].startswith("2026-10-07T10:00:00")
    assert "3R 무장가 11,500" in t["text"] and "1R 면제선 10,500" in t["text"]
    assert "무장 — 손절선 본전" in t["text"]


def test_target_bfb_refound_after_restart_mentions_entry_target(jv):
    rows = [_a_stop("2026-10-05T09:12:20", "first", 11530, inputs=_IN0),
            _a_stop("2026-10-07T09:00:30", "boot", 11530, target=13600, inputs=_IN0)]
    t = jv.build_card(_a_pair(), **_a_kw(stops=rows))["entry"]["target"]
    assert t["price"] == 13600 and t["signal_price"] == 13450
    assert "재시작 뒤 다시 찾은 목표" in t["text"] and "13,450" in t["text"]


def test_target_restored_bfb_is_before_record(jv):
    """복원분 BFB — AI평가 `target_won` 은 깃발 상단이지 측정 목표가가 아니다 → 목표는 기록 전."""
    e = _entry_text(jv, "bull_flag_breakout", {"signal_src": "log_only", "path": "accept"}, source="log_restore",
                    day="2026-09-22", rs=RS_REAL,
                    llm=_llm(date(2026, 9, 22), "bull_flag_breakout", target_won=12300))
    assert e["target"]["kind"] == "measured_move"
    assert e["target"]["price"] is None and e["target"]["na"] == "before_record"


def test_cost_allocated_flags_follow_rows_and_pair(jv):
    costs = {A_BUY: dict(A_COSTS[A_BUY]), A_SELL: {**A_COSTS[A_SELL], "allocated": True}}
    card = jv.build_card(_a_pair(allocated=True), **_a_kw(costs=costs))
    co = card["costs"]
    assert co["entry_allocated"] is False and co["exits"][0]["allocated"] is True and co["allocated"] is True
