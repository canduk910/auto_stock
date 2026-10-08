"""cycle412 Red — 대사(설계 관찰자안 2절 「자기 점검」 · 3절 W3).

| # | 계약 |
|---|---|
| C1 | 항등식 셋: `SELL 주문 완료` 수 = 매도 일지 행 수 · `BUY 주문 완료` 수 = 매수 일지 행 수 · 사유 미상 매도 = 0 |
| C2 | 골든(매도 70·매수 75)에서 셋 다 성립 → `[journal_gap]` 0줄 |
| C3 | 하나라도 어긋나면 `[journal_gap]` WARNING 정확히 1줄(접두 고정) |
| C4 | `external`·`unmatched` 행은 항등식에서 뺀다 |
| C5 | 외부 행은 **체결된 것만** — trade_history COMPLETED/PARTIAL 이고 일지에 없는 주문: 접수 전문이 있으면 `external`, 없으면 `unmatched` · PENDING/CANCELLED·전문만 있는 주문 = 0 |
| C6 | 막 생긴 trade_history 행(120초 미만)은 아직 보지 않는다 — 짝짓기 보류 회전과 경주하지 않게 |
"""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from jw_testkit import golden_lines, jw, kst, parse_all

pytestmark = pytest.mark.unit


def _restore(lines):
    p = jw("pairing").Pairer(source="log_restore")
    evs = parse_all(lines)
    p.feed_events(evs)
    return evs, p.drain(final=True)["orders"]


def _gap_records(caplog):
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith("[journal_gap] ")]


def test_c1_c2_golden_identities_hold(caplog):
    evs, rows = _restore(golden_lines())
    res = jw("reconcile").check_identities(evs, rows)
    assert res == {"sell_done": 70, "sell_rows": 70, "buy_done": 75, "buy_rows": 75,
                   "unknown_reason_sells": 0, "ok": True}
    caplog.set_level(logging.DEBUG)
    assert jw("reconcile").emit_gap(res, logging.getLogger("jw.test")) is False
    assert _gap_records(caplog) == []


def test_c3_missing_accept_line_breaks_sell_identity(caplog):
    lines = [ln for ln in golden_lines()
             if "(주문번호: 0001638800, 전략: donchian_swing)" not in ln]  # 접수 줄 하나를 뺀다
    evs, rows = _restore(lines)
    res = jw("reconcile").check_identities(evs, rows)
    assert (res["sell_done"], res["sell_rows"], res["ok"]) == (70, 69, False)
    caplog.set_level(logging.DEBUG)
    assert jw("reconcile").emit_gap(res, logging.getLogger("jw.test")) is True
    (rec,) = _gap_records(caplog)
    assert "sell_done=70" in rec.getMessage() and "sell_rows=69" in rec.getMessage()


def test_c3b_unknown_reason_sell_breaks_identity():
    rows = [{"side": "SELL", "source": "fallback_inferred", "reason_code": None, "order_no": "1"}]
    evs = [{"kind": "order_done", "side": "SELL", "order_no": "1"}]
    res = jw("reconcile").check_identities(evs, rows)
    assert res["unknown_reason_sells"] == 1 and res["ok"] is False


def test_c4_external_rows_are_not_counted():
    evs = [{"kind": "order_done", "side": "BUY", "order_no": "1"}]
    rows = [{"side": "BUY", "source": "log_harvest", "reason_code": "ENTRY", "order_no": "1"},
            {"side": "BUY", "source": "external", "reason_code": None, "order_no": "9"},
            {"side": "SELL", "source": "unmatched", "reason_code": None, "order_no": "8"}]
    res = jw("reconcile").check_identities(evs, rows)
    assert (res["buy_done"], res["buy_rows"], res["sell_rows"], res["unknown_reason_sells"], res["ok"]) == (
        1, 1, 0, 0, True)


NOW = kst(2026, 10, 13, 12, 0, 0)


def _th(no, side, status, ts, strategy="kojiro"):
    return {"order_no": no, "trade_type": side, "strategy": strategy, "ticker": "005930",
            "timestamp": ts, "status": status, "price": 70000, "order_price": None}


