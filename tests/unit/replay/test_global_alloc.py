"""여러 나라 자산배분 연구 도구 — 미래 정보 차단 · 집행 지연 · 비용 · 세금 · 채권 수익 모형."""
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
from replay import global_alloc_data as D  # noqa: E402


def _df(T: int = 900, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=T)
    out = {}
    for a in G.RISKY:
        r = rng.normal(0.0003, 0.01, T)
        out[f"{a}_ret"] = r
        out[f"{a}_hret"] = r * 0.9
        out[f"{a}_lret"] = r
    out["CASH_ret"] = np.full(T, 0.0001)
    for a in G.EQUITY:
        out[f"{a}_px_local"] = 100 * np.cumprod(1 + out[f"{a}_ret"])
    out["fx_usdkrw"] = 1000 * np.cumprod(1 + out["USD_ret"])
    return pd.DataFrame(out, index=idx)


def test_par_bond_no_yield_change_earns_carry_only():
    y = np.array([0.05])
    r = D.par_bond_return(y, y, np.array([1 / 365]))
    assert r[0] == pytest.approx(0.05 / 365, abs=1e-12)


def test_par_bond_yield_up_loses_about_duration():
    r = D.par_bond_return(np.array([0.04]), np.array([0.05]), np.array([0.0]))
    assert -0.085 < r[0] < -0.07          # 10년 액면채 수정듀레이션 ≈ 8


@pytest.mark.parametrize("fam", ["F1", "F2", "F3", "F4", "F5", "F6"])
def test_weights_do_not_use_future_data(fam):
    df = _df()
    m1 = G.load_market(df)
    i = 600
    df2 = df.copy()
    df2.iloc[i + 1:, :] = df2.iloc[i + 1:, :].abs() * 1.7      # 미래만 훼손(가격은 양수 유지)
    m2 = G.load_market(df2)
    for p in G.GRID[fam]:
        np.testing.assert_allclose(G.weights(m1, fam, p, i), G.weights(m2, fam, p, i))


@pytest.mark.parametrize("fam", ["F1", "F2", "F3", "F4", "F5", "F6"])
def test_weights_sum_to_one_and_nonnegative(fam):
    m = G.load_market(_df())
    for p in G.GRID[fam]:
        for i in (100, 400, 800):
            w = G.weights(m, fam, p, i)
            assert w.sum() == pytest.approx(1.0)
            assert (w >= -1e-12).all()


def test_execution_is_next_close_and_cost_charged():
    df = _df(300)
    m = G.load_market(df)
    m.fee[:] = 0.0
    w = np.zeros(G.NA)
    w[0] = 1.0
    res = G.simulate(m, {10: w}, start=5)
    # 결정 10 → 11 종가 집행. 11 까지는 현금 수익만.
    cash = np.prod(1 + m.ret[6:12, G.I_CASH])
    assert res.value[11] == pytest.approx(cash * (1 - G.COST_ONE_WAY))
    # 12 일은 K200 수익을 탄다
    assert res.value[12] == pytest.approx(res.value[11] * (1 + m.ret[12, 0]))
    assert res.turnover[11] == pytest.approx(1.0)


def test_tax_reduces_value_only_on_gains():
    df = _df(400)
    df["SPX_ret"] = 0.002            # 계속 오른다 → 차익 과세
    m = G.load_market(df)
    w1 = np.zeros(G.NA)
    w1[1] = 1.0
    w2 = np.zeros(G.NA)
    w2[G.I_CASH] = 1.0
    sched = {10: w1, 200: w2}
    pre = G.simulate(m, sched, 5).value[-1]
    post = G.simulate(m, sched, 5, tax=True)
    assert post.value[-1] < pre
    assert post.tax_paid > 0


def test_walk_forward_pick_ignores_the_year_it_trades():
    df = _df(3000, seed=3)
    df.index = pd.bdate_range("1995-01-03", periods=3000)
    m1 = G.load_market(df)
    old = G.OOS_START
    G.OOS_START = 2005
    try:
        GRID_SAVE = dict(G.GRID)
        for f in G.FAMILIES:
            G.GRID[f] = G.GRID[f][:2]
        w1 = G.walk_forward(m1, "M", 0, 2005)
        df2 = df.copy()
        df2.loc[df2.index.year >= 2005, :] = df2.loc[df2.index.year >= 2005, :].abs() * 1.7
        w2 = G.walk_forward(G.load_market(df2), "M", 0, 2005)
        assert w1["picks"]["W"][2005] == w2["picks"]["W"][2005]
    finally:
        G.OOS_START = old
        G.GRID.update(GRID_SAVE)


def test_decision_points_month_end_and_exec_exists():
    idx = pd.bdate_range("2001-01-01", "2001-03-31")
    dp = G.decision_points(idx, "M")
    assert [str(idx[i].date()) for i in dp] == ["2001-01-31", "2001-02-28"]   # 3월 말은 집행일이 없어 빠진다
