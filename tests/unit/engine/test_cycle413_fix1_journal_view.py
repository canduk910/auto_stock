"""cycle413 보완 1차 Red — 거래일지 카드 조립 leaf `src/engine/journal_view.py::build_card` 결함 회귀.

판정 원문 = scratchpad `c413/fix/verdict1.md`(결함 #4·#5·#8·#9·#10·#11·#12 의 leaf 몫) ·
명세 = `_workspace/red/cycle413/journal_view_spec.md` · 계약 = `_workspace/red/cycle413/journal_view_contract.md`.
이 파일과 명세가 갈리면 이 파일이 정본이다(갈린 곳은 그 테스트의 docstring 에 적는다).

| # | 결함 → 계약 |
|---|---|
| F4 | 사유 코드가 None(기록 전 청산·`unmatched`·`external`·일지 조회 실패)이면 `line_role` 을 정하지 않는다(None) — 「손절 미발동」 단정 금지. 명세 3-3 은 「외부」를 reference 로 적었으나 판정 #4 가 정본이다(엔진이 판 것이 아니므로 손절의 발동 여부를 모른다) |
| F5 | TRAILING_STOP 사유 줄 없음(momentum·etf_trend — 워커 문법에 패턴이 없어 `fired_line=None`)이고 스냅샷 손절선이 `hard_pct`(고정% 근사)면 문장에 트레일선 숫자를 쓰지 않는다 |
| F8 | 체결 행 조회 실패(`fills=None`)여도 `opened_at`·`closed_at`·`held_days` 를 페어의 매수/매도 일시로 채운다(TS 타입 non-null 유지) · MFE/MAE 는 `lookup_failed`(「해당 없음」 위장 금지) |
| F9 | 손절선 방향은 「직전에 보인 행 중 **값이 있는** 것」과 비교한다(명세 4-3) — first 9,400 → eod None → boot 9,000 = down −400 |
| F10 | 비용 맵에 없는 체결 id 는 0원이 아니라 None(「모름 ≠ 0」) — 그 몫이 빠진 `paid_total` 도 None |
| F11 | VB·LTV 진입 문장은 「{보드} 돌파선 {가격} 돌파」(명세 3-1 · 3-2 — 보드 표기 = 2-6 `main` 본장 · `pre_nxt` NXT 프리 · `post_nxt` NXT 애프터) |
| F12 | 익절(TAKE_PROFIT) 청산 줄의 발동선 = 신호의 목표가(`signal.target`) — 진입 목표가 기록 전인 복원 BFB 도 청산 줄에 「목표 18,640」 이 선다(지금은 `line_na='unknown'` → 「—」) |
"""

from __future__ import annotations

import importlib
from datetime import date

import pytest

