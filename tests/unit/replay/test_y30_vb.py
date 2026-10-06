"""volatility_breakout 30년 재검증 층(``vb_y30``) 단위 테스트 — 합성 입력 + 기존 재현 층과의 대조.

사전 고정 = ``_workspace/analysis/strategy_30y_20261006/vb/prereg.md``.
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
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

from replay.audit import judge as J  # noqa: E402
from replay.strategies import vb as VB  # noqa: E402
from replay.strategies import vb_opt as VO  # noqa: E402
from replay.strategies import vb_y30 as Y  # noqa: E402

pytestmark = pytest.mark.unit


def test_noise_k_series_matches_scalar():
    rng = np.random.default_rng(1)
    n = 60
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = c + rng.normal(0, 0.5, n)
    h = np.maximum(o, c) + rng.uniform(0, 1, n)
    l = np.minimum(o, c) - rng.uniform(0, 1, n)
    h[10] = l[10] = o[10] = c[10]           # 범위 0 봉
    ks = Y.noise_k_series(o, h, l, c, 15)
    for i in range(2, n):
        assert ks[i] == pytest.approx(VB.noise_k(o, h, l, c, i, 15), rel=1e-12)
    assert np.isnan(ks[0]) and np.isnan(ks[1])


def _cands(O, H, L, C, nxt_o, lock=None):
    n = len(O)
    f = lambda x: np.asarray(x, float)  # noqa: E731
    return Y.Cands(tk=np.zeros(n, int), names=["000001"], i=np.arange(n), gd=np.arange(n), k=np.full(n, .5),
                   rng_prev=np.full(n, 10.), tv_prev=np.ones(n), trend=np.ones(n, bool), range_pct=np.full(n, .1),
                   O=f(O), H=f(H), L=f(L), C=f(C), raw=np.ones(n), nxt_o=f(nxt_o),
                   nxt_gd=np.where(np.isfinite(f(nxt_o)), np.arange(n) + 1, -1),
                   lock_dn=np.zeros(n, bool) if lock is None else np.asarray(lock), near_up=np.zeros(n, bool),
                   m=np.ones(n))


@pytest.mark.parametrize("hold", ["C", "N", "W"])
@pytest.mark.parametrize("version", ["pes", "opt"])
@pytest.mark.parametrize("mode,stop", [("intraday", -5.0), ("intraday", -8.0), ("close", -5.0)])
def test_outcome_matches_vb_opt(hold, version, mode, stop):
    # 체결 100 고정 · 여러 날 모양
    O = [95, 95, 95, 95, 95]
    H = [104, 101, 103, 100.5, 110]
    L = [99, 94, 91, 89, 97]
    C = [102, 97, 93, 90, 99]
    nx = [103, 98, 92, 85, np.nan]
    cd = _cands(O, H, L, C, nx)
    sg = Y.Sigs(np.arange(5), np.full(5, 100.0), np.full(5, 100.0))
    px, why, xg = Y.outcome(cd, sg, hold, mode, stop, version)
    for j in range(5):
        b = {"o": np.array([O[j], nx[j] if np.isfinite(nx[j]) else 0.0]), "h": np.array([H[j], 0.0]),
             "l": np.array([L[j], 0.0]), "c": np.array([C[j], 0.0]), "di": np.array([j, j + 1])}
        if not np.isfinite(nx[j]):
            b = {k: v[:1] for k, v in b.items()}
        epx, _w, exi = VO.outcome(b, 0, 100.0, stop, hold, version, mode)
        assert px[j] == pytest.approx(epx)
        assert xg[j] == j + exi


def test_limit_lock_pushes_close_exit_to_next_open():
    cd = _cands([95], [101], [91], [91], [88], lock=[True])
    sg = Y.Sigs(np.array([0]), np.array([100.0]), np.array([100.0]))
    px, why, xg = Y.outcome(cd, sg, "C", "close", -5.0, "opt")      # 종가 손절인데 하한가 잠김
    assert (px[0], why[0], xg[0]) == (88.0, 5, 1)
    px, why, xg = Y.outcome(cd, sg, "C", "intraday", -5.0, "opt")   # 손절선 체결은 장중 — 잠김과 무관
    assert (px[0], why[0]) == (95.0, 1)


def test_fill_capped_at_high():
    cd = _cands([100], [101.5], [99], [100], [100])
    cd.rng_prev[:] = 2.0
    cd.k[:] = 0.5
    sg = Y.signals(cd, 1.0, "F0", 1.0193)          # 목표 101 · 101 × 1.0193 > 고가
    assert sg.target[0] == pytest.approx(101.0)
    assert sg.E[0] == pytest.approx(101.5)
    sg2 = Y.signals(cd, 2.0, "F0", 1.0)            # 목표 102 > 고가 → 신호 없음
    assert len(sg2.idx) == 0


def test_cooldown_counts_from_exit_day():
    cd = _cands([95] * 6, [110] * 6, [99] * 6, [100] * 6, [100] * 6)
    sg = Y.Sigs(np.arange(6), np.full(6, 100.0), np.full(6, 100.0))
    xg = np.array([1, 2, 3, 4, 5, 6])              # 모두 다음 날 청산
    keep = Y.cooldown_keep(cd, sg, xg, cooldown=2)
    # 0 진입 → 청산 1 → 1·2·3 금지 → 4 허용 → 청산 5 → 5 금지
    assert keep.tolist() == [True, False, False, False, True, False]


def test_cluster_boot_equals_judge_sorted():
    rng = np.random.default_rng(3)
    v = rng.normal(0, 0.02, 400)
    keys = [f"{rng.integers(0, 40):03d}|W{rng.integers(0, 9)}" for _ in range(400)]
    a = J.cluster_bootstrap(v, keys, order="sorted")
    b = Y.cluster_boot(v, keys, chunk=137)
    assert a[0] == pytest.approx(b[0]) and a[1] == pytest.approx(b[1]) and a[2] == pytest.approx(b[2])


def test_cost_and_limit_tables():
    costs = Y.load_costs()
    d = pd.DatetimeIndex(["1996-02-01", "1997-05-02", "1999-07-01", "2010-03-02", "2020-01-02", "2026-09-01"])
    assert Y.cost_rt_for_dates(d, costs).tolist() == pytest.approx([.0145, .013, .005, .0036, .0028, .0023])
    lim = Y.load_limits()
    assert Y.limit_for(0, pd.DatetimeIndex(["1997-01-03", "1998-06-01", "2010-01-04", "2016-01-04"]),
                       lim).tolist() == pytest.approx([.08, .12, .15, .30])
    k = Y.limit_for(1, pd.DatetimeIndex(["1996-08-01", "2000-01-04", "2006-01-04"]), lim)
    assert np.isnan(k[0]) and k[1:].tolist() == pytest.approx([.12, .15])


def test_rank_pct_and_x_thresholds():
    df = pd.DataFrame({"ticker": list("abcd") * 2,
                       "bas_dd": pd.to_datetime(["2025-01-02"] * 4 + ["2025-01-03"] * 4),
                       "mktcap": [9e10, 6e10, 1e10, np.nan, 9e10, 4e10, 1e10, 2e10],
                       "trade_value": [6e10, 1e9, 0, 0, 1e9, 1e9, 1e9, 1e9]})
    x = Y.x_thresholds(df)
    assert x["X_mcap"] == pytest.approx((0.5 + 0.25) / 2)
    assert x["X_tv"] == pytest.approx((0.25 + 0) / 2)
    r = Y.add_rank_pct(df.copy())
    assert r.loc[0, "mc_pct"] == pytest.approx(0.25) and r.loc[1, "mc_pct"] == pytest.approx(0.5)
    assert r.loc[3, "mc_pct"] == pytest.approx(1.0)                # 결측 = 맨 뒤
