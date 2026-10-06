"""(라) 장세 규칙 미국 이식 — 기울기 · 칸 판정 · t+1 집행 · 정렬 · 한국 재현 일치."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import global_alloc_b as GB  # noqa: E402
from replay import ra_us as R  # noqa: E402
from replay import regime_v2 as V  # noqa: E402


def _mkt(n=300, asset="SPX", x_ret=0.0, l_ret=0.0, c_ret=0.0):
    dates = pd.bdate_range("2000-01-03", periods=n)
    ix, il = R.cols(asset)
    ret = np.zeros((n, GB.N))
    ret[:, ix] = x_ret
    ret[:, il] = l_ret
    ret[:, GB.I_CASH] = c_ret
    return GB.Mkt(dates, ret, np.zeros((n, GB.N)), np.full(n, 1 / 365), np.zeros(GB.N, bool), np.zeros(GB.N))


def test_slope_t7_is_sma120_over_20_sessions():
    c = pd.Series(np.arange(1.0, 301.0), index=pd.bdate_range("2000-01-03", periods=300))
    f = R.feats_from_close(c)
    t = 250
    s_now = c.iloc[t - 119:t + 1].mean()
    s_then = c.iloc[t - 20 - 119:t - 20 + 1].mean()
    assert f["T7"].iloc[t] == pytest.approx(s_now / s_then - 1)
    assert np.isnan(f["T7"].iloc[130])                     # 120 + 20 세션 전엔 결측
    falling = R.feats_from_close(c[::-1].reset_index(drop=True).set_axis(c.index))
    assert falling["T7"].iloc[t] < 0


def test_breadth_columns_missing_on_us():
    f = R.feats_from_close(pd.Series(np.linspace(1, 2, 300), index=pd.bdate_range("2000-01-03", periods=300)))
    assert f[list(R.NO_US)].isna().all().all()


def test_transplant_cells_slope_up_is_2x_else_cash():
    """폭 결측 = 조건2 거짓 → 칸은 10(2배) 또는 00(현금)뿐."""
    f = pd.DataFrame({"T7": [0.01, -0.01, np.nan, 0.0], "R5": [np.nan] * 4})
    keys = V.rule_keys(f, R.RULE_RA)
    assert list(keys) == ["10", "00", "00", "00"]
    assert list(R.expo_of(keys, R.MAP_RA)) == [2.0, 0.0, 0.0, 0.0]
    # 폭이 있으면 원판 칸 그대로
    f2 = pd.DataFrame({"T7": [0.01, -0.01, 0.01], "R5": [0.2, 0.2, 0.5]})
    assert list(R.expo_of(V.rule_keys(f2, R.RULE_RA), R.MAP_RA)) == [0.0, 1.0, 2.0]


def test_rule_constants_match_regime_v2_artifacts():
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    ra = json.load(open(os.path.join(here, "_workspace/analysis/regime_v2_20261006/ra_rule.json")))
    assert tuple(tuple(x) for x in ra["rule"]) == R.RULE_RA and ra["map"] == R.MAP_RA
    res = json.load(open(os.path.join(here, "_workspace/analysis/regime_v2_20261006/result.json")))
    top = res["meta"]["desc"]["ra_top5"]
    for bn, k in (("B2", 1), ("B3", 2), ("B4", 3)):
        assert top[k]["map"] == R.B_RULES[bn][1]
        assert top[k]["name"] == V.rule_name(R.B_RULES[bn][0])


def test_us_candidates_drop_breadth_and_kosdaq():
    c = R.us_candidates()
    assert len(c) == 92
    assert not any(cond[0] in ("T8", "T9", "R5") for r in c for cond in r)
    full = V.candidates()
    assert [full.index(r) for r in c] == sorted(full.index(r) for r in c)   # 원판 순서 유지


def test_align_before_uses_strictly_previous_us_close():
    us = pd.DataFrame({"x": [1.0, 2.0, 3.0]}, index=pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"]))
    krx = pd.DatetimeIndex(["2020-01-03", "2020-01-06", "2020-01-07"])
    out = R.align_before(us, krx)
    assert list(out["x"]) == [1.0, 2.0, 3.0]                # D 의 값 = D 보다 앞선 마지막 미국 종가


def test_t_plus_1_execution_misses_jump_on_execution_day():
    """종가 t 결정 → t+1 종가 집행: t+1 당일 수익은 잡지 못하고 t+2 부터 탄다."""
    n = 40
    m = _mkt(n=n)
    ix, il = R.cols("SPX")
    expo = np.zeros(n)
    expo[10:] = 1.0                                          # 결정 t=10 에 1배
    m.ret[11, ix] = 0.50                                     # 집행일 당일 급등 — 못 잡는다
    m.ret[12, ix] = 0.10                                     # 다음 날 — 잡는다
    sim = GB.simulate(m, R.schedule(m, expo, 0, n - 1, ix, il), 0, n - 1, cost_one_way=0.0)
    assert sim.value[11] == pytest.approx(1.0)
    assert sim.value[12] == pytest.approx(1.10)


def test_schedule_decides_month_end_and_changes():
    n = 70
    m = _mkt(n=n)
    ix, il = R.cols("NDX")
    expo = np.zeros(n)
    expo[5:] = 2.0
    sch = R.schedule(m, expo, 0, n - 1, ix, il)
    assert 0 in sch and 5 in sch
    assert sch[5][il] == 1.0 and sch[5][ix] == 0.0
    me = [int(i) for i in GB.decision_points(m.dates, "M") if i < n - 1]
    assert all(i in sch for i in me)


def test_generic_learn_equals_regime_v2_on_k200():
    n = 300
    dates = pd.bdate_range("2000-01-03", periods=n)
    rng = np.random.default_rng(1)
    ret = np.zeros((n, GB.N))
    ret[:, V.I_K] = rng.normal(0.0005, 0.01, n)
    ret[:, V.I_L] = 2 * ret[:, V.I_K]
    ret[:, GB.I_CASH] = 0.0001
    m = GB.Mkt(dates, ret, np.zeros((n, GB.N)), np.full(n, 1 / 365), np.zeros(GB.N, bool), np.zeros(GB.N))
    keys = np.array(["a", "b", "c"] * 100, dtype=object)
    win = (str(dates[1].date()), str(dates[-1].date()))
    assert R.learn(m, keys, win, V.I_K, V.I_L)["map"] == V.learn_index(m, keys, win)["map"]


def test_judge_rules():
    def b(p05, p95, d):
        return {"mar": {"p05": p05, "p95": p95, "d": d}}
    assert R.judge(b(0.1, 0.5, 0.3), b(0, 0, 0.2)) == "우위"
    assert R.judge(b(0.1, 0.5, 0.3), b(0, 0, -0.2)) == "검증만"
    assert R.judge(b(-0.5, -0.1, -0.3), b(0, 0, 0.2)) == "기준이 낫다"
    assert R.judge(b(-0.1, 0.2, 0.0), b(0, 0, 0.2)) == "가려지지 않음"


_SB = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
                   "_workspace/analysis/regime_v2_20261006/scoreboard_entries.json")


@pytest.mark.skipif(not (os.path.exists(R.PARQUET) and os.path.exists(V.BREADTH_CACHE)
                         and os.path.exists(V.ARCHIVE)), reason="보관소·시장 폭 캐시 없음")
def test_korea_reproduction_matches_scoreboard_curve():
    m = V.load_mkt()
    f = V.features(m)
    expo = R.expo_of(V.rule_keys(f, R.RULE_RA), R.MAP_RA)
    a, b = V.RA.win_ab(m, V.RG.FULL)
    v = GB.simulate(m, R.schedule(m, expo, a, b, *R.cols("K200")), a, b).value[a:b + 1]
    ent = next(e for e in json.load(open(_SB))["entries"] if e["id"] == "R2_IDX_ra")
    cum = np.asarray(ent["curve"]["cum"], float)
    assert len(cum) == len(v)
    assert np.max(np.abs(v / v[0] / cum - 1)) < 1e-9
