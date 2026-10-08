"""cycle412 Red — 손절선 사건 규칙(계획서 4-2 R8 규칙을 워커 W2 로 옮긴 것, 관찰자안 3절 「부팅 처리」).

| # | 계약 |
|---|---|
| S1 | 처음 보는 보유 = `first` · 다시 보면 변화 없으면 0 |
| S2 | 내려가면 1원이라도 `change` |
| S3 | 올라가면 직전 **기록** 대비 0.5% 이상일 때만 · 조금씩 오르면 누적이 넘는 회전에 1번 |
| S4 | `stop_kind` · 목표가 · 목표 도달 · 무장가가 바뀌면 `change` |
| S5 | 15:30 이후 첫 관측 `eod` — (전략,종목)마다 하루 1번, 같은 회전 변화가 있어도 행 1개 |
| S6 | 꺼진 전략의 보유 = `paused` 꺼짐 구간마다 1번 |
| S7 | `booting` 회전 0 · 그 뒤 첫 회전 0(기억도 안 바꿈) · 다음 회전에 값이 다르면 `boot`(문턱 없음) |
| S8 | 엔진 정지·idle·G1 없음 = 0 · 21:30 보유 사라짐은 청산이 아니다(다음 날 이어 붙는다) |
| S9 | DB 마지막 행으로 이어 붙이기 · `new_holding_keys` 면 새 보유(`first`) |
| S10 | 무장가 = G1 `kk_arm_price`, 무장(null) 뒤에는 마지막 무장가 유지 · `target_hit` = `measured_move_hit` |
| S11 | 사건 dict 칸 = 저장 표 칸 · `inputs` 에 원인 입력 |
| S12 | 한 회전·한 (전략,종목)에 행 1개 — 우선순위 `first` > `boot` > `paused` > `eod` > `change` |
"""
from __future__ import annotations

import pytest

from jw_testkit import jw, kst

pytestmark = pytest.mark.unit

EVENT_KEYS = {"strategy", "ticker", "buy_date", "pos_order_no", "observed_at", "event", "stop_price",
              "stop_kind", "target_price", "target_hit", "arm_price", "inputs"}


def at(h, m, s=0, day=13):
    return kst(2026, 10, day, h, m, s)


def it(sid="kojiro", ticker="005930", *, stop=9500, source="effective", target=None, target_source=None,
       arm=None, armed=None, buy=10000, high=10000, qty=3, atr=400.0):
    return {"strategy_id": sid, "ticker": ticker, "stop_price": stop, "stop_source": source,
            "target_price": target, "target_source": target_source, "buy_price": buy, "quantity": qty,
            "high_since_buy": high, "buy_date": "2026-10-10", "order_no": "0000100000", "entry_atr": atr,
            "kk_armed": armed, "kk_arm_price": arm}


def G0(phase="main_trading", running=True, enabled=None):
    enabled = enabled or {}
    sids = {"kojiro", "donchian_swing", "bull_flag_breakout"} | set(enabled)
    return {"running": running, "phase": phase,
            "strategies": {s: {"enabled": enabled.get(s, True), "params": {}, "buy_signals": []} for s in sids}}


def G1(*items, when=None):
    return {"running": True, "as_of": (when or at(10, 0)).isoformat(), "items": list(items)}


def T(**kw):
    return jw("stops").StopTracker(**kw)


def obs(tr, when, *items, g0=None, new=frozenset()):
    return tr.observe(observed_at=when, g0=g0 or G0(), g1=G1(*items, when=when), new_holding_keys=new)


def events(evs):
    return [(e["strategy"], e["ticker"], e["event"], e["stop_price"]) for e in evs]


def test_s1_first_then_quiet():
    tr = T()
    e1 = obs(tr, at(10, 0), it(stop=9500))
    assert events(e1) == [("kojiro", "005930", "first", 9500)]
    assert set(e1[0]) == EVENT_KEYS
    assert obs(tr, at(10, 0, 15), it(stop=9500)) == []


def test_s2_any_decrease_records():
    tr = T()
    obs(tr, at(10, 0), it(stop=9500))
    assert events(obs(tr, at(10, 0, 15), it(stop=9499))) == [("kojiro", "005930", "change", 9499)]


