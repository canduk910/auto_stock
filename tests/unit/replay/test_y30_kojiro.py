"""kojiro 30년 재검증(2026-10-06) — 시대 층 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_30y_20261006/kojiro/prereg.frozen.md`` §1·§3. 네트워크·DB 0.
비용·제한폭 표는 보관소 메타 csv(본 작업 트리)를 읽는다 — 없으면 그 테스트만 건너뛴다.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.strategies import kojiro as KJ  # noqa: E402
from replay.strategies import kojiro_opt as KO  # noqa: E402
from replay.strategies import kojiro_y30 as Y  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy  # noqa: E402

pytestmark = pytest.mark.unit

P = {**KojiroStrategy.DEFAULT_PARAMS, "breakeven_promote_atr": 1.5, "sizing_mode": "turtle",
     "position_ratio": 0.166, "max_positions": 6, "market_unit_mode": "enforce"}
HAS_META = os.path.exists(os.path.join(Y.ARCHIVE, "meta", "regime_costs.csv"))


def _bars(o, h, l, c, mkt=0):
    n = len(c)
    return {"di": np.arange(n), "o": np.asarray(o, float), "h": np.asarray(h, float), "l": np.asarray(l, float),
            "c": np.asarray(c, float), "o_raw": np.asarray(o, float), "c_raw": np.asarray(c, float),
            "raw": np.ones(n), "tv": np.full(n, 5e9), "vol": np.full(n, 1e5), "mktcap": np.full(n, 1e11),
            "mkt": np.full(n, mkt), "notrade": np.zeros(n, dtype=bool),
            "cap_pct": np.full(n, 0.9), "tv_pct": np.full(n, 0.9)}


def test_fast_ewm_matches_loop():
    rng = np.random.default_rng(1)
    x = rng.normal(100, 5, 300)
    first = x - 3
    for a in (2 / 6, 2 / 21, 1 / 20):
        assert np.allclose(Y.ewm_full_fast(x, a), _loop(x, a), atol=1e-9)
        assert np.allclose(Y.ewm_full_fast(x, a, first), _loop(x, a, first), atol=1e-9)


def _loop(x, alpha, first=None):
    out = np.empty(len(x))
    acc = np.nan
    for j in range(len(x)):
        acc = (first[j] if first is not None else x[j]) if j == 0 else (1 - alpha) * acc + alpha * x[j]
        out[j] = acc
    return out


def test_features_unchanged_by_fast_ewm():
    rng = np.random.default_rng(7)
    n = 260
    c = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.02, n)))
    b = _bars(c * 0.995, c * 1.01, c * 0.985, c)
    orig = KJ._ewm_full
    try:
        f0 = KJ.features(b, P)
        Y.patch_fast_ewm()
        f1 = KJ.features(b, P)
    finally:
        KJ._ewm_full = orig
    assert np.allclose(f0["atr"], f1["atr"], equal_nan=True)
    assert (f0["stage"] == f1["stage"]).all() and (f0["tech"] == f1["tech"]).all()


def test_cost_rt_buy_fee_sell_fee_tax():
    cal = pd.DatetimeIndex(["2000-01-04", "2000-01-05"])
    c = Y.Cost(np.array([0.001, 0.002]), np.array([0.003, 0.004]))
    assert c.rt(0, 1) == pytest.approx(0.001 + 0.002 + 0.004)
    assert c.rt(0, None) == pytest.approx(0.001 + 0.001 + 0.003)
    k = Y.const_cost(cal)
    assert k.rt(0, 1) == pytest.approx(0.0038)


@pytest.mark.skipif(not HAS_META, reason="보관소 메타 없음")
def test_era_tables_known_dates():
    cal = pd.DatetimeIndex(["1997-03-03", "2000-06-01", "2010-06-01", "2020-06-01", "2026-03-03"])
    c = Y.era_cost(cal)
    assert [round(c.rt(i, i) * 100, 3) for i in range(5)] == [1.3, 0.5, 0.36, 0.28, 0.23]
    lim = Y.limit_table(cal)
    assert lim[0].tolist() == [0.08, 0.15, 0.15, 0.30, 0.30]
    assert lim[1].tolist() == [0.08, 0.12, 0.15, 0.30, 0.30]


def test_locked_uses_era_limit():
    # 전일 100 · 시가=고가=저가=85 : 15% 시대는 잠김, 30% 시대는 잠김 아님
    b = _bars([100, 85], [100, 85], [100, 85], [100, 85])
    s = KJ.Sig("000001", 0, 0, 100.0, 100.0, 2.0, 1.0)
    ps = Y.Y30Pos(s, b, {"atr": np.full(2, 2.0), "stage": np.ones(2, np.int8)}, 1, P)
    Y.Y30Pos.LIM = np.array([[0.15, 0.15], [0.15, 0.15]])
    try:
        assert ps._locked(1)
        Y.Y30Pos.LIM = np.array([[0.30, 0.30], [0.30, 0.30]])
        assert not ps._locked(1)
    finally:
        Y.Y30Pos.LIM = None


def test_universe_era_percentile_and_price():
    b = _bars([5000] * 4, [5000] * 4, [5000] * 4, [5000, 5000, 2000, 5000])
    b["cap_pct"] = np.array([0.9, 0.2, 0.9, 0.9])
    b["tv_pct"] = np.array([0.9, 0.9, 0.9, 0.5])
    u = Y.universe_era(b)
    assert u.tolist() == [True, False, False, False]     # 시총 하위 · 가격 < 3000 · 거래대금 하위


def test_add_pct_cross_section():
    df = pd.DataFrame({"bas_dd": pd.to_datetime(["2000-01-04"] * 4 + ["2000-01-05"] * 2),
                       "mktcap": [1, 2, 3, 4, 10, 5], "trade_value": [4, 3, 2, 1, 0, 0]})
    out = Y.add_pct(df)
    assert out.cap_pct.tolist() == [0.25, 0.5, 0.75, 1.0, 1.0, 0.5]
    assert out.tv_pct.tolist()[-2:] == [0.75, 0.75]


def test_run_book30_reconciles_with_era_cost():
    n = 30
    c = np.linspace(100, 130, n)
    b = _bars(c, c * 1.01, c * 0.99, c)
    cal = pd.bdate_range("2001-01-02", periods=n)
    f = {"atr": np.full(n, 2.0), "stage": np.ones(n, np.int8)}
    cost = Y.Cost(np.full(n, 0.001), np.full(n, 0.003))
    sig = KJ.Sig("000001", 2, 2, float(b["o"][2]), float(b["o"][2]), 2.0, 1.0)

    def open_pos(s, q):
        return Y.Y30Pos(s, b, f, q, P)
    r = Y.run_book30({2: [sig]}, open_pos, lambda s, B, u: (10, "ok"), cal, str(cal[0].date()),
                     str(cal[-1].date()), 0, start_equity=1e6, cost=cost, max_pos=6)
    assert abs(r["recon"]) < 1e-6
    assert r["counts"]["fill"] == 1


def test_baselines_hold_and_m():
    kd = pd.bdate_range("2000-01-03", periods=120)
    kc = np.linspace(100, 160, 120)
    out = Y.baselines(kd, kc, (str(kd[100].date()), str(kd[-1].date())))
    assert out["hold"]["total"] == pytest.approx(kc[-1] / kc[99] - 1)
    assert out["m_hold"]["total"] <= out["hold"]["total"] + 1e-12


def test_population_memo_uses_y30pos():
    n = 10
    c = np.full(n, 100.0)
    b = _bars(c, c + 0.5, c - 0.5, c)
    f = {"atr": np.full(n, 2.0), "stage": np.ones(n, np.int8)}
    memo = Y.PathMemo({"000001": b}, {"000001": f}, P)
    s = KJ.Sig("000001", 1, 1, 100.0, 100.0, 2.0, 1.0)
    pop = Y.population([s], memo, KO.ExitCfg(), 0, n - 1, 0.0)
    assert len(pop) == 1 and isinstance(pop[0], Y.Y30Pos) and pop[0].exit_reason == "END"
