"""cycle412 Red — 짝짓기 골든(설계 관찰자안 2절 출처 표의 실측값을 그대로 고정).

과거분 모드 = `Pairer(source="log_restore")` 에 골든 로그를 넣고 `drain(final=True)`.
기대값 = `fixtures/golden_expected.json`(매도 70 · 매수 75, 주문번호별).

| # | 계약 (설계 2절 실측) |
|---|---|
| P1 | 매도 70/70 · 매수 75/75 행 · 전부 `source="log_restore"` · 행의 주문번호 = 접수 줄 주문번호 = `주문 완료` 줄 주문번호 |
| P2 | 청산 이름 보정 — cycle402 전 7/70 은 사유 줄의 실제 사유로 저장(시간청산 5 · 스테이지3 1 · 측정 목표 익절 1) |
| P3 | 익일청산 11 = `reason_sub` `gap_below` 4(갭률) · `krx_only` 7 |
| P4 | 발동선 정확 15(선 가격 7 + 임계 % 8) · 손절·트레일링 26건의 판단가 = 정확 10 · 역산 13 · 상한만 3 |
| P5 | 주문구분 = `[order_notice]` `kind` — 09-28 이후 매도 42(01×41·44×1) · 매수 45(01) · 그 전 58 은 빈칸 |
| P6 | 매수 판단가 = 신호 줄 현재가, BFB·VCP 15건은 빈칸 · 과거분은 링이 없으니 `signal_src="log_only"` |
| P7 | 09-29 16:00:26 재시작 뒤 16:02:21 donchian TRAILING_STOP(030530) — 선 26659 · 판단가 26650 · 주문구분 44 |
| P8 | 음성: 09-28 HTS 외부 매수 접수 전문 5건(199800) — 미체결이라 행 0 · 외부 후보로만 남는다 |
"""
from __future__ import annotations

from collections import Counter

import pytest

from jw_testkit import golden_expected, golden_lines, jw, kst, parse_all

pytestmark = pytest.mark.unit

EXTERNAL_UNFILLED = {"0000042300", "0000340300", "0000345900", "0000549100", "0001402000"}


_CACHE: dict = {}


def _restore():
    if "v" not in _CACHE:
        p = jw("pairing").Pairer(source="log_restore")
        p.feed_events(parse_all(golden_lines()))
        _CACHE["v"] = (p, p.drain(final=True))
    return _CACHE["v"]


@pytest.fixture
def restored():
    # 픽스처 단계가 아니라 테스트 본문에서 import 가 실패하도록(Red 가 ERROR 가 아니라 FAILED 로 보이게)
    return _restore


def _by_side(out, side):
    return {r["order_no"]: r for r in out["orders"] if r["side"] == side}


def test_p1_every_accept_becomes_one_row(restored):
    _, out = restored()
    sells, buys = _by_side(out, "SELL"), _by_side(out, "BUY")
    exp = golden_expected()
    assert set(sells) == set(exp["sells"])
    assert set(buys) == set(exp["buys"])
    assert len(out["orders"]) == 145
    assert {r["source"] for r in out["orders"]} == {"log_restore"}
    assert out["stops"] == []  # 과거분에는 스냅샷이 없다 → exit 사건 0


@pytest.mark.parametrize("field", ["order_date", "strategy", "ticker", "reason_code", "reason_sub",
                                   "fired_line", "judge_price", "order_division"])
def test_p1b_sell_rows_match_golden(restored, field):
    _, out = restored()
    sells = _by_side(out, "SELL")
    exp = golden_expected()["sells"]
    diffs = {}
    for no, e in exp.items():
        got = sells[no][field]
        want = e[field]
        if field == "order_date":
            got = got.isoformat()
        if got != want:
            diffs[no] = (got, want)
    assert diffs == {}, diffs


@pytest.mark.parametrize("key", ["signal_name", "phrase", "judge_src", "gap"])
def test_p1c_sell_signal_json_matches_golden(restored, key):
    _, out = restored()
    sells = _by_side(out, "SELL")
    exp = golden_expected()["sells"]
    diffs = {no: (sells[no]["signal"].get(key), e[key]) for no, e in exp.items()
             if sells[no]["signal"].get(key) != e[key]}
    assert diffs == {}, diffs


@pytest.mark.parametrize("field", ["order_date", "strategy", "ticker", "order_price", "judge_price",
                                   "order_division"])
def test_p1d_buy_rows_match_golden(restored, field):
    _, out = restored()
    buys = _by_side(out, "BUY")
    exp = golden_expected()["buys"]
    diffs = {}
    for no, e in exp.items():
        got = buys[no][field]
        if field == "order_date":
            got = got.isoformat()
        if got != e[field]:
            diffs[no] = (got, e[field])
    assert diffs == {}, diffs
    assert all(buys[no]["reason_code"] == "ENTRY" for no in exp)
    assert all(buys[no]["signal"]["signal_src"] == exp[no]["signal_src"] for no in exp)


def test_p2_name_correction_distribution(restored):
    _, out = restored()
    sells = list(_by_side(out, "SELL").values())
    assert Counter(r["reason_code"] for r in sells) == {
        "FORCE_CLEAR": 26, "STOP_LOSS": 22, "NEXT_DAY_CLEAR": 11, "TIME_EXIT": 5,
        "TRAILING_STOP": 4, "TREND_EXIT": 1, "TAKE_PROFIT": 1,
    }
    corrected = [r for r in sells if r["reason_code"] != r["signal"]["signal_name"]]
    assert len(corrected) == 7
    assert Counter((r["signal"]["signal_name"], r["reason_code"]) for r in corrected) == {
        ("STOP_LOSS", "TIME_EXIT"): 3, ("TRAILING_STOP", "TIME_EXIT"): 2,
        ("TRAILING_STOP", "TREND_EXIT"): 1, ("TRAILING_STOP", "TAKE_PROFIT"): 1,
    }
    assert all(r["signal"]["reason_line"] for r in corrected)


