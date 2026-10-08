"""cycle412 Red — 로그 문법 골든(설계 관찰자안 3절 「파서」·6절 「문법 골든 테스트」).

픽스처 = EC2 로그 사본(2026-09-17~10-07)에서 필요한 로거 줄만 뽑은 것(민감값 0 — I8).
설계 실측: 매도 접수 70 · 매수 접수 75 · `SELL 주문 완료` 70 · `BUY 주문 완료` 75 ·
익일청산 보류 11(갭 4 · KRX 전용 7 · NXT 시가 미수신 0) · `[order_notice]` 93.

| # | 계약 |
|---|---|
| G1 | 골든 종류별 개수가 실측과 같다 |
| G2 | 종목 표기 두 꼴(`이름(코드)`·`코드`) · 코드는 끝에서 읽는다(`인제니아테라퓨틱스(Reg.S)(950260)`) · 이름의 공백 |
| G3 | 「수동 매도 주문 접수」는 **로거 이름**으로 가른다 — 같은 문구가 `<신호> 매도 주문 접수` 꼴에 겹친다 |
| G4 | 익일청산 보류 3문구 → `krx_only`·`nxt_open_missing`·`gap_below`(갭·임계 숫자) |
| G5 | 다른 로거·다른 접두·`[order_rejected_notice]`·websockets 잡음 = None |
| G6 | 사유 16문구 · 매수 신호 7문구 · `[order_notice]` 칸 |
| G7 | 시각은 KST aware |
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

import pytest

from jw_testkit import golden_lines, jw, kst, log_line, parse_all

pytestmark = pytest.mark.unit

OE = "src.engine.order_engine"


def _one(line: str) -> dict:
    ev = jw("grammar").parse_line(line)
    assert ev is not None, line
    return ev


# ── G1 골든 개수 ──────────────────────────────────────────────────────────────

def test_g1_golden_kind_counts_match_measurement():
    evs = parse_all(golden_lines())
    c = Counter(e["kind"] for e in evs)
    assert c["sell_accept"] == 70
    assert c["buy_accept"] == 75
    assert Counter(e["side"] for e in evs if e["kind"] == "order_done") == {"SELL": 70, "BUY": 75}
    assert c["order_notice"] == 93
    assert c["ndc_defer"] == 11
    assert c["manual_sell_accept"] == 0 and c["sell_fallback"] == 0 and c["buy_fallback"] == 0
    assert c["reorder"] == 0 and c["status_exit_fire"] == 0


def test_g1b_golden_ndc_subtypes():
    evs = [e for e in parse_all(golden_lines()) if e["kind"] == "ndc_defer"]
    assert Counter(e["reason_sub"] for e in evs) == {"krx_only": 7, "gap_below": 4}
    gaps = sorted((e["ticker"], e["gap"], e["threshold"]) for e in evs if e["reason_sub"] == "gap_below")
    assert gaps == [("007810", -2.8, 10.0), ("047920", 3.9, 10.0), ("394800", 2.7, 10.0),
                    ("486990", 8.1, 10.0)]
    assert all(e["strategy"] == "momentum" for e in evs)


def test_g1c_golden_exit_reason_phrases():
    evs = [e for e in parse_all(golden_lines()) if e["kind"] == "exit_reason"]
    c = Counter(e["phrase"] for e in evs)
    assert c["momentum_stop"] == 4 and c["vb_stop"] == 2 and c["kojiro_trailing"] == 2
    assert c["kojiro_atr_stop"] == 3 and c["kojiro_hard_stop"] == 2 and c["bfb_turtle_backstop"] == 2
    assert c["bfb_pullback_stop"] == 4 and c["ltv_intraday_stop"] == 5
    assert c["donchian_trailing_legacy"] == 2 and c["donchian_time_exit_legacy"] == 3
    assert c["bfb_time_exit"] == 2 and c["kojiro_stage3_exit"] == 1 and c["bfb_measured_target"] == 1


def test_g1d_golden_buy_signal_lines_cover_every_buy():
    evs = parse_all(golden_lines())
    sigs = [e for e in evs if e["kind"] == "buy_signal"]
    buys = [e for e in evs if e["kind"] == "buy_accept"]
    for b in buys:
        near = [s for s in sigs if s["strategy"] == b["strategy"] and s["ticker"] == b["ticker"]
                and timedelta(0) <= b["ts"] - s["ts"] <= timedelta(seconds=1)]
        assert near, f"매수 {b['order_no']} 의 신호 줄이 1초 안에 없다"
    deltas = Counter(
        int((b["ts"] - max(s["ts"] for s in sigs if s["strategy"] == b["strategy"]
                           and s["ticker"] == b["ticker"] and s["ts"] <= b["ts"])).total_seconds())
        for b in buys
    )
    assert deltas == {0: 49, 1: 26}


# ── G2 종목 표기 ──────────────────────────────────────────────────────────────

def test_g2_name_with_parentheses_reads_code_from_end():
    e = _one(log_line("2026-09-22 14:29:17", "INFO", OE,
                      "매수 주문 접수: 인제니아테라퓨틱스(Reg.S)(950260) 2주 @ 23350 "
                      "(주문번호: 0001614400, 전략: long_tail_volatility)"))
    assert e["kind"] == "buy_accept"
    assert (e["ticker"], e["name"]) == ("950260", "인제니아테라퓨틱스(Reg.S)")
    assert (e["qty"], e["price"], e["order_no"], e["strategy"]) == (2, 23350, "0001614400",
                                                                   "long_tail_volatility")


def test_g2b_code_only_form():
    e = _one(log_line("2026-09-21 10:49:04", "INFO", "src.engine.strategies.kojiro",
                      "[kojiro_atr_stop] 004690 손절선(130000) = 매수가(130000) - 2.0×ATR(3628.5)"))
    assert (e["ticker"], e["name"]) == ("004690", None)
    e2 = _one(log_line("2026-09-21 10:49:04", "INFO", OE,
                       "STOP_LOSS 매도 주문 접수: 004690 1주 (주문번호: 0000788000, 전략: kojiro)"))
    assert (e2["kind"], e2["ticker"], e2["name"], e2["signal"]) == ("sell_accept", "004690", None,
                                                                    "STOP_LOSS")


def test_g2c_name_with_space():
    e = _one(log_line("2026-10-01 09:44:18", "INFO", OE,
                      "STOP_LOSS 매도 주문 접수: CJ ENM(035760) 5주 (주문번호: 0000501000, 전략: kojiro)"))
    assert (e["ticker"], e["name"], e["qty"]) == ("035760", "CJ ENM", 5)


def test_g2d_golden_reg_s_name_both_lines():
    evs = [e for e in parse_all(golden_lines()) if e.get("ticker") == "950260"
           and e["kind"] in ("buy_accept", "sell_accept")]
    assert {e["kind"] for e in evs} == {"buy_accept", "sell_accept"}
    assert all(e["name"] == "인제니아테라퓨틱스(Reg.S)" for e in evs)


# ── G3 수동 매도 로거 구분 ─────────────────────────────────────────────────────

def test_g3_manual_sell_is_routes_logger_only():
    msg = "수동 매도 주문 접수: 삼성전자(005930) 3주 (주문번호: 0000123400, 전략: kojiro)"
    e = _one(log_line("2026-10-13 10:00:00", "INFO", "src.routes.trading", msg))
    assert e["kind"] == "manual_sell_accept"
    assert (e["ticker"], e["qty"], e["order_no"], e["strategy"]) == ("005930", 3, "0000123400", "kojiro")
    # 휴식 컷 꼬리표가 붙어도 같다
    e2 = _one(log_line("2026-10-13 15:40:00", "INFO", "src.routes.trading",
                       msg + " [market_rest_manual_exempt]"))
    assert e2["kind"] == "manual_sell_accept" and e2["order_no"] == "0000123400"
    # 신호 이름 자리에 「수동」을 읽은 sell_accept 가 되면 안 된다
    assert e["kind"] != "sell_accept" and "signal" not in e


def test_g3b_same_text_from_other_logger_is_not_manual():
    msg = "수동 매도 주문 접수: 삼성전자(005930) 3주 (주문번호: 0000123400, 전략: kojiro)"
    assert jw("grammar").parse_line(log_line("2026-10-13 10:00:00", "INFO", OE, msg)) is None


# ── G4 익일청산 보류 3문구 ───────────────────────────────────────────────────

@pytest.mark.parametrize("level,msg,sub,gap,th", [
    ("INFO", "stock_master nxt_tradable=False — 익일 청산 보류 (09:00 KRX 시장가 청산 예약): "
             "우리넷(115440) (전략: momentum)", "krx_only", None, None),
    ("WARNING", "NXT 시가 미수신 — 익일 청산 보류 (KRX 시가 확정 후 재시도): 우리넷(115440) (전략: momentum)",
     "nxt_open_missing", None, None),
    ("INFO", "익일 청산 보류 (갭 -2.8% < 임계 10.0%, 09:00 KRX 시장가 청산 예약): 우리넷(115440) "
             "(전략: momentum)", "gap_below", -2.8, 10.0),
])
def test_g4_ndc_defer_three_phrases(level, msg, sub, gap, th):
    e = _one(log_line("2026-09-28 08:00:30", level, "src.engine.scheduler", msg))
    assert e["kind"] == "ndc_defer"
    assert (e["ticker"], e["strategy"], e["reason_sub"], e["gap"], e["threshold"]) == (
        "115440", "momentum", sub, gap, th)


def test_g4b_write_log_variant_is_not_a_defer_line():
    """`write_log` 가 DB 로 쓰는 짧은 문구는 파일 로그의 scheduler 줄이 아니다 — 다른 로거면 None."""
    msg = "익일 청산 보류 (갭 -2.8% < 임계): 우리넷(115440) (momentum)"
    assert jw("grammar").parse_line(log_line("2026-09-28 08:00:30", "INFO", "src.engine.scheduler",
                                             msg)) is None


# ── G5 잡음 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    log_line("2026-10-07 07:47:10", "DEBUG", "websockets.client", "< TEXT '{\"header\":{}}' [37 bytes]"),
    log_line("2026-09-29 16:02:21", "INFO", OE,
             "[after_exit_division] ticker=030530 div=44 unpr=0 cur=26650 exchange=KRX dial=44"),
    log_line("2026-09-17 09:30:45", "DEBUG", "src.realtime.handler",
             "체결통보 접수(미체결): order_no=0000451100, ticker=047050"),
    log_line("2026-09-28 08:08:33", "WARNING", "src.realtime.handler",
             "[order_rejected_notice] order_no=0000042300 orig_order_no= side=BUY rctf=0 kind=00 cond=3 "
             "ticker=199800 qty=0000000001 price=000023650 hour=080833 rfus=1 acpt=1 ord_qty=000000001"),
    log_line("2026-09-17 09:30:45", "INFO", "src.engine.boot_manager",
             "매수 주문 접수: 포스코인터내셔널(047050) 1주 @ 58800 (주문번호: 0000451100, 전략: long_tail_volatility)"),
    log_line("2026-09-17 09:30:45", "INFO", "src.engine.strategies.kojiro",
             "[days_held_observe] ticker=095340 strategy=donchian_swing buy_date=2026-09-23"),
    "그냥 한 줄",
    "",
])
def test_g5_noise_is_none(line):
    assert jw("grammar").parse_line(line) is None


# ── G6 개별 문법 ─────────────────────────────────────────────────────────────

def test_g6_order_notice_fields():
    e = _one(log_line("2026-09-28 09:12:16", "INFO", "src.realtime.handler",
                      "[order_notice] order_no=0000345900 orig_order_no=0000340300 side=BUY rctf=2 kind=00 "
                      "cond=0 ticker=199800 qty=0000000001 price=000000000 hour=091216 rfus=0 acpt=2 "
                      "ord_qty=000000001"))
    assert e["kind"] == "order_notice"
    assert (e["order_no"], e["orig_order_no"], e["side"], e["rctf"], e["division"], e["ticker"],
            e["qty"], e["price"], e["acpt"]) == ("0000345900", "0000340300", "BUY", "2", "00", "199800",
                                                 1, 0, "2")
    e2 = _one(log_line("2026-09-29 16:02:21", "INFO", "src.realtime.handler",
                       "[order_notice] order_no=0001638800 orig_order_no= side=SELL rctf=0 kind=44 cond=0 "
                       "ticker=030530 qty=0000000001 price=000000000 hour=160221 rfus=0 acpt=1 "
                       "ord_qty=000000001"))
    assert e2["orig_order_no"] is None and e2["division"] == "44" and e2["side"] == "SELL"


def test_g6b_order_done_both_sides():
    e = _one(log_line("2026-09-29 16:02:21", "INFO", "src.api.order",
                      "SELL 주문 완료: 030530 1주 @ 0 (주문번호: 0001638800)"))
    assert (e["kind"], e["side"], e["ticker"], e["qty"], e["price"], e["order_no"]) == (
        "order_done", "SELL", "030530", 1, 0, "0001638800")


def test_g6c_fallbacks_and_reorder():
    g = jw("grammar")
    b = g.parse_line(log_line("2026-10-13 09:01:00", "WARNING", OE,
                              "시장가 거부 → 지정가 5호가 폴백: 삼성전자(005930) @ 70500 (원인 [APBK1943] 시장가 불가)"))
    assert (b["kind"], b["ticker"], b["price"]) == ("buy_fallback", "005930", 70500)
    s = g.parse_line(log_line("2026-10-13 09:02:00", "WARNING", OE,
                              "매도 시장가 거부 → 지정가 5호가 폴백: 삼성전자(005930) @ 69500 "
                              "(원인 [APBK1943] 시장가 불가, 주문번호: 0000300100, 전략: kojiro)"))
    assert (s["kind"], s["ticker"], s["price"], s["order_no"], s["strategy"]) == (
        "sell_fallback", "005930", 69500, "0000300100", "kojiro")
    r = g.parse_line(log_line("2026-10-13 09:03:00", "INFO", OE, "손절 잔여 재주문: 삼성전자(005930) 2주"))
    assert (r["kind"], r["ticker"], r["qty"]) == ("reorder", "005930", 2)


def test_g6d_status_exit_fire():
    e = _one(log_line("2026-10-13 09:30:00", "WARNING", "src.engine.status_exit_watch",
                      "[status_exit_fire] ticker=208640 strategy=kojiro reason=managed iscd=51 mang=Y "
                      "short_over=N qty=3 mode=enforce attempt=1 bought_today=0"))
    assert (e["kind"], e["ticker"], e["strategy"], e["reason"]) == (
        "status_exit_fire", "208640", "kojiro", "managed")


_STRAT = "src.engine.strategies."


@pytest.mark.parametrize("logger,msg,phrase,code,fields", [
    ("kojiro", "[kojiro_hard_stop] 011170 매수가(64400) 대비 -8.1% ≤ -8.0%", "kojiro_hard_stop", "STOP_LOSS",
     {"buy_price": 64400, "pct": -8.1, "threshold": -8.0}),
    ("kojiro", "[kojiro_atr_stop] 000520 손절선(7740) = 매수가(7740) - 2.0×ATR(417.5)", "kojiro_atr_stop",
     "STOP_LOSS", {"line": 7740, "buy_price": 7740}),
    ("kojiro", "[kojiro_trailing] 285130 고점(57000) - 2.5×ATR(2464.3) = 50839 / 현재가 50700",
     "kojiro_trailing", "TRAILING_STOP", {"line": 50839, "current_price": 50700}),
    ("kojiro", "[kojiro_stage3_exit] 003470 스테이지3 진입 (추세 종료) judged_on=2026-09-21",
     "kojiro_stage3_exit", "TREND_EXIT", {}),
    ("bull_flag_breakout", "[bfb_turtle_stop] 356680 손절선(19100) = 매수가(20650) − 2.0×entry_atr(775.0)",
     "bfb_turtle_stop", "STOP_LOSS", {"line": 19100, "buy_price": 20650}),
    ("bull_flag_breakout", "[bfb_turtle_backstop] 100840 매수가(39450) 대비 -7.1% ≤ -7.0%",
     "bfb_turtle_backstop", "STOP_LOSS", {"buy_price": 39450, "pct": -7.1, "threshold": -7.0}),
    ("bull_flag_breakout", "눌림목 손절: 052710 매수가(19270) 대비 -6.0%", "bfb_pullback_stop", "STOP_LOSS",
     {"buy_price": 19270, "pct": -6.0}),
    ("bull_flag_breakout", "눌림목 측정된 이동 도달: 232140 현재가(18640) ≥ 타겟(18640) — 익절 신호",
     "bfb_measured_target", "TAKE_PROFIT", {"current_price": 18640, "target": 18640}),
    ("bull_flag_breakout", "눌림목 시간 청산: 036800 buy_date=2026-09-14 today=2026-09-22 보유일수 초과",
     "bfb_time_exit", "TIME_EXIT", {}),
    ("long_tail_volatility", "롱테일VB 당일 손절: 한켐(457370) -5.0%", "ltv_intraday_stop", "STOP_LOSS",
     {"pct": -5.0, "mode": "intraday"}),
    ("long_tail_volatility", "롱테일VB 손절(상한가 모드): 한켐(457370) -3.6%", "ltv_limit_up_stop",
     "STOP_LOSS", {"pct": -3.6, "mode": "limit_up"}),
    ("volatility_breakout", "변동성돌파 손절: 대한광통신(010170) 매수가(18400) 대비 -5.0% (현재가: 17480)",
     "vb_stop", "STOP_LOSS", {"buy_price": 18400, "pct": -5.0, "current_price": 17480}),
    ("momentum", "손절 신호: 토마토시스템(393210) 매수가(4825) 대비 -5.1% (임계: -5.0%, 현재가: 4580)",
     "momentum_stop", "STOP_LOSS", {"buy_price": 4825, "pct": -5.1, "threshold": -5.0, "current_price": 4580}),
    ("donchian_swing", "[donchian_time_exit] ticker=112610 reason=fail_n_days days_held=20 high=58000 "
                       "target_1r=61000", "donchian_time_exit", "TIME_EXIT", {}),
    ("donchian_swing", "도치안 시간 기반 청산: 316140 보유 5영업일 ≥ 2, 현재가(35550) < 돌파선(35600)",
     "donchian_time_exit_legacy", "TIME_EXIT", {"current_price": 35550}),
    ("donchian_swing", "도치안 스윙 트레일링: 030530 고점(30400) - ATR×1.8 = 26659 / 현재가 26650",
     "donchian_trailing_legacy", "TRAILING_STOP", {"line": 26659, "current_price": 26650}),
])
def test_g6e_exit_reason_phrases(logger, msg, phrase, code, fields):
    e = _one(log_line("2026-09-28 10:00:00", "INFO", _STRAT + logger, msg))
    assert e["kind"] == "exit_reason"
    assert (e["strategy"], e["phrase"], e["reason_code"]) == (logger, phrase, code)
    for k, v in fields.items():
        assert e[k] == v, (k, e[k], v)


def test_g6f_exit_reason_from_wrong_logger_is_none():
    msg = "[kojiro_hard_stop] 011170 매수가(64400) 대비 -8.1% ≤ -8.0%"
    assert jw("grammar").parse_line(log_line("2026-09-28 10:00:00", "INFO", OE, msg)) is None


@pytest.mark.parametrize("logger,msg,ticker,price", [
    ("bull_flag_breakout", "[bfb_vol_gate_pass] ticker=003160 observed=323837 threshold=322528 latch_age_sec=18519",
     "003160", None),
    ("vcp_breakout", "[vcp_vol_gate_pass] ticker=006120 observed=33246 threshold=30296 latch_age_sec=8109",
     "006120", None),
    ("kojiro", "고지로 매수 신호: 000520 현재가(7740) — 스테이지1(6→1) + EMA정배열 + ATR(392.9)", "000520", 7740),
    ("donchian_swing", "도치안 스윙 매수 신호: 112610 현재가(57200) — 신고가(56800) 돌파 + EMA60(47309) 위 + ATR(2867)",
     "112610", 57200),
    ("volatility_breakout", "변동성돌파 매수 신호 [main]: S-Oil(010950) 현재가(152600) >= 목표가(152570), "
                            "이전가(152100), K=0.6119", "010950", 152600),
    ("long_tail_volatility", "롱테일 변동성 돌파 매수 신호 [main]: 인제니아테라퓨틱스(Reg.S)(950260) 현재가(23350) "
                             ">= 목표가(23324), K=0.5804", "950260", 23350),
    ("momentum", "매수 신호: HLB제약(047920) 전일종가(9620) 대비 29.0% (현재가: 12410, 직전: 28.8%)", "047920", 12410),
])
def test_g6g_buy_signal_phrases(logger, msg, ticker, price):
    e = _one(log_line("2026-09-28 10:00:00", "INFO", _STRAT + logger, msg))
    assert (e["kind"], e["strategy"], e["ticker"], e["price"]) == ("buy_signal", logger, ticker, price)


# ── G7 시각 ──────────────────────────────────────────────────────────────────

def test_g7_timestamp_is_kst_aware():
    e = _one(log_line("2026-09-29 16:02:21", "INFO", "src.api.order",
                      "SELL 주문 완료: 030530 1주 @ 0 (주문번호: 0001638800)") + "\n")
    assert e["ts"] == kst(2026, 9, 29, 16, 2, 21)
    assert e["ts"].utcoffset() == timedelta(hours=9)
    assert (e["level"], e["logger"]) == ("INFO", "src.api.order")