def test_c5_external_only_for_filled_rows_not_in_journal():
    old = NOW - timedelta(minutes=10)
    trades = [
        _th("0000100100", "BUY", "COMPLETED", old),            # 일지에 있다 → 0
        _th("0000100200", "SELL", "COMPLETED", old),           # 일지 없음 + 접수 전문 있음 → external
        _th("0000100300", "BUY", "PARTIAL", old),              # 일지 없음 + 전문 없음 → unmatched
        _th("0000100400", "BUY", "PENDING", old),              # 미체결 → 0
        _th("0000100500", "BUY", "CANCELLED", old),            # 취소 → 0
    ]
    journal = {(old.date(), "0000100100", "BUY")}
    notices = {"0000100200", "0000042300"}                     # 0000042300 = trade_history 없는 미체결 외부
    rows = jw("reconcile").rows_from_trade_history(trades, journal, notices, now=NOW)
    got = {(r["order_no"], r["side"], r["source"]) for r in rows}
    assert got == {("0000100200", "SELL", "external"), ("0000100300", "BUY", "unmatched")}
    for r in rows:
        assert r["reason_code"] is None and r["strategy"] == "kojiro" and r["ticker"] == "005930"
        assert r["order_date"] == old.date() and r["noted_at"] == old


def test_c6_young_trade_rows_wait():
    young = NOW - timedelta(seconds=60)
    trades = [_th("0000100200", "SELL", "COMPLETED", young)]
    assert jw("reconcile").rows_from_trade_history(trades, set(), {"0000100200"}, now=NOW) == []
    assert jw("config").RECONCILE_MIN_AGE_SECONDS == 120


def test_c7_golden_external_notices_without_trade_rows_make_nothing():
    """음성 골든 — 09-28 HTS 외부 매수 접수 전문 5건은 trade_history 행이 없으니(미체결) 행 0."""
    p = jw("pairing").Pairer(source="log_restore")
    p.feed_events(parse_all(golden_lines()))
    p.drain(final=True)
    rows = jw("reconcile").rows_from_trade_history([], set(), p.external_notice_orders(),
                                                   now=kst(2026, 9, 28, 23, 0))
    assert rows == []


# ── cycle412 보완 Red — 결함 7(낮음): UTC 시각에서 날짜를 뽑음 · 대사 행 모양 ─────────
#
# asyncpg 는 TIMESTAMPTZ 를 UTC aware 로 돌려준다. KST 00:00~09:00 체결(08:00 NXT 프리장 포함)은 UTC 로
# 전날이라 `ts.date()` 가 하루 앞선 날짜를 만든다 → 일지 키와 안 맞아 같은 주문이 unmatched 로 한 번 더.
#
# | # | 계약 |
# |---|---|
# | C8 | 날짜 키·`order_date` 는 KST 날짜 · `noted_at` 은 KST aware |
# | C9 | 대사 행은 `insert_order` 가 쓰는 칸을 전부 갖는다(없는 값은 None) — 그대로 저장할 수 있다 |

from datetime import date, datetime, timezone  # noqa: E402

from jw_testkit import ORDER_KEYS  # noqa: E402

_UTC = timezone.utc
_PRE = datetime(2026, 10, 12, 23, 30, tzinfo=_UTC)   # = 2026-10-13 08:30 KST (NXT 프리장)


def test_c8_kst_date_for_utc_timestamp_already_in_journal():
    trades = [_th("0000100200", "SELL", "COMPLETED", _PRE)]
    journal = {(date(2026, 10, 13), "0000100200", "SELL")}
    assert jw("reconcile").rows_from_trade_history(trades, journal, set(), now=NOW) == []


def test_c8b_kst_date_and_kst_noted_at_for_new_row():
    (r,) = jw("reconcile").rows_from_trade_history([_th("0000100200", "SELL", "COMPLETED", _PRE)], set(), set(),
                                                   now=NOW)
    assert r["order_date"] == date(2026, 10, 13)
    assert r["noted_at"] == _PRE and r["noted_at"].utcoffset() == timedelta(hours=9)


def test_c9_reconcile_rows_have_every_insert_column():
    (r,) = jw("reconcile").rows_from_trade_history(
        [_th("0000100300", "BUY", "PARTIAL", NOW - timedelta(minutes=5))], set(), set(), now=NOW)
    missing = [k for k in ORDER_KEYS if k not in r]
    assert missing == [], f"대사 행에 insert_order 칸이 없다(KeyError 로 저장 실패): {missing}"
