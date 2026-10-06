"""6장세 튜닝 연구 — 순수 함수 단위 테스트(사전 등록 regime/prereg.md 의 규칙 꼴)."""
import numpy as np
import pandas as pd

from tools.replay import opt_regime as R


def test_hyst_matches_label_module_shape():
    # 횡보 → +3% 넘으면 상승, +1% 밑이면 풀림, 풀리는 날 −3% 밑이면 곧장 하락
    x = [0.0, 0.031, 0.02, 0.009, -0.031, -0.02, -0.009, 0.05, -0.05]
    assert R.hyst(x, 0.03, 0.01) == ["S", "U", "U", "S", "D", "D", "S", "U", "D"]


def test_hyst_nan_keeps_state():
    assert R.hyst([0.05, float("nan"), 0.02], 0.03, 0.01) == ["U", None, "U"]


def test_hyst_vol_band():
    assert R.hyst_vol([0.15, 0.21, 0.18, 0.15, 0.19], 0.20, 0.16) == ["L", "H", "H", "L", "L"]


def test_confirm_needs_n_consecutive():
    raw = ["U", "U", "S", "U", "U", "U", "D", "D"]
    assert R.confirm(raw, 3) == ["S", "S", "S", "S", "S", "U", "U", "U"]


def test_truth_dir_centered_window():
    c = pd.Series(np.r_[np.full(30, 100.0), np.full(30, 110.0)], index=pd.bdate_range("2021-01-01", periods=60))
    t = R.truth_dir(c, half=20, thr=0.05)
    assert t.iloc[:20].isna().all() and t.iloc[-20:].isna().all()
    assert t.iloc[29] == "U"           # 100 → 110 을 가로지름
    assert t.iloc[20] == "S" or t.iloc[20] == "U"


def test_session_label_is_shifted_one_day():
    c = pd.Series([1.0, 2.0, 3.0], index=pd.bdate_range("2021-01-01", periods=3))
    lab = R.session_label(c, ["U", "D", "S"], ["L", "H", "L"])
    assert lab.iloc[0] is None or pd.isna(lab.iloc[0])
    assert lab.iloc[1] == "UL" and lab.iloc[2] == "DH"


def test_zigzag_and_lags():
    v = np.r_[np.linspace(100, 120, 21), np.linspace(119, 96, 24), np.linspace(97, 115, 19)]
    c = pd.Series(v, index=pd.bdate_range("2021-01-01", periods=len(v)))
    z = R.zigzag(c, 0.10)
    assert [k for _, k in z] == ["T", "P", "T"]
    assert z[1][0] == c.index[20]
    lab = pd.Series(["U"] * 25 + ["S"] * 5 + ["D"] * (len(v) - 30), index=c.index)
    lg = R.turn_lags(lab, z, c.index[0], c.index[-1])
    p = [x for x in lg if x["kind"] == "P"][0]
    assert p["leave"] == 5 and p["enter"] == 10 and not p["enter_miss"]


def test_balanced_acc_class_mean():
    t = pd.Series(["U"] * 8 + ["D"] * 2)
    p = pd.Series(["U"] * 10)
    assert R.balanced_acc(p, t) == 0.5
