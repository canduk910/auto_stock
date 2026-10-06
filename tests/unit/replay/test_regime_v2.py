"""장세 판단 재설계 — 해석표 · 후보 규칙 · 칸 학습 · 일정(데이터 없이)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import global_alloc_b as GB  # noqa: E402
from replay import regime_v2 as V  # noqa: E402


def _mkt(n=300, k_ret=0.0, l_ret=0.0, c_ret=0.0):
    dates = pd.bdate_range("2000-01-03", periods=n)
    ret = np.zeros((n, GB.N))
    ret[:, V.I_K] = k_ret
    ret[:, V.I_L] = l_ret
    ret[:, GB.I_CASH] = c_ret
    return GB.Mkt(dates, ret, np.zeros((n, GB.N)), np.full(n, 1 / 365), np.zeros(GB.N, bool), np.zeros(GB.N))


def test_ga_and_na_maps_match_prereg_tables():
    assert V.M_GA == {"UL": 2.0, "UH": 1.0, "SL": 1.0, "SH": 0.5, "DL": 0.5, "DH": 0.0}
    assert V.M_NA == {"UL": 1.0, "UH": 0.5, "SL": 2.0, "SH": 0.0, "DL": 1.0, "DH": 0.5}
    assert {c for c in V.CELLS if V.allow_of(V.M_GA[c])} == {"UL", "UH", "SL"}
    assert {c for c in V.CELLS if V.allow_of(V.M_NA[c])} == {"UL", "SL", "DL"}


def test_next_is_one_six_cycle():
    seen, x = [], "UL"
    for _ in range(6):
        seen.append(x)
        x = V.NEXT[x]
    assert x == "UL" and sorted(seen) == sorted(V.CELLS)


def test_candidates_count_and_order():
    c = V.candidates()
    assert len(c) == 145 <= 300
    assert c[0] == (("T1", ">", 0.0),)
    assert c[9] == (("R1", ">=", 0.16),)
    assert len(c[19]) == 2 and c[19][0][0] == "T1" and c[19][1][0] == "R1"


def test_rule_keys_missing_is_false():
    f = pd.DataFrame({"T1": [np.nan, 0.1, -0.1], "R1": [0.3, np.nan, 0.1]})
    k = V.rule_keys(f, (("T1", ">", 0.0), ("R1", ">=", 0.2)))
    assert list(k) == ["01", "10", "00"]


def test_learn_index_picks_growth_max_and_defaults_small_cells():
    m = _mkt(k_ret=0.001, l_ret=0.002 - 0.00001)
    keys = np.array(["a"] * 250 + ["b"] * 50, dtype=object)
    lr = V.learn_index(m, keys, win=(str(m.dates[1].date()), str(m.dates[-1].date())))
    assert lr["map"]["a"] == 2.0
    assert lr["map"]["b"] == 1.0 and lr["detail"]["b"]["default"]


def test_learn_index_tie_takes_lower_exposure():
    m = _mkt()
    keys = np.array(["a"] * 300, dtype=object)
    lr = V.learn_index(m, keys, win=(str(m.dates[1].date()), str(m.dates[-1].date())))
    assert lr["map"]["a"] == 0.0


def test_weights_and_schedule_change_days():
    assert V.weights(2.0)[V.I_L] == 1.0 and V.weights(2.0).sum() == 1.0
    w = V.weights(0.5)
    assert w[V.I_K] == 0.5 and w[GB.I_CASH] == 0.5
    m = _mkt(n=60)
    expo = np.r_[np.ones(30), np.zeros(30)]
    sc = V.schedule(m, expo, 0, 59)
    assert 30 in sc and sc[30][GB.I_CASH] == 1.0 and 0 in sc


def test_session_keys_shift_one_close():
    dates = pd.bdate_range("2020-01-01", periods=4)
    keys = np.array(["a", "b", "c", "d"], dtype=object)
    cal = pd.DatetimeIndex([dates[0], dates[2], pd.Timestamp("2020-01-04")])
    assert list(V.session_keys_on(cal, dates, keys)) == [None, "b", None]
    assert list(V.allow_on(np.array([None, "a", "b"], dtype=object), {"a": False})) == [True, False, True]
