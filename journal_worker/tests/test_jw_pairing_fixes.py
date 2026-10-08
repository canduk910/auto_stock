"""cycle412 보완 Red — 짝짓기 결함 2·4·5 (직전 판정 원문 번호 그대로).

| # | 결함 | 계약 |
|---|---|---|
| F2 | 2(중간) 매수 폴백 행·부모 없는 재주문 행의 전략 None → NOT NULL 위반으로 저장 실패 | 전략은 줄 → (재주문) 부모 → `trade_strategies[주문번호]`(trade_history) 순으로 채운다. 그래도 모르면 행을 버리지 않고 `strategy="unknown"` + `signal["strategy_src"]="unknown"`(채운 출처 표시: `trade_history`·`unknown`) · 047 NOT NULL 칸은 어떤 행에서도 None 이 아니다 |
| F4 | 4(중간) 가격 무관 청산(시간·목표·추세)에도 발동선에 손절선 | 사유 줄이 시간 청산·목표 익절·추세 종료면 `fired_line=None`(유효선 `effective_line` 은 그대로 스냅샷 값) |
| F5 | 5(중간) 가장 오래된 미사용 완료 줄을 고르고 정상 접수의 완료 줄에 사용 표시 안 함 | 접수·수동·매도 폴백 줄은 같은 주문번호 완료 줄을 「사용」으로 표시한다 · 폴백 매수·재주문은 같은 종목(재주문은 같은 수량) 미사용 완료 줄 중 **시각이 가장 가까운** 것 |
"""
from __future__ import annotations

import pytest

from jw_testkit import ORDER_NOT_NULL, golden_lines, jw, kst, log_line, parse_all

pytestmark = pytest.mark.unit

OE = "src.engine.order_engine"
D = "2026-10-13"


def L(hms, logger, msg, level="INFO"):
    return log_line(f"{D} {hms}", level, logger, msg)


