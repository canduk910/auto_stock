"""여러 나라 자산배분 2차 — 일일 2배 수익 모형 · 밴드 재조정 · 위험 동일 기여 · 미래 정보 차단."""
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
from replay import global_alloc_b as B  # noqa: E402


def _df(T: int = 600, seed: int = 3, fx: float = 0.0, cash: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=T)
    out = {}
    for a in G.RISKY:
        rl = rng.normal(0.0003, 0.01, T)
        out[f"{a}_lret"] = rl
        out[f"{a}_ret"] = (1 + rl) * (1 + fx) - 1
        out[f"{a}_hret"] = rl
    out["CASH_ret"] = np.full(T, cash)
    return pd.DataFrame(out, index=idx)


def test_lev_U_is_twice_local_when_no_fx_rates_costs():
    df = _df()
    lv = B.lev_returns(df, "U", 0.0)
    np.testing.assert_allclose(lv["LSPX"][1:], 2 * df["SPX_lret"].to_numpy()[1:], atol=1e-12)
    np.testing.assert_allclose(lv["LK200"][1:], 2 * df["K200_ret"].to_numpy()[1:], atol=1e-12)


def test_lev_U_carries_fx_once_H_does_not():
    df = _df(fx=0.001)
    u = B.lev_returns(df, "U", 0.0)["LNDX"][1:]
    h = B.lev_returns(df, "H", 0.0)["LNDX"][1:]
    rl = df["NDX_lret"].to_numpy()[1:]
    np.testing.assert_allclose(u, (1 + 2 * rl) * 1.001 - 1, atol=1e-12)
    np.testing.assert_allclose(h, 2 * rl, atol=1e-12)


def test_lev_cost_and_financing_reduce_return():
    df = _df(cash=0.0001)
    lv = B.lev_returns(df, "U", 0.008)["LK200"][1:]
    r = df["K200_ret"].to_numpy()[1:]
    dt = pd.Series(df.index, index=df.index).diff().dt.days.to_numpy()[1:] / 365
    np.testing.assert_allclose(lv, 2 * r - 0.0001 - 0.008 * dt, atol=1e-12)


def test_volatility_drag_appears_in_flat_market():
    """오르내림만 있고 지수는 제자리 → 2배 상품은 잃는다(일별 재설정)."""
    T = 401
    rl = np.tile([0.05, -0.05 / 1.05], 200)
    df = _df(T=T)
    df.loc[:, "K200_ret"] = np.concatenate([[0.0], rl])
    lv = B.lev_returns(df, "U", 0.0)["LK200"]
    assert np.prod(1 + df["K200_ret"]) == pytest.approx(1.0)
    assert np.prod(1 + lv) < 0.7


def test_band_rebalances_only_when_drift_exceeds_5pp():
    df = _df()
    m = B.load(df)
    m.ret[:] = 0.0
    m.fee[:] = 0.0
    m.ret[300, 0] = 0.30        # K200 +30% 하루 → 비중 14.3% → 17.8% (+3.5%p, 밴드 안)
    s = B.simulate(m, "band", 0, len(df) - 1)
    assert s.n_trades == 1
    m.ret[400, 0] = 0.40        # 누적 → 22% 넘음 → 이탈
    s = B.simulate(m, "band", 0, len(df) - 1)
    assert s.n_trades == 2


def test_erc_equalizes_risk_contribution():
    rng = np.random.default_rng(0)
    A = rng.normal(size=(7, 7))
    cov = A @ A.T / 7 + np.diag(np.linspace(0.01, 0.2, 7))
    w = B.erc_weights(cov)
    rc = w * (cov @ w)
    assert w.sum() == pytest.approx(1.0)
    assert (w > 0).all()
    assert rc.max() / rc.min() == pytest.approx(1.0, abs=1e-6)


def test_erc_does_not_use_future():
    df = _df()
    m1 = B.load(df)
    df2 = df.copy()
    df2.iloc[301:] = df2.iloc[301:] * 3
    m2 = B.load(df2)
    np.testing.assert_allclose(B.erc_at(m1, 300), B.erc_at(m2, 300))


@pytest.mark.parametrize("nm", ["B", "B-EQ", "LEV1", "LEV2a", "LEV2b", "LEV3", "LEV4", "B0", "B1"])
def test_targets_sum_to_one(nm):
    assert B.target(nm).sum() == pytest.approx(1.0)


def test_lev2a_exposure_equals_plain():
    w = B.target("LEV2a")
    expo = w[:7] + 2 * w[[B.COLS.index(x) for x in B.LEV]]
    np.testing.assert_allclose(expo, np.full(7, 1 / 7))


def test_execution_is_next_close():
    df = _df()
    m = B.load(df)
    m.fee[:] = 0.0
    s = B.simulate(m, {10: B.target("B0")}, 10, 20)
    assert s.value[11] == pytest.approx(1 + m.ret[11, B.I_CASH] - 0.0019)   # 11일 종가에 매수(그날 수익은 현금)
