"""금 투자 추가 — 원화 환산 · 환헤지 · 일일 2배 · 리밸런싱 · 위험 균형 · 걷기 전진 일반화."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402
from replay import gold_alloc as A  # noqa: E402


def _base(T: int = 400, seed: int = 5, fx_step: float = 0.0, r_kr: float = 0.0, r_us: float = 0.0) -> pd.DataFrame:
    """global_daily_krw 와 같은 열 모양의 합성 계열."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2001-01-02", periods=T)
    out = {}
    for a in G.RISKY:
        rl = rng.normal(0.0003, 0.01, T)
        rl[0] = 0.0
        out[f"{a}_lret"] = rl
        out[f"{a}_ret"] = (1 + rl) * (1 + fx_step) - 1
        out[f"{a}_hret"] = rl
    for a in G.EQUITY:
        out[f"{a}_px_local"] = 100 * np.cumprod(1 + out[f"{a}_lret"])
    out["CASH_ret"] = np.zeros(T)
    out["r_kr"] = np.full(T, r_kr)
    out["r_us"] = np.full(T, r_us)
    out["fx_usdkrw"] = 1000 * (1 + fx_step) ** np.arange(T)
    out["y10"] = np.full(T, 0.04)
    return pd.DataFrame(out, index=idx)


def _gold(df: pd.DataFrame, seed: int = 9) -> pd.Series:
    rng = np.random.default_rng(seed)
    days = pd.date_range(df.index[0] - pd.Timedelta(days=5), df.index[-1], freq="D")
    return pd.Series(300 * np.cumprod(1 + rng.normal(0, 0.01, len(days))), index=days)


def test_align_uses_strictly_earlier_observation():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2001-01-01", "2001-01-02", "2001-01-03"]))
    got = A.align_before(s, pd.DatetimeIndex(pd.to_datetime(["2001-01-02", "2001-01-03", "2001-01-05"])))
    assert got.tolist() == [1.0, 2.0, 3.0]          # D 의 값 = D 보다 앞선 마지막 관측


def test_unhedged_is_gold_times_fx():
    df = _base(fx_step=0.002)
    gc = A.gold_columns(df, _gold(df))
    exp = (1 + gc["GOLD_lret"]) * 1.002 - 1
    np.testing.assert_allclose(gc["GOLD_ret"].to_numpy()[1:], exp.to_numpy()[1:], atol=1e-12)
    assert gc["GOLD_ret"].iloc[0] == 0.0


def test_hedged_adds_rate_differential_not_fx():
    df = _base(fx_step=0.002, r_kr=0.05, r_us=0.02)
    gc = A.gold_columns(df, _gold(df))
    dt = pd.Series(df.index, index=df.index).diff().dt.days.to_numpy()[1:] / 365.0
    np.testing.assert_allclose((gc["GOLD_hret"] - gc["GOLD_lret"]).to_numpy()[1:], 0.03 * dt, atol=1e-12)


def test_gold_columns_rejects_missing_prices():
    df = _base()
    g = _gold(df)
    with pytest.raises(ValueError):
        A.gold_columns(df, g[g.index > df.index[10]])


def test_lev2_is_twice_when_no_rates_fx_costs():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, 50)
    z = np.zeros(50)
    dt = np.full(50, 1 / 365)
    for k in ("U", "H"):
        x = A.lev2(r, r, r, z, dt, k, c=0.0)
        np.testing.assert_allclose(x[1:], 2 * r[1:], atol=1e-12)
        assert x[0] == 0.0


def test_lev2_U_carries_fx_once_and_matches_global_formula():
    rng = np.random.default_rng(2)
    rl = rng.normal(0, 0.01, 60)
    fx = 0.001
    ret = (1 + rl) * (1 + fx) - 1
    cash = np.full(60, 0.0001)
    hret = rl + 0.00005                      # rf = cash − (h − l) = 0.00005
    dt = np.full(60, 1 / 365)
    xu = A.lev2(rl, ret, hret, cash, dt, "U", c=0.008)
    exp = (1 + 2 * rl - 0.00005 - 0.008 / 365) * (1 + fx) - 1
    np.testing.assert_allclose(xu[1:], exp[1:], atol=1e-12)
    xh = A.lev2(rl, ret, hret, cash, dt, "H", c=0.008)
    np.testing.assert_allclose(xh[1:], (2 * rl - 0.00005 - 0.008 / 365 + 0.00005)[1:], atol=1e-12)


def test_lev2_floor_at_minus_one():
    r = np.array([0.0, -0.7])
    x = A.lev2(r, r, r, np.zeros(2), np.full(2, 1 / 365), "U", c=0.0)
    assert x[1] == -1.0


