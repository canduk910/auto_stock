"""성적표 덧붙임 — 낙폭 정지 트리거 · 재개 기준 재설정 · 분기 순위 · 비중 배정 · 편입 전 재정규화."""
from __future__ import annotations

import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import sb_addons_core as S  # noqa: E402


# ── 낙폭 정지 ────────────────────────────────────────────────────────────────

def _feed(g: S.DDPause, eqs):
    return [g.allow(e) for e in eqs]


def test_trigger_at_minus_20_exactly_pauses_next_30_days():
    g = S.DDPause()
    eqs = [100.0, 110.0, 88.0] + [88.0] * 40       # 110 → 88 = −20% 정확히
    ok = _feed(g, eqs)
    # allow(i) 는 i 날 장 시작(e_prev = i−1 날 종가). 88 은 eqs[2] → 그 값을 보는 날 = 색인 2
    assert ok[:2] == [True, True]
    assert ok[2:32] == [False] * 30                 # 30 영업일 금지
    assert ok[32] is True                           # 재개일
    assert len(g.events) == 1 and g.events[0][2] == 110.0


def test_no_trigger_above_threshold():
    g = S.DDPause()
    ok = _feed(g, [100.0, 110.0, 88.01, 88.01, 89.0])
    assert all(ok) and not g.events


def test_resume_resets_peak_to_resume_day_close():
    g = S.DDPause(days=3)
    # 100 → 75 발동(색인 1) · 금지 1~3 · 재개일 4(검사 없음) · 색인 5 의 e_prev(= 재개일 종가 60) 이 새 기준
    eqs = [100.0, 75.0, 70.0, 65.0, 62.0, 60.0, 55.0, 49.0, 47.0]
    ok = _feed(g, eqs)
    assert ok[1:4] == [False, False, False]
    assert ok[4] is True
    assert g.peak == 60.0 or ok[5] is True
    # 60 기준 −20% = 48 → 49 는 발동 안 함, 47 은 발동
    assert ok[5] and ok[6] and ok[7]
    assert ok[8] is False
    assert len(g.events) == 2 and g.events[1][2] == 60.0


def test_no_immediate_retrigger_on_resume_day():
    g = S.DDPause(days=2)
    eqs = [100.0, 79.0, 70.0, 60.0, 60.0]           # 정지 중 더 빠져도 재개일엔 발동 없음
    ok = _feed(g, eqs)
    assert ok == [True, False, False, True, True]
    assert len(g.events) == 1


def test_gatehub_new_run_on_gd_restart_and_disabled_passthrough():
    h = S.GateHub(enabled=False)
    for gd in range(5):
        assert h.allow(gd, 100.0 if gd < 2 else 50.0, 3)
    for gd in range(5):
        h.allow(gd, 100.0)
    assert len(h.runs) == 2
    assert h.runs[0].events                    # 꺼져 있어도 상태는 센다
    assert h.dropped == [0, 0]


def test_gate_source_rewrites_exactly_the_signal_line():
    src = ("def run(sbg, g0, g1):\n    eq_prev = 1.0\n    out = []\n    for gd in range(g0, g1):\n"
           "        todays = list(sbg.get(gd, []))\n        out.append(len(todays))\n"
           "        eq_prev = eq_prev * 0.7\n    return out\n")
    new, n = S.gate_source(src)
    assert n == 1 and "_SB_GATE.allow(gd, eq_prev" in new
    mod = types.ModuleType("m_test_sb")
    exec(compile(src, "m", "exec"), mod.__dict__)
    import inspect  # noqa: F401
    hub = S.GateHub(enabled=True, days=2)
    mod.__dict__["_SB_GATE"] = hub
    loc = {}
    exec(compile(new, "m2", "exec"), mod.__dict__, loc)
    sbg = {gd: ["x"] for gd in range(8)}
    out = loc["run"](sbg, 0, 8)
    # 1.0 → 0.7(−30%): 색인 1 에서 발동 · 1,2 금지 · 3 재개
    assert out[:4] == [1, 0, 0, 1]
    assert hub.dropped[0] >= 2