def test_s3_increase_needs_half_percent_over_last_record():
    tr = T()
    obs(tr, at(10, 0), it(stop=10000))
    assert obs(tr, at(10, 0, 15), it(stop=10040)) == []            # +0.40%
    assert obs(tr, at(10, 0, 30), it(stop=10049)) == []            # +0.49% (직전 기록 10000 대비)
    assert events(obs(tr, at(10, 0, 45), it(stop=10050))) == [("kojiro", "005930", "change", 10050)]
    assert obs(tr, at(10, 1, 0), it(stop=10090)) == []             # 새 기록 10050 대비 +0.40%


@pytest.mark.parametrize("before,after", [
    (dict(stop=9500, source="hard_pct"), dict(stop=9500, source="effective")),
    (dict(target=12000, target_source="measured_move"), dict(target=12100, target_source="measured_move")),
    (dict(target=12000, target_source="measured_move"), dict(target=12000, target_source="measured_move_hit")),
    (dict(arm=12400, armed=False), dict(arm=12500, armed=False)),
    (dict(stop=None, source="mode_dependent"), dict(stop=9500, source="effective")),
])
def test_s4_kind_target_arm_changes_record(before, after):
    tr = T()
    obs(tr, at(10, 0), it(**before))
    evs = obs(tr, at(10, 0, 15), it(**after))
    assert [e["event"] for e in evs] == ["change"]


def test_s5_eod_once_per_key_per_day_even_with_change():
    tr = T()
    obs(tr, at(15, 29, 45), it(stop=9500), it(ticker="000660", stop=50000))
    e = obs(tr, at(15, 30, 0), it(stop=9400), it(ticker="000660", stop=50000))
    assert sorted((x["ticker"], x["event"], x["stop_price"]) for x in e) == [
        ("000660", "eod", 50000), ("005930", "eod", 9400)]
    assert obs(tr, at(15, 30, 15), it(stop=9400), it(ticker="000660", stop=50000)) == []
    # 다음 날 15:30 에 다시 1번
    nxt = obs(tr, at(15, 31, 0, day=14), it(stop=9400), it(ticker="000660", stop=50000))
    assert sorted((x["ticker"], x["event"]) for x in nxt) == [("000660", "eod"), ("005930", "eod")]


def test_s6_paused_once_per_disabled_episode():
    tr = T()
    obs(tr, at(10, 0), it())
    off = G0(enabled={"kojiro": False})
    assert [e["event"] for e in obs(tr, at(10, 0, 15), it(), g0=off)] == ["paused"]
    assert obs(tr, at(10, 0, 30), it(), g0=off) == []
    assert obs(tr, at(10, 0, 45), it()) == []                      # 다시 켜짐
    assert [e["event"] for e in obs(tr, at(10, 1, 0), it(), g0=off)] == ["paused"]


def test_s7_boot_skip_rotation_then_boot_event():
    tr = T()
    obs(tr, at(10, 0), it(stop=9500))
    assert obs(tr, at(10, 5), it(stop=9000), g0=G0(phase="booting")) == []
    # booting 을 벗어난 첫 회전 — 재구성 전 값일 수 있어 아무것도 쓰지 않는다(값 9100 은 기억도 안 한다)
    assert obs(tr, at(10, 5, 15), it(stop=9100)) == []
    # 다음 회전 — 직전 기록(9500)과 다르면 문턱 없이 boot
    assert events(obs(tr, at(10, 5, 30), it(stop=9498))) == [("kojiro", "005930", "boot", 9498)]
    assert obs(tr, at(10, 5, 45), it(stop=9498)) == []


def test_s7b_boot_with_same_value_records_nothing():
    tr = T()
    obs(tr, at(10, 0), it(stop=9500))
    obs(tr, at(10, 5), it(stop=9500), g0=G0(phase="booting"))
    obs(tr, at(10, 5, 15), it(stop=9500))
    assert obs(tr, at(10, 5, 30), it(stop=9500)) == []


def test_s7c_boot_increase_below_threshold_still_boot():
    tr = T()
    obs(tr, at(10, 0), it(stop=9500))
    obs(tr, at(10, 5), it(stop=9500), g0=G0(phase="booting"))
    obs(tr, at(10, 5, 15), it(stop=9500))
    assert [e["event"] for e in obs(tr, at(10, 5, 30), it(stop=9501))] == ["boot"]


