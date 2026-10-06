"""30년 재검증(etf_trend · 바탕 층) — 데이터 층 · 계좌 · 부트스트랩의 순수 함수 테스트."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import base_layer as BL  # noqa: E402
from replay import y30_etfbase_data as YD  # noqa: E402
from replay import y30_etfbase_run as R  # noqa: E402


def _costs():
    return pd.DataFrame({"from": pd.to_datetime(["1996-01-01", "1999-07-01"]),
                         "to": pd.to_datetime(["1999-06-30", None]).fillna(pd.Timestamp("2100-01-01")),
                         "round_trip_pct_assumed": [1.3, 0.5], "fee_one_way_pct_assumed": [0.5, 0.1]})


def test_cost_rt_on_regimes_and_warmup():
    d = pd.to_datetime(["1995-06-01", "1998-01-05", "2001-01-02"])
    assert np.allclose(YD.cost_rt_on(d, _costs(), "table"), [0.013, 0.013, 0.005])
    assert np.allclose(YD.cost_rt_on(d, _costs(), "fee"), [0.010, 0.010, 0.002])
    assert np.allclose(YD.cost_rt_on(d, _costs(), "const"), 0.0038)


def test_caldays_counts_calendar_days_not_bars():
    cal = pd.DatetimeIndex(pd.to_datetime(["1997-01-03", "1997-01-04", "1997-01-06"]))   # 금 · 토 · 월
    assert list(YD.caldays(cal)) == [0.0, 1.0, 2.0]


def test_proxy_cash_compounds_by_calendar_days():
    cal = pd.DatetimeIndex(pd.date_range("2000-01-01", periods=366, freq="D"))
    p = YD.proxy_cash(cal, np.full(366, 10.0))
    assert p[-1] == pytest.approx(1.10, rel=1e-3)


def test_chain_backward_splices_proxy_to_first_etf_close():
    cal = pd.DatetimeIndex(pd.date_range("2010-01-04", periods=6, freq="B"))
    etf = pd.DataFrame({"bas_dd": cal[3:], "open": [101.0, 102.0, 103.0], "close": [100.0, 110.0, 121.0],
                        "volume": [1, 1, 1], "no_trade": [False, False, False]})
    proxy = np.array([1.0, 2.0, 4.0, 8.0, 9.0, 10.0])
    O, Cl, src = YD.chain_backward(cal, etf, proxy, None)
    assert list(src) == [0, 0, 0, 1, 1, 1]
    assert Cl[3] == 100.0 and Cl[2] == pytest.approx(50.0) and Cl[0] == pytest.approx(12.5)
    assert O[1] == pytest.approx(Cl[0])            # 근사 구간 시가 = 전일 종가
    assert Cl[5] == 121.0 and O[4] == 102.0


def test_run_account30_matches_base_layer_with_const_cost_and_252():
    rng = np.random.default_rng(0)
    n = 300
    cal = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=n))
    px = 100 * np.cumprod(1 + rng.normal(0, 0.01, (n, 5)), axis=0)
    O, Cl = px * 0.999, px
    m = rng.choice([0.0, 0.5, 0.75, 1.0], size=n)
    dd = BL.drawdown60(Cl[:, 0])
    W = BL.weights_path({"fam": "B1", "park": "short", "R": "D", "band": 0.0}, cal, m, dd, Cl[:, 0])
    a = BL.run_account(W, O, Cl, 10, n - 1)
    b = R.run_account30(W, O, Cl, 10, n - 1, np.full(n, 0.0019), cal, ann="252")
    assert b["cagr"] == pytest.approx(a["cagr"], abs=1e-12)
    assert b["mdd"] == pytest.approx(a["mdd"], abs=1e-12)
    assert np.allclose(b["equity"], a["equity"])


def test_mar_paths30_equals_base_layer_when_years_are_bars_over_252():
    rng = np.random.default_rng(1)
    r = rng.normal(0.0005, 0.01, 500)
    idx = BL.boot_index(500, 50)
    assert np.allclose(R.mar_paths30(r, idx, 500 / 252.0), BL.mar_paths(r, idx), equal_nan=True)


def test_mar_diff_boot30_is_zero_for_identical_series_and_chunk_invariant():
    rng = np.random.default_rng(2)
    r = rng.normal(0.0003, 0.01, 400)
    assert np.nanmax(np.abs(R.mar_diff_boot30(r, r, 300, 1.6))) == 0.0
    r2 = r + 0.0002
    a = R.mar_diff_boot30(r2, r, 300, 1.6, chunk=300)
    b = R.mar_diff_boot30(r2, r, 300, 1.6, chunk=70)
    assert np.allclose(a, b, equal_nan=True)


def test_m1_only_path_uses_previous_close_m_and_fail_open():
    cal = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=4))
    m = np.array([np.nan, 1.0, 0.75, 1.0])
    W = R.m1_only_path(cal, m)
    assert list(W[:, 0]) == [1.0, 1.0, 1.0, 0.0]     # 세션 0 = 결손 1.0 · 세션 1 = m[0] NaN → 1.0