# ── 곡선 근사 ────────────────────────────────────────────────────────────────

def test_ddp_curve_goes_to_cash_and_reenters_with_cost():
    v = np.array([1.0, 1.0, 0.75, 0.5, 0.5, 0.6, 0.6])
    rf = np.zeros(len(v))
    out, ev = S.ddp_curve(v, rf, days=2, cost_side=0.01)
    assert ev[0][0] == 2 and ev[0][1] == 4
    assert out[2] == pytest.approx(0.75 * 0.99)
    assert out[3] == pytest.approx(out[2])               # 현금: 0.5 로 빠지지 않는다
    assert out[4] == pytest.approx(out[2] * 0.99)        # 재진입 비용
    assert out[5] == pytest.approx(out[4] * 1.2)


# ── 분기 순위 · 비중 ─────────────────────────────────────────────────────────

def test_rank_order_ties_follow_list_order():
    assert S.rank_order({"b": 0.1, "a": 0.1, "c": 0.2}, ["a", "b", "c"]) == ["c", "a", "b"]


def test_weights_top30_and_top5():
    w = S.weights_top(["a", "b", "c", "d", "e", "f", "g", "h"], 0.30)
    assert w["a"] == pytest.approx(0.30) and w["h"] == pytest.approx(0.10) and sum(w.values()) == pytest.approx(1)
    w5 = S.weights_topk(list("abcdefgh"), 5, [0.30] + [0.175] * 4)
    assert set(w5) == set("abcde") and w5["a"] == pytest.approx(0.30) and w5["e"] == pytest.approx(0.175)
    w3 = S.weights_topk(list("abc"), 5, [0.30] + [0.175] * 4)
    assert sum(w3.values()) == pytest.approx(1) and w3["a"] == pytest.approx(0.30 / 0.65)
    assert S.weights_top(["a"], 0.3) == {"a": 1.0}


def test_weights_fixed_renormalizes_before_inclusion():
    base = {"k": 0.30, "d": 0.25, "e": 0.02, "v": 0.0}
    w = S.weights_fixed(["k", "d", "v"], base)
    assert set(w) == {"k", "d"} and w["k"] == pytest.approx(0.30 / 0.55)
    w2 = S.weights_fixed(["k", "d", "e", "v"], base)
    assert w2["e"] == pytest.approx(0.02 / 0.57)


def _curve(dates, rets):
    v = np.cumprod(np.r_[1.0, 1.0 + np.asarray(rets)])
    return dates, v


def test_rotation_inclusion_and_ranking():
    d = pd.bdate_range("2020-01-01", "2020-12-31")
    n = len(d)
    a = _curve(d, np.full(n - 1, 0.001))
    b = _curve(d, np.full(n - 1, 0.002))
    # c 는 2020-05-01 에 시작(편입 전 재정규화 · 첫 분기말 = 6월 말부터 비중)
    dc = d[d >= "2020-05-01"]
    c = _curve(dc, np.full(len(dc) - 1, 0.01))
    res = S.rotation({"a": a, "b": b, "c": c}, ["a", "b", "c"], lambda r, av: S.weights_top(r, 0.30), cost_side=0.0)
    log = res["log"]
    assert log[0]["date"].startswith("2020-03") and set(log[0]["weights"]) == {"a", "b"}
    assert log[0]["ranked"][0] == "b" and log[0]["weights"]["b"] == pytest.approx(0.30)
    assert log[1]["date"].startswith("2020-06") and log[1]["ranked"][0] == "c"
    assert log[1]["weights"]["c"] == pytest.approx(0.30) and log[1]["weights"]["a"] == pytest.approx(0.35)
    # 첫 분기 = a·b 균등 50/50 → 분기말 가치 = 평균
    i = int(np.nonzero(res["dates"] == pd.Timestamp(log[0]["date"]))[0][0])
    exp = 0.5 * a[1][i] + 0.5 * b[1][i]
    assert res["value"][i] == pytest.approx(exp, rel=1e-9)