@pytest.mark.parametrize("g0", [None, {"running": False, "phase": "main_trading", "strategies": {}},
                                {"running": True, "phase": "idle", "strategies": {}}])
def test_s8_idle_or_stopped_writes_nothing(g0):
    tr = T()
    assert tr.observe(observed_at=at(22, 0), g0=g0, g1=G1(it(), when=at(22, 0))) == []


def test_s8b_no_g1_writes_nothing():
    tr = T()
    obs(tr, at(10, 0), it())
    assert tr.observe(observed_at=at(10, 0, 15), g0=G0(), g1=None) == []


def test_s8c_2130_clear_is_not_exit_and_next_morning_continues():
    tr = T()
    assert [e["event"] for e in obs(tr, at(15, 31), it(stop=9500))] == ["first"]  # first 가 eod 보다 앞선다
    assert tr.observe(observed_at=at(21, 31), g0=G0(phase="idle"), g1=G1(when=at(21, 31))) == []
    # 다음 날 아침 부팅 → 같은 값이면 아무것도 없다(first 를 다시 쓰지 않는다)
    obs(tr, at(7, 46, 0, day=14), g0=G0(phase="booting"))
    obs(tr, at(9, 0, 0, day=14), it(stop=9500))
    assert obs(tr, at(9, 0, 15, day=14), it(stop=9500)) == []


def test_s9_continuation_from_db_last_row():
    last = {("kojiro", "005930"): {"stop_price": 9500, "stop_kind": "effective", "target_price": None,
                                   "target_hit": None, "arm_price": None, "event": "change",
                                   "observed_at": at(14, 0, day=10)}}
    tr = T(last_rows=last)
    assert obs(tr, at(10, 0), it(stop=9500)) == []
    assert events(obs(tr, at(10, 0, 15), it(stop=9400))) == [("kojiro", "005930", "change", 9400)]


def test_s9b_new_holding_after_closing_sell_gets_first():
    last = {("kojiro", "005930"): {"stop_price": 9500, "stop_kind": "effective", "target_price": None,
                                   "target_hit": None, "arm_price": None, "event": "eod",
                                   "observed_at": at(15, 31, day=10)}}
    tr = T(last_rows=last)
    evs = obs(tr, at(10, 0), it(stop=9500), new=frozenset({("kojiro", "005930")}))
    assert [e["event"] for e in evs] == ["first"]


def test_s10_arm_price_kept_after_arming_and_target_hit():
    tr = T()
    e1 = obs(tr, at(10, 0), it("donchian_swing", stop=9200, arm=12400, armed=False))
    assert e1[0]["arm_price"] == 12400
    e2 = obs(tr, at(10, 0, 15), it("donchian_swing", stop=10000, arm=None, armed=True))
    assert e2[0]["arm_price"] == 12400 and e2[0]["inputs"]["kk_armed"] is True
    e3 = obs(tr, at(10, 0, 30), it("bull_flag_breakout", target=12000, target_source="measured_move_hit"))
    assert e3[0]["target_hit"] is True and e3[0]["target_price"] == 12000


def test_s11_inputs_and_holding_identity():
    tr = T()
    (e,) = obs(tr, at(10, 0), it(stop=9500, buy=10000, high=10500, qty=3, atr=400.0))
    assert e["buy_date"] == kst(2026, 10, 10).date() and e["pos_order_no"] == "0000100000"
    assert e["observed_at"] == at(10, 0) and e["stop_kind"] == "effective"
    for k, v in {"buy_price": 10000, "quantity": 3, "high_since_buy": 10500, "entry_atr": 400.0,
                 "stop_source": "effective"}.items():
        assert e["inputs"][k] == v, k


def test_s12_two_strategies_same_ticker_are_separate_keys():
    tr = T()
    evs = obs(tr, at(10, 0), it("kojiro", stop=9500), it("donchian_swing", stop=9200))
    assert sorted((e["strategy"], e["event"]) for e in evs) == [("donchian_swing", "first"), ("kojiro", "first")]