def test_p3_next_day_clear_subtypes(restored):
    _, out = restored()
    ndc = [r for r in _by_side(out, "SELL").values() if r["reason_code"] == "NEXT_DAY_CLEAR"]
    assert Counter(r["reason_sub"] for r in ndc) == {"gap_below": 4, "krx_only": 7}
    gaps = {r["ticker"]: r["signal"]["gap"] for r in ndc if r["reason_sub"] == "gap_below"}
    assert gaps == {"007810": -2.8, "486990": 8.1, "394800": 2.7, "047920": 3.9}


def test_p4_fired_and_judge_counts(restored):
    _, out = restored()
    sells = list(_by_side(out, "SELL").values())
    assert sum(1 for r in sells if r["fired_line"] is not None) == 15
    core = [r for r in sells if r["reason_code"] in ("STOP_LOSS", "TRAILING_STOP")]
    assert len(core) == 26
    assert Counter(r["signal"].get("judge_src") for r in core) == {"log_price": 10, "log_pct": 13, None: 3}
    upper = [r for r in core if r["signal"].get("judge_src") is None]
    assert {r["signal"]["phrase"] for r in upper} == {"kojiro_atr_stop"}
    assert all(r["signal"]["judge_upper"] == r["fired_line"] for r in upper)
    # 가격 무관 청산은 발동선이 없다(「미발동, 참고값」)
    assert all(r["fired_line"] is None for r in sells
               if r["reason_code"] in ("FORCE_CLEAR", "NEXT_DAY_CLEAR", "TIME_EXIT", "TREND_EXIT"))


def test_p4b_threshold_line_uses_buy_price_and_round(restored):
    """임계 % 문구의 발동선 = round(매수가 × (1 + 임계/100)) — 잔고 화면 `_hard_pct_stop` 과 같은 반올림."""
    _, out = restored()
    sells = _by_side(out, "SELL")
    assert sells["0000578700"]["fired_line"] == round(4825 * (1 + -5.0 / 100))     # momentum 토마토시스템
    assert sells["0000849100"]["fired_line"] == round(39450 * (1 + -7.0 / 100))    # BFB 받침선
    assert sells["0000269700"]["fired_line"] == round(64400 * (1 + -8.0 / 100))    # kojiro 하드
    assert sells["0000849100"]["judge_price"] == round(39450 * (1 + -7.1 / 100))   # 역산


def test_p4c_ltv_judge_uses_last_buy_accept_price(restored):
    """LTV 사유 줄에는 매수가가 없다 — 과거분은 같은 (전략, 종목) 마지막 매수 접수 가격으로 역산."""
    _, out = restored()
    sells = _by_side(out, "SELL")
    r = sells["0001154900"]  # 한켐(457370) 롱테일VB 당일 손절 -5.0%
    assert r["signal"]["phrase"] == "ltv_intraday_stop" and r["signal"]["judge_src"] == "log_pct"
    assert r["fired_line"] is None  # 과거분은 스냅샷 파라미터가 없다


def test_p5_order_division_from_notice(restored):
    _, out = restored()
    sells = list(_by_side(out, "SELL").values())
    buys = list(_by_side(out, "BUY").values())
    assert Counter(r["order_division"] for r in sells) == {"01": 41, "44": 1, None: 28}
    assert Counter(r["order_division"] for r in buys) == {"01": 45, None: 30}
    early = [r for r in sells + buys if r["order_date"] < kst(2026, 9, 28).date()]
    assert len(early) == 58 and all(r["order_division"] is None for r in early)


def test_p6_buy_judge_blank_only_for_bfb_vcp(restored):
    _, out = restored()
    buys = list(_by_side(out, "BUY").values())
    blank = [r for r in buys if r["judge_price"] is None]
    assert len(blank) == 15
    assert {r["strategy"] for r in blank} == {"bull_flag_breakout", "vcp_breakout"}
    assert all(r["signal"]["signal_src"] == "log_only" for r in buys)
    assert all(r["params"] is None for r in buys)


def test_p7_restart_then_trailing_sell_sample(restored):
    _, out = restored()
    r = _by_side(out, "SELL")["0001638800"]
    assert (r["strategy"], r["ticker"], r["reason_code"]) == ("donchian_swing", "030530", "TRAILING_STOP")
    assert (r["fired_line"], r["judge_price"], r["order_division"]) == (26659, 26650, "44")
    assert r["signal"]["judge_src"] == "log_price"
    assert r["noted_at"] == kst(2026, 9, 29, 16, 2, 21)
    assert r["order_date"] == kst(2026, 9, 29).date()


def test_p8_unfilled_external_notices_make_no_rows(restored):
    p, out = restored()
    nos = {r["order_no"] for r in out["orders"]}
    assert nos.isdisjoint(EXTERNAL_UNFILLED)
    # 신규 접수 전문(rctf=0)만 — 0000345900 은 0000340300 의 정정·취소 전문(rctf=2)이다
    assert p.external_notice_orders() == {"0000042300", "0000340300", "0000549100", "0001402000"}