def test_generic_engine_matches_global_b_for_60_40():
    df = _base(T=500)
    gb = GB.load(df, "U")
    m = A.build_mkt(df, G.RISKY)
    a, b = 21, 480
    s_gb = GB.schedule(gb, "B1", a, b)
    s_me = A.static_schedule(m, A.wvec(m, {"K200": 0.6, "UST10": 0.4}), a, b, "M")
    assert sorted(s_gb) == sorted(s_me)
    for tax in (False, True):
        vg = GB.simulate(gb, s_gb, a, b, tax=tax).value
        vm = A.simulate(m, s_me, a, b, tax=tax).value
        np.testing.assert_allclose(vm[a:b + 1], vg[a:b + 1], rtol=1e-12)


def test_rebalance_restores_target_and_charges_cost():
    idx = pd.bdate_range("2001-01-01", periods=6)
    m = A.AMkt(idx, ("X", "CASH"), np.array([[0, 0], [0, 0], [0.10, 0], [0, 0], [0, 0], [0, 0]], float),
               np.zeros((6, 2)), np.full(6, 1 / 365), np.array([True, False]), np.zeros(2), np.ones((6, 1)))
    w = np.array([0.5, 0.5])
    sim = A.simulate(m, {0: w, 2: w}, 0, 5)
    v_after_buy = 1 - 0.5 * G.COST_ONE_WAY            # t=1 집행: 위험 몫 0.5 회전
    assert sim.value[1] == pytest.approx(v_after_buy)
    v2 = v_after_buy * (0.5 * 1.10 + 0.5)              # t=2 수익
    assert sim.value[2] == pytest.approx(v2)
    cur = 0.5 * 1.10 / (0.5 * 1.10 + 0.5)
    v3 = v2 * (1 - abs(cur - 0.5) * G.COST_ONE_WAY)    # t=3 되돌림 비용
    assert sim.value[3] == pytest.approx(v3)
    assert sim.n_trades == 2


def test_quarterly_schedule_includes_start_and_quarter_ends():
    idx = pd.bdate_range("2001-01-01", "2001-12-31")
    m = A.AMkt(idx, ("X", "CASH"), np.zeros((len(idx), 2)), np.zeros((len(idx), 2)), np.zeros(len(idx)),
               np.zeros(2, bool), np.zeros(2), np.ones((len(idx), 1)))
    s = A.static_schedule(m, np.array([1.0, 0.0]), 5, len(idx) - 1, "Q")
    ds = [idx[i] for i in sorted(s)]
    assert ds[0] == idx[5]
    assert [d.month for d in ds[1:]] == [3, 6, 9]


def test_inv_vol_weights_risky_share_and_inverse_order():
    T = 300
    rng = np.random.default_rng(4)
    r = np.column_stack([rng.normal(0, 0.01, T), rng.normal(0, 0.02, T), rng.normal(0, 0.04, T), np.zeros(T)])
    idx = pd.bdate_range("2001-01-01", periods=T)
    m = A.AMkt(idx, ("A", "B", "C", "CASH"), r, np.zeros_like(r), np.zeros(T), np.zeros(4, bool), np.zeros(4),
               np.ones((T, 3)))
    w = A.inv_vol_weights(m, T - 1)
    assert w[:3].sum() == pytest.approx(0.75)
    assert w[3] == pytest.approx(0.25)
    assert w[0] > w[1] > w[2]
    w0 = A.inv_vol_weights(m, 100)                       # 252일 미만 = 균등
    np.testing.assert_allclose(w0, [0.25, 0.25, 0.25, 0.25])


@pytest.mark.parametrize("fam", ["F1", "F2", "F3", "F4", "F5", "F6"])
def test_generic_weights_match_global_alloc_for_seven_assets(fam):
    df = _base(T=420, seed=11)
    gm = G.load_market(df)
    am = A.build_mkt(df, G.RISKY)
    for p in G.GRID[fam][::3]:
        for i in (300, 380, 419):
            np.testing.assert_allclose(A.weights(am, fam, p, i), G.weights(gm, fam, p, i), atol=1e-12)


def test_weights_without_ust_fall_back_to_cash():
    df = _base(T=420, seed=12)
    df = df.join(A.gold_columns(df, _gold(df)))
    am = A.build_mkt(df, ("NDX", "GOLD"))
    for p in G.GRID["F1"]:
        w = A.weights(am, "F1", p, 400)
        assert w.sum() == pytest.approx(1.0)
        assert set(np.nonzero(w)[0]) <= {0, 1, 2}


def test_window_return_uses_value_before_window():
    d = pd.to_datetime(["1999-12-30", "2000-06-30", "2002-12-30", "2003-01-02"])
    v = np.array([1.0, 0.8, 0.5, 0.6])
    assert A.window_return(pd.DatetimeIndex(d), v, "2000-01-01", "2002-12-31") == pytest.approx(-0.5)
    assert A.window_return(pd.DatetimeIndex(d), v, "1997-01-01", "1997-12-31") is None