def at(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return kst(2026, 10, 13, h, m, s)


def done(hms, side, ticker, qty, price, no):
    return L(hms, "src.api.order", f"{side} 주문 완료: {ticker} {qty}주 @ {price} (주문번호: {no})")


def buy_accept(hms, no, ticker="005930", qty=3, price=70000, sid="kojiro"):
    return L(hms, OE, f"매수 주문 접수: 삼성전자({ticker}) {qty}주 @ {price} (주문번호: {no}, 전략: {sid})")


def sell_accept(hms, signal, no, ticker="005930", qty=3, sid="kojiro"):
    return L(hms, OE, f"{signal} 매도 주문 접수: 삼성전자({ticker}) {qty}주 (주문번호: {no}, 전략: {sid})")


def buy_fallback(hms, ticker="005930", price=70500):
    return L(hms, OE, f"시장가 거부 → 지정가 5호가 폴백: 삼성전자({ticker}) @ {price} (원인 [APBK1943] 시장가 불가)",
             level="WARNING")


def sell_fallback(hms, no, ticker="005930", price=9150, sid="kojiro"):
    return L(hms, OE, f"매도 시장가 거부 → 지정가 5호가 폴백: 삼성전자({ticker}) @ {price} "
                      f"(원인 [APBK1943] 시장가 불가, 주문번호: {no}, 전략: {sid})", level="WARNING")


def manual(hms, no, ticker="005930", qty=2, sid="kojiro"):
    return L(hms, "src.routes.trading", f"수동 매도 주문 접수: 삼성전자({ticker}) {qty}주 (주문번호: {no}, 전략: {sid})")


def reorder(hms, qty, ticker="005930"):
    return L(hms, OE, f"손절 잔여 재주문: 삼성전자({ticker}) {qty}주")


def item(sid, ticker, *, stop, buy=10000):
    return {"strategy_id": sid, "ticker": ticker, "stop_price": stop, "stop_source": "effective",
            "target_price": None, "target_source": None, "buy_price": buy, "quantity": 3,
            "high_since_buy": buy, "buy_date": "2026-10-10", "order_no": "0000100000", "entry_atr": None,
            "kk_armed": None, "kk_arm_price": None}


def g1(items, when):
    return {"running": True, "as_of": when.isoformat(), "items": list(items)}


def run(*lines, trade_strategies=None, snapshots=()):
    p = jw("pairing").Pairer()
    for when, items in snapshots:
        p.feed_snapshot(None, g1(items, when), when)
    p.feed_events(parse_all(list(lines)))
    out = p.drain(trade_strategies=trade_strategies or {})
    later = p.drain(trade_strategies=trade_strategies or {})
    return out["orders"] + later["orders"], out["stops"] + later["stops"]


def by_no(rows):
    return {r["order_no"]: r for r in rows}


# ── F2 전략 빈칸 ──────────────────────────────────────────────────────────────

def test_f2a_buy_fallback_unknown_strategy_is_kept_as_unknown():
    rows, _ = run(done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"), buy_fallback("10:00:08"))
    (r,) = rows
    assert (r["order_no"], r["source"], r["side"]) == ("0000200700", "fallback_inferred", "BUY")
    assert r["strategy"] == "unknown", "모르면 행을 버리지 말고 'unknown' 으로 남긴다(047 NOT NULL 은 그대로)"
    assert r["signal"]["strategy_src"] == "unknown"


def test_f2b_buy_fallback_strategy_from_trade_history_is_marked():
    rows, _ = run(done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"), buy_fallback("10:00:08"),
                  trade_strategies={"0000200700": "kojiro"})
    (r,) = rows
    assert r["strategy"] == "kojiro" and r["signal"]["strategy_src"] == "trade_history"


def test_f2c_orphan_reorder_strategy_from_trade_history():
    """부모 매도 접수 줄이 이 워커 수명 밖(재시작 전·다른 청크)에 있으면 부모를 모른다."""
    rows, _ = run(done("10:00:40", "SELL", "005930", 2, 0, "0000300900"), reorder("10:00:40", 2),
                  trade_strategies={"0000300900": "kojiro"})
    (r,) = rows
    assert (r["order_no"], r["source"], r["parent_order_no"]) == ("0000300900", "reorder_inferred", None)
    assert r["strategy"] == "kojiro" and r["signal"]["strategy_src"] == "trade_history"


def test_f2d_orphan_reorder_without_any_strategy_is_unknown_not_dropped():
    rows, _ = run(done("10:00:40", "SELL", "005930", 2, 0, "0000300900"), reorder("10:00:40", 2))
    (r,) = rows
    assert r["strategy"] == "unknown" and r["signal"]["strategy_src"] == "unknown"
    assert r["source"] == "reorder_inferred"


def test_f2e_trade_history_does_not_override_strategy_from_the_line():
    rows, _ = run(done("10:00:08", "BUY", "005930", 3, 0, "0000200100"), buy_accept("10:00:08", "0000200100"),
                  trade_strategies={"0000200100": "momentum"})
    (r,) = rows
    assert r["strategy"] == "kojiro"


@pytest.mark.parametrize("case", ["synthetic", "golden"])
def test_f2f_not_null_columns_are_never_none(case):
    if case == "golden":
        p = jw("pairing").Pairer()
        p.feed_events(parse_all(golden_lines()))
        rows = p.drain(final=True)["orders"]
    else:
        rows, _ = run(done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"), buy_fallback("10:00:08"),
                      done("10:00:40", "SELL", "000660", 2, 0, "0000300900"), reorder("10:00:40", 2, "000660"),
                      done("10:01:00", "SELL", "035720", 1, 0, "0000301000"),
                      manual("10:01:00", "0000301000", ticker="035720", qty=1))
        assert len(rows) == 3
    bad = [(r["order_no"], k) for r in rows for k in ORDER_NOT_NULL if r.get(k) is None]
    assert bad == []


# ── F4 가격 무관 청산의 발동선 ────────────────────────────────────────────────

_NON_PRICE = [
    ("kojiro", "TREND_EXIT",
     "[kojiro_stage3_exit] 005930 스테이지3 진입 (추세 종료) judged_on=2026-10-13"),
    ("bull_flag_breakout", "TAKE_PROFIT",
     "눌림목 측정된 이동 도달: 005930 현재가(18640) ≥ 타겟(18640) — 익절 신호"),
    ("bull_flag_breakout", "TIME_EXIT",
     "눌림목 시간 청산: 005930 buy_date=2026-09-14 today=2026-10-13 보유일수 초과"),
    ("donchian_swing", "TIME_EXIT",
     "[donchian_time_exit] ticker=005930 reason=fail_n_days days_held=20 high=58000 target_1r=61000"),
    ("donchian_swing", "TIME_EXIT",
     "도치안 시간 기반 청산: 005930 보유 5영업일 ≥ 2, 현재가(35550) < 돌파선(35600)"),
]


@pytest.mark.parametrize("sid,signal,reason", _NON_PRICE,
                         ids=["stage3", "measured_target", "bfb_time", "donchian_time", "donchian_time_legacy"])
def test_f4_non_price_exit_has_no_fired_line(sid, signal, reason):
    rows, stops = run(L("10:00:05", f"src.engine.strategies.{sid}", reason),
                      done("10:00:06", "SELL", "005930", 3, 0, "0000300100"),
                      sell_accept("10:00:06", signal, "0000300100", sid=sid),
                      snapshots=[(at("10:00:00"), [item(sid, "005930", stop=9500)])])
    (r,) = rows
    assert r["reason_code"] == signal and r["signal"]["reason_line"] is not None
    assert r["fired_line"] is None, f"가격 무관 청산({signal})의 발동선은 빈칸 — 손절선({r['fired_line']})이 아니다"
    assert r["effective_line"] == 9500  # 청산 순간 손절선(유효선)은 그대로 남긴다


def test_f4b_price_exit_without_line_still_uses_snapshot_stop():
    """경계 — 선·임계가 없는 가격 손절(BFB 눌림목)은 여전히 스냅샷 손절선이 발동선이다."""
    rows, _ = run(L("10:00:05", "src.engine.strategies.bull_flag_breakout", "눌림목 손절: 005930 매수가(10000) 대비 -5.1%"),
                  done("10:00:06", "SELL", "005930", 3, 0, "0000300100"),
                  sell_accept("10:00:06", "STOP_LOSS", "0000300100", sid="bull_flag_breakout"),
                  snapshots=[(at("10:00:00"), [item("bull_flag_breakout", "005930", stop=9520)])])
    assert rows[0]["fired_line"] == 9520


# ── F5 완료 줄 고르기 ─────────────────────────────────────────────────────────

def test_f5a_buy_fallback_picks_nearest_done_not_oldest():
    rows, _ = run(done("09:00:00", "BUY", "005930", 1, 0, "0000200050"),      # 짝 없는 옛 완료 줄
                  done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"), buy_fallback("10:00:08"))
    assert [r["order_no"] for r in rows] == ["0000200700"]


def test_f5b_normal_buy_accept_consumes_its_done_line():
    rows, _ = run(done("09:30:00", "BUY", "005930", 3, 0, "0000200100"), buy_accept("09:30:00", "0000200100"),
                  done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"), buy_fallback("10:00:08"),
                  trade_strategies={"0000200700": "kojiro"})
    got = by_no(rows)
    assert set(got) == {"0000200100", "0000200700"}, "폴백 행이 앞선 정상 매수의 주문번호를 가로챘다"
    assert got["0000200700"]["source"] == "fallback_inferred"
    assert got["0000200100"]["source"] == "log_harvest"


@pytest.mark.parametrize("parent_kind", ["accept", "manual", "sell_fallback"])
def test_f5c_reorder_does_not_steal_parent_done_line(parent_kind):
    parent = {
        "accept": [done("10:00:06", "SELL", "005930", 2, 0, "0000300100"),
                   sell_accept("10:00:06", "STOP_LOSS", "0000300100", qty=2)],
        "manual": [done("10:00:06", "SELL", "005930", 2, 0, "0000300100"), manual("10:00:06", "0000300100")],
        "sell_fallback": [done("10:00:06", "SELL", "005930", 2, 9150, "0000300100"),
                          sell_fallback("10:00:06", "0000300100")],
    }[parent_kind]
    rows, _ = run(L("10:00:05", "src.engine.strategies.kojiro",
                    "[kojiro_hard_stop] 005930 매수가(10000) 대비 -8.1% ≤ -8.0%"),
                  *parent,
                  done("10:00:40", "SELL", "005930", 2, 0, "0000300900"), reorder("10:00:40", 2),
                  trade_strategies={"0000300900": "kojiro"})
    got = by_no(rows)
    assert set(got) == {"0000300100", "0000300900"}, (
        f"재주문 행이 부모({parent_kind}) 완료 줄의 주문번호를 가로챘다: {sorted(got)}")
    assert got["0000300900"]["source"] == "reorder_inferred"


def test_f5d_reorder_picks_nearest_same_qty_done():
    rows, _ = run(done("09:10:00", "SELL", "005930", 2, 0, "0000300050"),      # 짝 없는 옛 완료 줄(같은 수량)
                  done("10:00:40", "SELL", "005930", 2, 0, "0000300900"), reorder("10:00:40", 2),
                  trade_strategies={"0000300900": "kojiro", "0000300050": "kojiro"})
    assert [r["order_no"] for r in rows] == ["0000300900"]
