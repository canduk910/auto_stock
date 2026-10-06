"""(라) 미국 이식 + 무료 시장 폭 대용 — 대용 폭 계산 · 분위 문턱(학습 구간만) · 정렬 · t+1 집행 · 재현 일치."""
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
from replay import ra_us_breadth as B  # noqa: E402
from replay import ra_us_breadth_data as D  # noqa: E402
from replay import regime_v2 as V  # noqa: E402

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_ar60_is_rolling_mean_of_advance_share():
    idx = pd.bdate_range("2001-01-01", periods=80)
    adv = pd.Series(np.arange(80, dtype=float) + 1, index=idx)
    dec = pd.Series(np.full(80, 50.0), index=idx)
    s = D.ar_n(adv, dec, 60)
    share = adv / (adv + dec)
    assert s.index[0] == idx[59]                                # 60 개가 차야 첫 값
    assert s.iloc[-1] == pytest.approx(share.iloc[-60:].mean())
    assert ((s > 0) & (s < 1)).all()


def test_ar60_does_not_use_future_rows():
    idx = pd.bdate_range("2001-01-01", periods=100)
    adv = pd.Series(np.full(100, 10.0), index=idx)
    dec = pd.Series(np.full(100, 10.0), index=idx)
    base = D.ar_n(adv, dec)
    adv2 = adv.copy()
    adv2.iloc[90:] = 1000.0                                     # 미래만 바꾼다
    after = D.ar_n(adv2, dec)
    assert (base.loc[:idx[89]] == after.loc[:idx[89]]).all()


def test_adl_gap_sign():
    idx = pd.bdate_range("2001-01-01", periods=80)
    up = D.adl_gap(pd.Series(np.full(80, 20.0), index=idx), pd.Series(np.full(80, 10.0), index=idx))
    dn = D.adl_gap(pd.Series(np.full(80, 10.0), index=idx), pd.Series(np.full(80, 20.0), index=idx))
    assert (up > 0).all() and (dn < 0).all()


def test_ew_gap_detects_equal_weight_lagging():
    idx = pd.bdate_range("2001-01-01", periods=100)
    cw = pd.Series(np.full(100, 100.0), index=idx)
    ew = pd.Series(np.r_[np.full(90, 100.0), np.linspace(99, 90, 10)], index=idx)
    g = D.ew_gap(ew, cw, 60)
    assert g.loc[idx[80]] == pytest.approx(0.0)
    assert g.iloc[-1] < 0                                       # 동일가중이 뒤처지면 음수(좁은 시장)


def test_above_ma_share_matches_korean_definition():
    idx = pd.bdate_range("2001-01-01", periods=70)
    px = pd.DataFrame({"a": np.linspace(1, 2, 70), "b": np.linspace(2, 1, 70), "c": np.r_[np.full(30, np.nan),
                                                                                          np.linspace(1, 2, 40)]},
                      index=idx)
    s = D.above_ma_share(px, 60)
    assert s.iloc[-1] == pytest.approx(0.5)                     # c 는 60일 평균이 아직 없어 분모 밖
    assert s.index[0] == idx[59]


def test_threshold_uses_training_window_only():
    dates = pd.bdate_range("2008-01-01", "2016-12-30")
    x = pd.Series(np.where(dates <= pd.Timestamp("2012-12-28"), 0.5, -100.0), index=dates)
    x.iloc[:10] = 0.1
    win = ("1995-01-03", "2012-12-28")
    t1 = B.train_threshold(x, 0.001, win)
    x2 = x.copy()
    x2[dates > pd.Timestamp("2012-12-28")] = 1e6                # 학습 뒤 값을 바꿔도
    assert B.train_threshold(x2, 0.001, win) == t1              # 문턱은 그대로
    assert t1 == pytest.approx(0.1)
    vals = x[(dates >= pd.Timestamp(win[0])) & (dates <= pd.Timestamp(win[1]))]
    assert B.train_threshold(x, 0.3, win) == pytest.approx(np.quantile(vals, 0.3))


