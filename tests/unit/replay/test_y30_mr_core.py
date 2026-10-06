"""30년 재검증(평균회귀·장세) — 데이터·집행 층 회귀 테스트.

사전 등록 = ``_workspace/analysis/strategy_30y_20261006/mr_regime/prereg.md``.
연구 전용 의존성(statsmodels·scipy)이 없는 운영 테스트 환경에서는 통째로 건너뛴다.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import y30_mr_data as Y  # noqa: E402
from replay import y30_mr_ou as OU  # noqa: E402
from replay.execution import Rule, simulate_ticker  # noqa: E402
from replay.strategies.mean_reversion.signals import SignalSeries  # noqa: E402

COSTS = [("1996-01-01", 0.0145), ("1996-04-01", 0.013), ("1999-07-01", 0.005), ("2006-01-01", 0.0036),
         ("2026-01-01", 0.0023)]
LIMITS = {"KOSPI": [("1995-04-01", 0.06), ("1996-11-25", 0.08), ("1998-03-02", 0.12), ("1998-12-07", 0.15),
                    ("2015-06-15", 0.30)],
          "KOSDAQ": [("1996-07-01", 0.08), ("1998-05-25", 0.12), ("2005-03-28", 0.15), ("2015-06-15", 0.30)]}


def test_cost_on_picks_era():
    assert Y.cost_on("1997-05-02", COSTS) == 0.013
    assert Y.cost_on("1999-06-30", COSTS) == 0.013
    assert Y.cost_on("1999-07-01", COSTS) == 0.005
    assert Y.cost_on("2026-09-01", COSTS) == 0.0023
    assert Y.cost_on("1990-01-01", COSTS) == 0.0145


def test_cost_table_file_matches_meta():
    tab = Y.load_cost_table()
    assert Y.cost_on("1997-01-02", tab) == pytest.approx(0.013)
    assert Y.cost_on("2013-01-02", tab) == pytest.approx(0.0036)


def test_limit_on_by_market_and_date():
    assert Y.limit_on("1997-06-02", "KOSPI", LIMITS) == 0.08
    assert Y.limit_on("2004-06-02", "KOSDAQ", LIMITS) == 0.12
    assert Y.limit_on("2004-06-02", "KOSPI", LIMITS) == 0.15
    assert Y.limit_on("2016-01-04", "KOSDAQ GLOBAL", LIMITS) == 0.30
    assert Y.limit_up_mult(0.30) == pytest.approx(1.29)
    assert Y.limit_down_mult(0.30) == pytest.approx(0.71)


def test_top_share_mask_counts_and_ignores_missing():
    v = np.array([5.0, np.nan, 1.0, 3.0, 0.0, 4.0, 2.0])
    m = Y.top_share_mask(v, 0.5)          # 유효 5개 → ceil(2.5)=3
    assert m.tolist() == [True, False, False, True, False, True, False]


def _ou_series(n, seed):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.6 * x[i - 1] + rng.normal(0, 0.03)
    c = 10000 * np.exp(x)
    o = c * np.exp(rng.normal(0, 0.01, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.02, n)))
    return o, h, l, c, x


def _sig_from(x, n, rng):
    z = (x - x.mean()) / x.std() + rng.normal(0, 0.2, n)
    valid = rng.random(n) > 0.05
    is_est = np.array([i % 5 == 0 for i in range(n)])
    reason = np.where(valid, 0, 1).astype(np.int8)
    return SignalSeries(z=np.where(valid, z, np.nan), valid=valid, is_est=is_est, est_reason=reason,
                        hl=np.full(n, 2.0), hl_adj=np.full(n, 2.0), sigma_stat=np.full(n, 0.05),
                        theta=np.full(n, math.log(2) / 2), adf_p=np.full(n, 0.01))


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_simulate_y30_equals_original_at_30pct_flat_cost(seed):
    n = 400
    o, h, l, c, x = _ou_series(n, seed)
    rng = np.random.default_rng(seed + 100)
    sig = _sig_from(x, n, rng)
    elig = rng.random(n) > 0.1
    mu = rng.choice([1.0, 0.75, 0.5, 0.0], size=n)
    for ez, xz, sp, k in ((-1.5, 0.0, 7.0, 1.5), (-2.0, -0.5, 5.0, 1.0)):
        a = simulate_ticker(o, h, l, c, sig, elig, mu, Rule("z", ez, xz, 0.0038, sp, k))
        b = OU.simulate_y30(o, h, l, c, sig, elig, mu, ez=ez, xz=xz, stop_pct=sp, k_stop=k, mu_rule="block0",
                            lim=np.full(n, 0.30), cost_day=np.full(n, 0.0038))
        assert len(a) == len(b) and len(a) > 0
        for p, q in zip(a, b):
            for f in ("ei", "xi", "sig_day", "reason", "rb_kind"):
                assert p[f] == q[f]
            assert p["exit_px"] == pytest.approx(q["exit_px"])
            assert q["cost"] == pytest.approx(0.0038)


def test_limit_up_entry_blocked_only_under_narrow_limit():
    n = 120
    c = np.full(n, 10000.0)
    o = c.copy()
    h, l = c * 1.01, c * 0.99
    o[61] = 11450.0                 # 전일 종가 대비 +14.5%
    z = np.full(n, 0.0)
    z[60] = -3.0
    sig = SignalSeries(z=z, valid=np.ones(n, bool), is_est=np.zeros(n, bool), est_reason=np.zeros(n, np.int8),
                       hl=np.full(n, 2.0), hl_adj=np.full(n, 2.0), sigma_stat=np.full(n, 0.05),
                       theta=np.full(n, 0.3), adf_p=np.full(n, 0.01))
    kw = dict(ez=-1.5, xz=0.0, stop_pct=7.0, k_stop=1.5, mu_rule="block0", cost_day=np.full(n, 0.0038))
    narrow = OU.simulate_y30(o, h, l, c, sig, np.ones(n, bool), np.ones(n), lim=np.full(n, 0.15), **kw)
    wide = OU.simulate_y30(o, h, l, c, sig, np.ones(n, bool), np.ones(n), lim=np.full(n, 0.30), **kw)
    assert narrow == [] and len(wide) == 1 and wide[0]["ei"] == 61


def test_locked_limit_down_uses_era_limit():
    n = 120
    c = np.full(n, 10000.0)
    o, h, l = c.copy(), c * 1.01, c * 0.99
    z = np.full(n, 0.0)
    z[60] = -3.0                    # 61 일 시가 진입
    o[63] = h[63] = l[63] = c[63] = 8600.0      # 전일 대비 −14% · 고가 = 저가 → 15% 시절이면 하한가 잠김
    o[64], h[64], l[64], c[64] = 8500.0, 8600.0, 8400.0, 8500.0
    sig = SignalSeries(z=z, valid=np.ones(n, bool), is_est=np.zeros(n, bool), est_reason=np.zeros(n, np.int8),
                       hl=np.full(n, 5.0), hl_adj=np.full(n, 5.0), sigma_stat=np.full(n, 0.05),
                       theta=np.full(n, 0.3), adf_p=np.full(n, 0.01))
    kw = dict(ez=-1.5, xz=0.5, stop_pct=7.0, k_stop=9.0, mu_rule="none", cost_day=np.full(n, 0.0038))
    narrow = OU.simulate_y30(o, h, l, c, sig, np.ones(n, bool), np.ones(n), lim=np.full(n, 0.15), **kw)
    wide = OU.simulate_y30(o, h, l, c, sig, np.ones(n, bool), np.ones(n), lim=np.full(n, 0.30), **kw)
    assert narrow[0]["xi"] == 64 and narrow[0]["exit_px"] == 8500.0
    assert wide[0]["xi"] == 63


def test_cost_is_half_entry_half_exit_day():
    n = 120
    c = np.full(n, 10000.0)
    o, h, l = c.copy(), c * 1.01, c * 0.99
    z = np.full(n, 0.0)
    z[60] = -3.0
    z[61] = 1.0                     # 61 종가 이익 신호 → 62 시가 청산
    sig = SignalSeries(z=z, valid=np.ones(n, bool), is_est=np.zeros(n, bool), est_reason=np.zeros(n, np.int8),
                       hl=np.full(n, 5.0), hl_adj=np.full(n, 5.0), sigma_stat=np.full(n, 0.05),
                       theta=np.full(n, 0.3), adf_p=np.full(n, 0.01))
    cost = np.full(n, 0.004)
    cost[62] = 0.002
    tr = OU.simulate_y30(o, h, l, c, sig, np.ones(n, bool), np.ones(n), ez=-1.5, xz=0.0, stop_pct=7.0, k_stop=1.5,
                         mu_rule="block0", lim=np.full(n, 0.30), cost_day=cost)
    assert tr[0]["xi"] == 62 and tr[0]["cost"] == pytest.approx(0.003)


def test_mu_rules():
    n = 120
    c = np.full(n, 10000.0)
    o, h, l = c.copy(), c * 1.01, c * 0.99
    z = np.full(n, 0.0)
    z[60] = -3.0
    sig = SignalSeries(z=z, valid=np.ones(n, bool), is_est=np.zeros(n, bool), est_reason=np.zeros(n, np.int8),
                       hl=np.full(n, 5.0), hl_adj=np.full(n, 5.0), sigma_stat=np.full(n, 0.05),
                       theta=np.full(n, 0.3), adf_p=np.full(n, 0.01))
    kw = dict(ez=-1.5, xz=0.0, stop_pct=7.0, k_stop=1.5, lim=np.full(n, 0.30), cost_day=np.full(n, 0.0038))
    for m, expect in ((0.0, {"block0": 0, "m1": 0, "none": 1}), (0.75, {"block0": 1, "m1": 0, "none": 1}),
                      (1.0, {"block0": 1, "m1": 1, "none": 1})):
        mu = np.full(n, m)
        for rule, k in expect.items():
            assert len(OU.simulate_y30(o, h, l, c, sig, np.ones(n, bool), mu, mu_rule=rule, **kw)) == k


def test_market_unit_by_session_is_d_minus_1():
    rng = np.random.default_rng(7)
    n = 200
    sd = np.arange(np.datetime64("2001-01-01"), np.datetime64("2001-01-01") + np.timedelta64(n, "D"))
    sc = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    m1 = Y.market_unit_by_session(sd, sc, sd)
    sc2 = sc.copy()
    sc2[150] *= 3.0                         # 150 일 종가만 바꾼다
    m2 = Y.market_unit_by_session(sd, sc2, sd)
    assert np.array_equal(m1[:151], m2[:151], equal_nan=True)
    assert np.isnan(m1[:80]).all() and np.isfinite(m1[80])


def test_regime_by_session_is_d_minus_1():
    rng = np.random.default_rng(8)
    n = 200
    sd = np.arange(np.datetime64("2001-01-01"), np.datetime64("2001-01-01") + np.timedelta64(n, "D"))
    sc = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    r1 = Y.regime_by_session(sd, sc, sd)
    sc2 = sc.copy()
    sc2[150] *= 3.0
    r2 = Y.regime_by_session(sd, sc2, sd)
    assert np.array_equal(r1[:151], r2[:151])
    assert (r1[:80] == 0).all() and r1[80] > 0


def test_seg_index_bounds():
    d = np.array(["1996-12-30", "1997-01-02", "2012-12-28", "2013-01-02", "2020-12-30", "2021-01-04",
                  "2026-10-02"], dtype="datetime64[D]")
    assert Y.seg_index(d).tolist() == [-1, 0, 0, 1, 1, 2, 2]