def test_rotation_turnover_cost():
    d = pd.bdate_range("2020-01-01", "2020-06-30")
    n = len(d)
    a = _curve(d, np.full(n - 1, 0.0))
    b = _curve(d, np.full(n - 1, 0.0))
    res = S.rotation({"a": a, "b": b}, ["a", "b"], lambda r, av: S.weights_top(r, 0.80), cost_side=0.001)
    # 50/50 → 80/20(동순위 → a 1위): 회전 0.6 × 0.1% = 0.06%
    assert res["log"][0]["turnover"] == pytest.approx(0.6)
    assert res["value"][-1] == pytest.approx(1.0 - 0.0006)


def test_live_curve_compounds_on_sell_dates():
    cal = pd.bdate_range("2026-04-27", "2026-05-08")
    trips = [{"strategy": "momentum", "buy_date": "2026-04-29", "sell_date": "2026-04-30", "net": 0.04},
             {"strategy": "momentum", "buy_date": "2026-04-28", "sell_date": "2026-04-29", "net": 0.5},
             {"strategy": "x", "buy_date": "2026-04-29", "sell_date": "2026-04-30", "net": 0.5}]
    d, v, n = S.live_curve(trips, "momentum", cal, "2026-04-29", 0.25)
    assert n == 1 and d[0] == pd.Timestamp("2026-04-28") and v[0] == 1.0
    assert v[-1] == pytest.approx(1.01)


def test_rep_index_lower_median():
    assert S.rep_index([5, 1, 3, 2]) == 3          # 정렬 1,2,3,5 → 하위 중앙 = 2 (색인 3)


def test_period_stats_uses_prior_value():
    d = pd.DatetimeIndex(["2012-12-28", "2013-01-02", "2013-12-30"])
    p = S.period_stats(d, np.array([1.0, 1.1, 1.21]), "2013-01-01", "2013-12-31")
    assert p["total"] == pytest.approx(0.21)


# ── 추가 등록 QRX — 포트폴리오 −10% 손절 ─────────────────────────────────────

def test_rotation_stop_sells_next_day_cash_30_reenters_day_31():
    d = pd.bdate_range("2021-01-04", periods=60)
    n = len(d)
    r = np.zeros(n - 1)
    r[4] = -0.12                                   # 색인 5 에서 −12% → 발동
    r[10] = -0.05                                  # 매도 뒤(현금 중) 손실은 받지 않는다
    a = _curve(d, r)
    res = S.rotation({"a": a}, ["a"], lambda rk, av: S.weights_top(rk, 0.3), cost_side=0.001,
                     stop={"dd": 0.10, "days": 30, "rf": np.zeros(n), "extra": 0.0})
    ev = res["events"][0]
    i_t = int(d.get_loc(pd.Timestamp(ev["trigger"])))
    i_s = int(d.get_loc(pd.Timestamp(ev["sell"])))
    i_r = int(d.get_loc(pd.Timestamp(ev["reenter"])))
    assert i_t == 5 and i_s == 6 and i_r == i_s + 31
    v = res["value"]
    assert v[i_s] == pytest.approx(0.88 * 0.999)
    assert v[i_r - 1] == pytest.approx(v[i_s])          # 현금(금리 0)
    assert v[i_r] == pytest.approx(v[i_s] * 0.999)       # 재진입 비용


def test_rotation_stop_resets_peak_at_reentry_and_none_is_unchanged():
    d = pd.bdate_range("2021-01-04", periods=120)
    n = len(d)
    r = np.zeros(n - 1)
    r[4] = -0.12
    r[60] = -0.095                                       # 재진입 뒤 새 기준 대비 −9.5% → 발동 없음
    a = _curve(d, r)
    res = S.rotation({"a": a}, ["a"], lambda rk, av: S.weights_top(rk, 0.3), cost_side=0.0,
                     stop={"dd": 0.10, "days": 30, "rf": np.zeros(n), "extra": 0.0})
    assert len(res["events"]) == 1
    base = S.rotation({"a": a}, ["a"], lambda rk, av: S.weights_top(rk, 0.3), cost_side=0.0)
    assert base["events"] == [] and base["value"][-1] == pytest.approx(a[1][-1])