def test_threshold_ignores_missing_before_data_start():
    dates = pd.bdate_range("2005-01-03", "2012-12-28")
    x = pd.Series(np.nan, index=dates)
    x[dates >= pd.Timestamp("2007-01-02")] = np.linspace(0, 1, int((dates >= pd.Timestamp("2007-01-02")).sum()))
    thr = B.train_threshold(x, 0.25)
    assert thr == pytest.approx(0.25, abs=1e-3)


def test_missing_proxy_means_breadth_healthy_and_cells_follow_original_map():
    f = pd.DataFrame({"T7": [0.01, -0.01, 0.01, -0.01, 0.01], "BX": [np.nan, np.nan, 0.1, 0.1, 0.9]})
    keys = V.rule_keys(f, B.rule_of(0.3))
    assert list(keys) == ["10", "00", "11", "01", "10"]
    assert list(R.expo_of(keys, R.MAP_RA)) == [2.0, 0.0, 0.0, 1.0, 2.0]


def test_aligned_uses_strictly_previous_us_value():
    us = pd.Series([0.1, 0.2, 0.3], index=pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"]))
    krx = pd.DatetimeIndex(["2020-01-03", "2020-01-06", "2020-01-07"])
    assert list(B.aligned(us, krx)) == [0.1, 0.2, 0.3]


def test_t_plus_1_execution_with_breadth_expo():
    n = 40
    dates = pd.bdate_range("2000-01-03", periods=n)
    ix, il = R.cols("SPX")
    ret = np.zeros((n, GB.N))
    ret[11, ix] = 0.5
    ret[12, ix] = 0.1
    m = GB.Mkt(dates, ret, np.zeros((n, GB.N)), np.full(n, 1 / 365), np.zeros(GB.N, bool), np.zeros(GB.N))
    f = pd.DataFrame({"T7": np.r_[np.full(10, 0.01), np.full(30, -0.01)],
                      "BX": np.r_[np.full(10, 0.9), np.full(30, 0.1)]}, index=dates)
    expo = R.expo_of(V.rule_keys(f, B.rule_of(0.3)), R.MAP_RA)    # t=10 부터 01 → 1배
    assert expo[9] == 2.0 and expo[10] == 1.0
    e = np.where(expo == 2.0, 0.0, expo)                          # 2배 열 0 수익 → 앞 구간 0
    sim = GB.simulate(m, R.schedule(m, e, 0, n - 1, ix, il), 0, n - 1, cost_one_way=0.0)
    assert sim.value[11] == pytest.approx(1.0)                    # 집행일 당일 급등은 못 잡는다
    assert sim.value[12] == pytest.approx(1.1)


def test_plan_lists_and_bonferroni():
    assert len(B.MAIN_PLANS) == 6 and B.N_BONF == 6 * 4
    assert set(B.PROXIES) == {"P0", "P1", "P2"}


@pytest.mark.skipif(not os.path.exists(os.path.join(D.BR, "tv_INDEX_S5FI.json")), reason="원자료 없음")
def test_real_proxies_ranges():
    s = D.p0("SPX")
    assert s.between(0, 1).all() and str(s.index.min().date()) <= "2007-01-02"
    a, d = D.ad_counts("SPX")
    assert (a + d > 0).all() and a.index.is_monotonic_increasing
    assert a.index.min() < pd.Timestamp("1995-01-01") and a.index.max() > pd.Timestamp("2026-09-01")
    p1 = D.p1("NDX")
    assert p1.between(0, 1).all()


@pytest.mark.skipif(not (os.path.exists(R.PARQUET) and os.path.exists(os.path.join(D.BR, "tv_INDEX_S5FI.json"))),
                    reason="보관소 없음")
def test_reproduces_raus_no_breadth_curve():
    df = pd.read_parquet(R.PARQUET)
    m = GB.load(df, "U")
    f = R.us_features("SPX", m.dates)
    expo = R.expo_of(V.rule_keys(f, R.RULE_RA), R.MAP_RA)
    run = R.Runner(m, "SPX", {"FULL": R.US_WINS["FULL"]}, R.US_ERAS)
    run.run_expo("A", expo)
    assert B.reproduce_A(run, "SPX", "U") < 1e-9
    ent = json.load(open(os.path.join(_ROOT, B.SB_RAUS)))
    assert any(e["id"] == "RAUS_SPX_U_A" for e in ent["entries"])
