"""cycle412 Red — 짝짓기 규칙(실시간 모드, 합성 줄). 설계 관찰자안 2절 ⑧·판단가·청산 순간 손절선, 3절 세부 규칙.

합성 줄은 생산 쪽 포맷 문자열(`test_cycle412_log_phrase_pins.py` 가 고정)로 만든 것이다 —
폴백·재주문·수동·종목상태 매도는 이 기간 실측 표본이 0건이라(설계 8절 한계 5) 여기서만 덮는다.

| # | 계약 |
|---|---|
| Q1 | 한 회전 보류 — 앵커를 먹은 회전의 `drain()` 은 비고, 다음 `drain()` 에서 나온다 |
| Q2 | 링 짝 = 같은 (전략, 종목) 중 신호 시각 ≤ 접수 시각인 마지막 것 · 이후 신호는 안 쓴다 |
| Q3 | 링 TTL 은 신호 시각 기준 600초 |
| Q4 | 보류 회전 사이에 들어온 링 신호를 쓴다 · 그래도 없으면 5초 안 로그 신호 줄 → `log_only` · 그것도 없으면 `none` |
| Q5 | 유효선 = 접수 시각 이전 마지막 스냅샷 + `snapshot_age_s` · `exit` 사건 · 스냅샷 없으면 빈칸 |
| Q6 | LTV 발동선 = 스냅샷 파라미터(모드별) · BFB 눌림목 발동선 = 스냅샷 손절선 |
| Q7 | 보류 중 도착한 `[order_notice]` 가 주문구분을 채운다 |
| Q8 | 경로 — 수동(`manual_api`) · 매도 폴백 · 재주문 · 매수 폴백(`fallback_inferred`/`reorder_inferred`) |
| Q9 | 사유 줄은 같은 전략 로거 · 10초 안 · 가격·전략 청산에만 / 종목상태 사유 |
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from jw_testkit import jw, kst, log_line, parse_all

pytestmark = pytest.mark.unit

OE = "src.engine.order_engine"
D = "2026-10-13"


def L(hms, logger, msg, level="INFO"):
    return log_line(f"{D} {hms}", level, logger, msg)


def at(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return kst(2026, 10, 13, h, m, s)


def g0(strategies=None, *, running=True, phase="main_trading"):
    return {"running": running, "phase": phase, "positions_detail": {}, "strategies": strategies or {}}


def strat(*, signals=(), params=None, enabled=True, tickers=()):
    return {"enabled": enabled, "params": dict(params or {}), "buy_signals": list(signals),
            "position_tickers": list(tickers)}


def item(sid, ticker, *, stop=None, source="effective", buy=10000, qty=3, high=10000, target=None,
         target_source=None, entry_atr=None, kk_armed=None, kk_arm_price=None, order_no="0000100000",
         buy_date="2026-10-10"):
    return {"strategy_id": sid, "ticker": ticker, "stop_price": stop, "stop_source": source,
            "target_price": target, "target_source": target_source, "buy_price": buy, "quantity": qty,
            "high_since_buy": high, "buy_date": buy_date, "order_no": order_no, "entry_atr": entry_atr,
            "kk_armed": kk_armed, "kk_arm_price": kk_arm_price}


def g1(items, as_of):
    return {"running": True, "as_of": as_of.isoformat(), "items": list(items)}


def buy_accept(hms, ticker="005930", name="삼성전자", qty=3, price=70000, no="0000200100", sid="kojiro"):
    return L(hms, OE, f"매수 주문 접수: {name}({ticker}) {qty}주 @ {price} (주문번호: {no}, 전략: {sid})")


def sell_accept(hms, signal, ticker="005930", name="삼성전자", qty=3, no="0000300100", sid="kojiro"):
    return L(hms, OE, f"{signal} 매도 주문 접수: {name}({ticker}) {qty}주 (주문번호: {no}, 전략: {sid})")


def done(hms, side, ticker, qty, price, no):
    return L(hms, "src.api.order", f"{side} 주문 완료: {ticker} {qty}주 @ {price} (주문번호: {no})")


def notice(hms, no, side, kind, ticker="005930"):
    return L(hms, "src.realtime.handler",
             f"[order_notice] order_no={no} orig_order_no= side={side} rctf=0 kind={kind} cond=0 "
             f"ticker={ticker} qty=0000000003 price=000000000 hour=100008 rfus=0 acpt=1 ord_qty=000000003")


def P(**kw):
    return jw("pairing").Pairer(**kw)


def feed(p, *lines):
    p.feed_events(parse_all(list(lines)))


def only(rows, side):
    rs = [r for r in rows["orders"] if r["side"] == side]
    assert len(rs) == 1, rows
    return rs[0]


# ── Q1 한 회전 보류 ───────────────────────────────────────────────────────────

def test_q1_rows_are_held_for_one_rotation():
    p = P()
    feed(p, done("10:00:08", "BUY", "005930", 3, 0, "0000200100"), buy_accept("10:00:08"))
    assert p.drain()["orders"] == []
    second = p.drain()
    assert len(second["orders"]) == 1 and second["orders"][0]["source"] == "log_harvest"
    assert second["orders"][0]["signal"]["path"] == "accept"
    assert p.drain()["orders"] == []  # 한 번만 나간다


# ── Q2·Q3 링 ─────────────────────────────────────────────────────────────────

def test_q2_ring_picks_last_signal_not_after_order():
    p = P()
    sigs = [{"ticker": "005930", "price": 69900, "time": "10:00:03"},
            {"ticker": "005930", "price": 70000, "time": "10:00:08"},
            {"ticker": "005930", "price": 70300, "time": "10:00:09"},   # 접수 뒤 — 쓰지 않는다
            {"ticker": "000660", "price": 1, "time": "10:00:08"}]       # 다른 종목
    p.feed_snapshot(g0({"kojiro": strat(signals=sigs, params={"hard_stop_pct": -8.0})}), None, at("10:00:10"))
    feed(p, buy_accept("10:00:08"))
    p.drain()
    r = only(p.drain(), "BUY")
    assert r["judge_price"] == 70000 and r["order_price"] == 70000
    assert r["signal"]["signal_src"] == "ring" and r["signal"]["time"] == "10:00:08"
    assert r["params"] == {"hard_stop_pct": -8.0}
    assert r["reason_code"] == "ENTRY" and r["strategy"] == "kojiro"


def test_q2b_ring_ignores_other_strategy():
    p = P()
    p.feed_snapshot(g0({"donchian_swing": strat(signals=[{"ticker": "005930", "price": 1, "time": "10:00:08"}])}),
                    None, at("10:00:10"))
    feed(p, buy_accept("10:00:08"))
    p.drain()
    assert only(p.drain(), "BUY")["signal"]["signal_src"] == "none"


def test_q3_ring_ttl_is_by_signal_time():
    p = P()
    old = {"ticker": "005930", "price": 65000, "time": "09:59:58"}
    p.feed_snapshot(g0({"kojiro": strat(signals=[old])}), None, at("10:00:00"))
    # G0 는 같은 신호를 계속 돌려준다 — 신호 시각 기준 600초가 지나면 링에서 빠져야 한다
    p.feed_snapshot(g0({"kojiro": strat(signals=[old])}), None, at("10:10:30"))
    feed(p, buy_accept("10:10:31"))
    p.drain()
    p.feed_snapshot(g0({"kojiro": strat(signals=[old])}), None, at("10:10:45"))
    r = only(p.drain(), "BUY")
    assert r["signal"]["signal_src"] == "none" and r["judge_price"] is None


# ── Q4 기다림과 「로그만」 ────────────────────────────────────────────────────

def test_q4_signal_arriving_in_next_rotation_is_used():
    p = P()
    feed(p, buy_accept("10:00:08"))
    assert p.drain()["orders"] == []
    p.feed_snapshot(g0({"kojiro": strat(signals=[{"ticker": "005930", "price": 70000, "time": "10:00:08"}])}),
                    None, at("10:00:20"))
    assert only(p.drain(), "BUY")["signal"]["signal_src"] == "ring"


def test_q4b_log_only_when_ring_missing_after_wait():
    p = P()
    feed(p, L("10:00:07", "src.engine.strategies.kojiro",
              "고지로 매수 신호: 삼성전자(005930) 현재가(70000) — 스테이지1(6→1) + EMA정배열 + ATR(1200.0)"),
         buy_accept("10:00:08"))
    p.drain()
    r = only(p.drain(), "BUY")
    assert r["signal"]["signal_src"] == "log_only"
    assert r["judge_price"] == 70000 and r["params"] is None


def test_q4c_log_signal_older_than_window_is_not_used():
    p = P()
    feed(p, L("10:00:01", "src.engine.strategies.kojiro",
              "고지로 매수 신호: 삼성전자(005930) 현재가(70000) — 스테이지1(6→1) + EMA정배열 + ATR(1200.0)"),
         buy_accept("10:00:08"))  # 7초 전 신호 줄 — 5초 창 밖
    p.drain()
    assert only(p.drain(), "BUY")["signal"]["signal_src"] == "none"


def test_q4d_final_drain_emits_without_waiting():
    p = P(source="log_restore")
    feed(p, buy_accept("10:00:08"))
    r = only(p.drain(final=True), "BUY")
    assert r["source"] == "log_restore" and r["signal"]["path"] == "accept"


# ── Q5 유효선·exit 사건 ───────────────────────────────────────────────────────

def test_q5_effective_line_from_last_snapshot_before_accept():
    p = P()
    p.feed_snapshot(None, g1([item("kojiro", "005930", stop=9500, buy=10000)], at("10:00:00")), at("10:00:00"))
    p.feed_snapshot(None, g1([item("kojiro", "005930", stop=9600, buy=10000)], at("10:00:15")), at("10:00:15"))
    feed(p, L("10:00:09", "src.engine.strategies.kojiro",
              "[kojiro_hard_stop] 삼성전자(005930) 매수가(10000) 대비 -8.1% ≤ -8.0%"),
         sell_accept("10:00:10", "STOP_LOSS"))
    p.drain()
    out = p.drain()
    r = only(out, "SELL")
    assert r["effective_line"] == 9500
    assert r["signal"]["snapshot_age_s"] == 10 and r["signal"]["stop_kind"] == "effective"
    assert r["fired_line"] == round(10000 * (1 + -8.0 / 100))
    (ev,) = out["stops"]
    assert (ev["event"], ev["strategy"], ev["ticker"], ev["stop_price"]) == ("exit", "kojiro", "005930", 9500)
    assert ev["inputs"]["snapshot_age_s"] == 10 and ev["inputs"]["sell_order_no"] == "0000300100"


def test_q5b_no_snapshot_before_accept_means_blank():
    p = P()
    p.feed_snapshot(None, g1([item("kojiro", "005930", stop=9600)], at("10:00:15")), at("10:00:15"))
    feed(p, sell_accept("10:00:10", "FORCE_CLEAR"))
    p.drain()
    out = p.drain()
    r = only(out, "SELL")
    assert r["effective_line"] is None and r["fired_line"] is None
    assert out["stops"] == []


# ── Q6 스냅샷으로 계산하는 발동선 ─────────────────────────────────────────────

def test_q6_ltv_fired_line_from_snapshot_params_by_mode():
    p = P()
    params = {"intraday_stop_loss": -5.0, "overnight_stop_loss": -3.5}
    p.feed_snapshot(g0({"long_tail_volatility": strat(params=params)}),
                    g1([item("long_tail_volatility", "005930", stop=None, source="mode_dependent", buy=10000)],
                       at("10:00:00")), at("10:00:00"))
    feed(p, L("10:00:05", "src.engine.strategies.long_tail_volatility",
              "롱테일VB 손절(상한가 모드): 삼성전자(005930) -3.6%"),
         sell_accept("10:00:05", "STOP_LOSS", sid="long_tail_volatility"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert r["fired_line"] == round(10000 * (1 + -3.5 / 100))
    assert r["judge_price"] == round(10000 * (1 + -3.6 / 100)) and r["signal"]["judge_src"] == "log_pct"
    assert r["signal"]["mode"] == "limit_up"


def test_q6b_pullback_fired_line_is_snapshot_stop():
    p = P()
    p.feed_snapshot(None, g1([item("bull_flag_breakout", "005930", stop=9520, buy=10000)], at("10:00:00")),
                    at("10:00:00"))
    feed(p, L("10:00:05", "src.engine.strategies.bull_flag_breakout", "눌림목 손절: 005930 매수가(10000) 대비 -5.1%"),
         sell_accept("10:00:05", "STOP_LOSS", sid="bull_flag_breakout"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert r["fired_line"] == 9520 and r["judge_price"] == round(10000 * (1 + -5.1 / 100))


# ── Q7 주문구분 ───────────────────────────────────────────────────────────────

def test_q7_notice_arriving_next_rotation_fills_division():
    p = P()
    feed(p, done("10:00:08", "SELL", "005930", 3, 0, "0000300100"), sell_accept("10:00:08", "FORCE_CLEAR"))
    assert p.drain()["orders"] == []
    feed(p, notice("10:00:08", "0000300100", "SELL", "01"))
    assert only(p.drain(), "SELL")["order_division"] == "01"


# ── Q8 경로 ──────────────────────────────────────────────────────────────────

def test_q8_manual_sell_row():
    p = P()
    feed(p, done("10:00:08", "SELL", "005930", 3, 0, "0000300100"),
         L("10:00:08", "src.routes.trading",
           "수동 매도 주문 접수: 삼성전자(005930) 3주 (주문번호: 0000300100, 전략: kojiro)"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert (r["source"], r["reason_code"], r["strategy"]) == ("manual_api", "MANUAL", "kojiro")
    assert r["signal"]["path"] == "manual"


def test_q8b_sell_fallback_joined_with_reason_line():
    p = P()
    feed(p, L("10:00:05", "src.engine.strategies.kojiro",
              "[kojiro_atr_stop] 005930 손절선(9200) = 매수가(10000) - 2.0×ATR(400.0)"),
         done("10:00:06", "SELL", "005930", 3, 9150, "0000300200"),
         L("10:00:06", OE, "매도 시장가 거부 → 지정가 5호가 폴백: 삼성전자(005930) @ 9150 "
                           "(원인 [APBK1943] 시장가 불가, 주문번호: 0000300200, 전략: kojiro)", level="WARNING"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert (r["source"], r["order_no"], r["reason_code"], r["fired_line"]) == (
        "fallback_inferred", "0000300200", "STOP_LOSS", 9200)
    assert r["order_price"] == 9150 and r["signal"]["path"] == "fallback"


def test_q8c_reorder_inherits_parent():
    p = P()
    feed(p, L("10:00:05", "src.engine.strategies.kojiro",
              "[kojiro_hard_stop] 005930 매수가(10000) 대비 -8.1% ≤ -8.0%"),
         done("10:00:06", "SELL", "005930", 5, 0, "0000300100"),
         sell_accept("10:00:06", "STOP_LOSS", qty=5, no="0000300100"),
         done("10:00:40", "SELL", "005930", 2, 0, "0000300900"),
         L("10:00:40", OE, "손절 잔여 재주문: 삼성전자(005930) 2주"))
    p.drain()
    out = p.drain()
    rows = {r["order_no"]: r for r in out["orders"]}
    assert set(rows) == {"0000300100", "0000300900"}
    child = rows["0000300900"]
    assert (child["source"], child["parent_order_no"], child["reason_code"], child["strategy"]) == (
        "reorder_inferred", "0000300100", "STOP_LOSS", "kojiro")
    assert child["signal"]["path"] == "reorder"


def test_q8d_buy_fallback_strategy_from_trade_history():
    p = P()
    feed(p, done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"),
         L("10:00:08", OE, "시장가 거부 → 지정가 5호가 폴백: 삼성전자(005930) @ 70500 (원인 [APBK1943] 시장가 불가)",
           level="WARNING"))
    p.drain(trade_strategies={"0000200700": "kojiro"})
    r = only(p.drain(trade_strategies={"0000200700": "kojiro"}), "BUY")
    assert (r["source"], r["strategy"], r["order_no"], r["reason_code"]) == (
        "fallback_inferred", "kojiro", "0000200700", "ENTRY")
    assert r["signal"]["path"] == "fallback"


def test_q8e_done_line_alone_makes_no_row():
    p = P()
    feed(p, done("10:00:08", "SELL", "005930", 3, 0, "0000300100"))
    p.drain()
    assert p.drain()["orders"] == []


# ── Q9 사유 줄 범위 ───────────────────────────────────────────────────────────

def test_q9_reason_line_from_other_strategy_is_ignored():
    p = P()
    feed(p, L("10:00:05", "src.engine.strategies.kojiro",
              "[kojiro_hard_stop] 005930 매수가(10000) 대비 -8.1% ≤ -8.0%"),
         sell_accept("10:00:06", "STOP_LOSS", sid="donchian_swing"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert r["reason_code"] == "STOP_LOSS" and r["signal"]["reason_line"] is None and r["fired_line"] is None


def test_q9b_reason_line_older_than_10s_is_ignored():
    p = P()
    feed(p, L("10:00:00", "src.engine.strategies.kojiro",
              "[kojiro_stage3_exit] 005930 스테이지3 진입 (추세 종료) judged_on=2026-10-13"),
         sell_accept("10:00:11", "TRAILING_STOP"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert r["reason_code"] == "TRAILING_STOP" and r["signal"]["reason_line"] is None


def test_q9c_time_based_signal_ignores_stray_reason_line():
    p = P()
    feed(p, L("10:00:05", "src.engine.strategies.kojiro",
              "[kojiro_hard_stop] 005930 매수가(10000) 대비 -8.1% ≤ -8.0%"),
         sell_accept("10:00:06", "FORCE_CLEAR"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert r["reason_code"] == "FORCE_CLEAR" and r["fired_line"] is None


def test_q9d_status_exit_reason_sub():
    p = P()
    feed(p, L("10:00:05", "src.engine.status_exit_watch",
              "[status_exit_fire] ticker=005930 strategy=kojiro reason=short_over iscd=59 mang=N short_over=Y "
              "qty=3 mode=enforce attempt=1 bought_today=0", level="WARNING"),
         sell_accept("10:00:05", "STATUS_EXIT"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert (r["reason_code"], r["reason_sub"]) == ("STATUS_EXIT", "short_over")


def test_q9e_noted_at_and_order_date_from_anchor_line():
    p = P()
    feed(p, sell_accept("10:00:06", "FORCE_CLEAR"))
    p.drain()
    r = only(p.drain(), "SELL")
    assert r["noted_at"] == at("10:00:06") and r["order_date"] == at("10:00:06").date()
    assert r["noted_at"].utcoffset() == timedelta(hours=9)