from tests.unit.engine.test_cycle413_journal_view import (
    A_BUY,
    A_COSTS,
    A_SELL,
    _a_kw,
    _a_pair,
    _c_kw,
    _c_pair,
    _entry_text,
    _exit,
    _llm,
    _order,
    _stop,
    _stop_card,
    _two_leg,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def jv():
    return importlib.import_module("src.engine.journal_view")


# ════════════════════════════════════════════════════════════════════════════
# F4 — 사유 코드 None → line_role None
# ════════════════════════════════════════════════════════════════════════════
def _no_code_row(source):
    row = _order(date(2026, 10, 5), "SX", "SELL", "kojiro", "005930", source=source, reason_code=None, signal=None)
    row["reason_code"] = None
    return row


@pytest.mark.parametrize("source", ["external", "unmatched"])
def test_f4_external_or_unmatched_exit_has_no_line_role(jv, source):
    x = _two_leg(jv, strategy="kojiro", sell_row=_no_code_row(source))["exits"][0]
    assert x["reason"]["code"] is None
    assert x["line_role"] is None, f"{source}: 사유를 모르는 청산을 「손절 미발동(reference)」 으로 단정했다"


def test_f4_exit_before_record_has_no_line_role(jv):
    """일지 행이 없는 기록 전 청산(09-10 < orders_restored 09-17)."""
    x = _two_leg(jv, strategy="kojiro", day="2026-09-10")["exits"][0]
    assert x["reason"]["code"] is None and x["reason"]["na"] == "before_record"
    assert x["line_role"] is None


def test_f4_orders_lookup_failed_has_no_line_role(jv):
    card = jv.build_card(_a_pair(), **_a_kw(orders=None))
    x = card["exits"][0]
    assert x["reason"]["na"] == "lookup_failed"
    assert x["line_role"] is None


@pytest.mark.parametrize("code,role", [("MANUAL", "reference"), ("FORCE_CLEAR", "reference"),
                                       ("TAKE_PROFIT", "target"), ("STOP_LOSS", "fired")])
def test_f4_known_codes_keep_their_role(jv, code, role):
    """가드 — 사유를 아는 청산의 역할은 그대로(수동 매도는 여전히 reference)."""
    kw = {"source": "manual_api", "signal": {"path": "manual"}} if code == "MANUAL" else {}
    assert _exit(jv, "kojiro", code=code, eff=9500, **kw)["line_role"] == role


# ════════════════════════════════════════════════════════════════════════════
# F5 — TRAILING_STOP 사유 줄 없음 + hard_pct 스냅샷 → 트레일선 숫자 금지
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("strategy", ["momentum", "etf_trend"])
def test_f5_trailing_without_fired_line_does_not_print_hard_pct_as_trail_line(jv, strategy):
    x = _exit(jv, strategy, code="TRAILING_STOP", eff=9500,
              signal={"stop_kind": "hard_pct", "snapshot_age_s": 6})
    text = x["reason"]["text"]
    assert text == "트레일선 이탈", text
    assert "9,500" not in text
    # 값 자체는 지우지 않는다(유효선 칸은 스냅샷 값 그대로 — 근사 여부는 화면이 stop_kind 로 보인다).
    assert x["effective_line"] == 9500 and x["fired_line"] is None


def test_f5_trailing_effective_snapshot_still_prints_line(jv):
    """가드 — 스냅샷이 전략 손절선(`effective`)이면 지금처럼 숫자를 쓴다."""
    x = _exit(jv, "vcp_breakout", code="TRAILING_STOP", eff=60000, signal={"stop_kind": "effective"})
    assert x["reason"]["text"] == "트레일선 60,000 이탈"


def test_f5_trailing_with_fired_line_prints_fired_even_if_snapshot_is_hard_pct(jv):
    """가드 — 발동선이 있으면(워커가 줄에서 읽은 선) 그 숫자를 쓴다."""
    x = _exit(jv, "momentum", code="TRAILING_STOP", fired=9600, eff=9500, signal={"stop_kind": "hard_pct"})
    assert x["reason"]["text"] == "트레일선 9,600 이탈"


# ════════════════════════════════════════════════════════════════════════════
# F8 — 체결 행 조회 실패(fills=None): 시각·보유일은 페어로 · MFE/MAE 는 조회 실패
# ════════════════════════════════════════════════════════════════════════════
def test_f8_closed_pair_fills_lookup_failed_keeps_dates_from_pair(jv):
    card = jv.build_card(_a_pair(), **_a_kw(fills=None))
    assert isinstance(card["opened_at"], str), "opened_at 이 None — TS 타입(string) 위반·화면 「null」"
    assert card["opened_at"].startswith("2026-10-05T09:12:03") and card["opened_at"].endswith("+09:00")
    assert isinstance(card["closed_at"], str)
    assert card["closed_at"].startswith("2026-10-08T14:31:20") and card["closed_at"].endswith("+09:00")
    assert card["held_days"] == 3
    ex = card["excursion"]
    assert ex["na"] == "lookup_failed", f"체결 조회 실패를 {ex['na']!r} 로 위장했다"
    assert ex["mfe"] is None and ex["mae"] is None
    # 거래기록(페어)·비용은 그대로 — 조회 실패는 그 칸에만 번진다.
    assert card["pnl"]["gross_krw"] == 44000 and card["anchor_trade_id"] == A_BUY


def test_f8_open_pair_fills_lookup_failed_held_days_until_now(jv):
    card = jv.build_card(_c_pair(), **_c_kw(fills=None))
    assert card["status"] == "open" and card["closed_at"] is None
    assert card["opened_at"].startswith("2026-10-05T10:00:00") and card["opened_at"].endswith("+09:00")
    assert card["held_days"] == 4
    assert card["excursion"]["na"] == "lookup_failed"


# ════════════════════════════════════════════════════════════════════════════
# F9 — 방향은 값이 있는 직전 행과 비교
# ════════════════════════════════════════════════════════════════════════════
def test_f9_direction_skips_valueless_previous_row(jv):
    rows = [
        _stop("donchian_swing", "005930", "2026-10-05T09:12:20", "first", 9400),
        _stop("donchian_swing", "005930", "2026-10-05T15:31:00", "eod", None, kind="engine_idle"),
        _stop("donchian_swing", "005930", "2026-10-06T09:00:30", "boot", 9000),
    ]
    tr = _stop_card(jv, rows)["stop_track"]
    assert [r["event"] for r in tr["rows"]] == ["first", "eod", "boot"]
    boot = tr["rows"][2]
    assert boot["direction"] == "down", "400원 내린 재시작 재계산이 「down」 으로 안 보인다"
    assert boot["delta_won"] == -400
    assert tr["downs"] == 1
    assert tr["rows"][1]["direction"] is None and tr["rows"][1]["delta_won"] is None


def test_f9_first_valued_row_after_valueless_start_has_no_direction(jv):
    """가드 — 비교할 값이 앞에 하나도 없으면 방향을 정하지 않는다."""
    rows = [
        _stop("long_tail_volatility", "005930", "2026-10-05T09:12:20", "first", None, kind="mode_dependent"),
        _stop("long_tail_volatility", "005930", "2026-10-06T10:00:00", "change", 9000),
    ]
    tr = _stop_card(jv, rows, strategy="long_tail_volatility")["stop_track"]
    assert tr["rows"][1]["direction"] is None and tr["ups"] == 0 and tr["downs"] == 0


# ════════════════════════════════════════════════════════════════════════════
# F10 — 비용 맵에 없는 체결 id 는 0 이 아니라 None
# ════════════════════════════════════════════════════════════════════════════
def test_f10_missing_buy_cost_is_none_not_zero(jv):
    costs = {A_SELL: dict(A_COSTS[A_SELL])}
    co = jv.build_card(_a_pair(), **_a_kw(costs=costs))["costs"]
    assert co["entry_fee"] is None, f"비용 맵에 없는 매수 체결을 {co['entry_fee']!r} 원으로 계산했다"
    assert co["exits"][0]["fee"] == pytest.approx(764) and co["exits"][0]["tax"] == pytest.approx(1071)
    assert co["paid_total"] is None, "모르는 진입 수수료를 0 으로 친 합계"


def test_f10_missing_sell_cost_is_none_not_zero(jv):
    costs = {A_BUY: dict(A_COSTS[A_BUY])}
    co = jv.build_card(_a_pair(), **_a_kw(costs=costs))["costs"]
    assert co["entry_fee"] == pytest.approx(701)
    assert co["exits"][0]["fee"] is None and co["exits"][0]["tax"] is None
    assert co["paid_total"] is None


# ════════════════════════════════════════════════════════════════════════════
# F11 — VB·LTV 진입 문장에 보드
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("strategy,board,price,head", [
    ("volatility_breakout", "main", 30500, "본장 돌파선 30,500 돌파"),
    ("long_tail_volatility", "pre_nxt", 8120, "NXT 프리 돌파선 8,120 돌파"),
    ("long_tail_volatility", "post_nxt", 8120, "NXT 애프터 돌파선 8,120 돌파"),
])
def test_f11_ring_vb_ltv_sentence_names_board(jv, strategy, board, price, head):
    sig = {"board": board, "target_price": price, "k": 0.5, "change_rate": 2.1, "signal_src": "ring",
           "path": "accept"}
    text = _entry_text(jv, strategy, sig)["reason"]["text"]
    assert text.startswith(head), text


def test_f11_ring_vb_without_board_keeps_plain_line(jv):
    sig = {"target_price": 30500, "k": 0.5, "signal_src": "ring", "path": "accept"}
    text = _entry_text(jv, "volatility_breakout", sig)["reason"]["text"]
    assert text.startswith("돌파선 30,500 돌파") and "None" not in text


def test_f11_ai_augmented_vb_sentence_names_board(jv):
    d = date(2026, 9, 22)
    e = _entry_text(jv, "volatility_breakout", {"signal_src": "log_only", "path": "accept"}, source="log_restore",
                    day="2026-09-22",
                    llm=_llm(d, "volatility_breakout", target_won=30400, k=0.5, strategy_board="pre_nxt"))
    r = e["reason"]
    assert r["src"] == "restored_ai"
    assert r["text"].startswith("NXT 프리 돌파선 30,400 돌파"), r["text"]
    assert "K 0.50" in r["text"]


# ════════════════════════════════════════════════════════════════════════════
# F12 — 익절 청산 줄의 목표가
# ════════════════════════════════════════════════════════════════════════════
def test_f12_take_profit_exit_line_carries_signal_target(jv):
    """복원 BFB(진입 목표 = 기록 전) — 청산 줄은 신호의 목표가로 「목표 18,640」 을 세운다."""
    row = _order(date(2026, 10, 2), "SX", "SELL", "bull_flag_breakout", "005930", source="log_restore",
                 reason_code="TAKE_PROFIT",
                 signal={"signal_name": "TAKE_PROFIT", "phrase": "bfb_measured_target", "judge_src": "log_price",
                         "current_price": 18640, "target": 18640, "path": "accept"})
    card = _two_leg(jv, strategy="bull_flag_breakout", day="2026-09-22", sell_day="2026-10-02",
                    buy=(14900, None), sell=(18620, None), sell_row=row)
    x = card["exits"][0]
    assert x["line_role"] == "target"
    assert x["fired_line"] == 18640, "익절 청산의 목표가가 줄에 없다 — 화면이 「—」 를 그린다"
    assert x["fired_src"] == "restored"
    assert x["line_na"] is None
    assert card["entry"]["target"]["price"] is None   # 진입 목표는 여전히 기록 전(복원분)


def test_f12_live_take_profit_fired_src_is_live(jv):
    x = _exit(jv, "bull_flag_breakout", code="TAKE_PROFIT", eff=12350,
              signal={"phrase": "bfb_measured_target", "target": 13450, "current_price": 13460})
    assert (x["fired_line"], x["fired_src"], x["effective_line"]) == (13450, "live", 12350)
