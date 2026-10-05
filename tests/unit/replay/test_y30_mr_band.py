"""30년 재검증 볼린저 — 5년판(``mrband``)과의 동치 · 시기별 폭 · 시기별 비용 테스트."""
from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("scipy")

import numpy as np  # noqa: E402

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import y30_mr_band as B  # noqa: E402
from replay.strategies import mrband as M  # noqa: E402


def _bars(seed, n=300):
    rng = np.random.default_rng(seed)
    c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.025, n)))
    o = c * np.exp(rng.normal(0, 0.01, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.012, n)))
    nt = rng.random(n) < 0.02
    return o, h, l, c, nt


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_ticker_cands_equal_mrband_at_30pct(seed):
    o, h, l, c, nt = _bars(seed)
    n = len(c)
    lab = np.random.default_rng(seed).choice([1, 2, 3, 4, 5, 6], size=n)
    sig_ok = np.ones(n, bool)
    b5 = {"o": o, "h": h, "l": l, "c": c, "notrade": nt, "o_raw": o, "di": np.arange(n)}
    b30 = {"o": o, "h": h, "l": l, "c": c, "notrade": nt, "o_raw": o, "g0": 0, "lim": np.full(n, 0.30),
           "flag": M.jump_bars(c).astype(np.int64)}
    for (N, k, ex, sp, liq, side) in ((20, 2.0, 0, "atr", False, False), (10, 1.5, 2, "pct", True, True)):
        old = M.candidates_for_ticker("X", b5, lab, sig_ok, n=N, k=k, exit_mode=ex, stop=sp, liq=liq,
                                      sideways_only=side)
        new = B.ticker_cands(0, b30, lab, sig_ok, N, k, ex, sp, liq, side, B.ind_for(b30, lab, N, k))
        for m in M.ENTRIES:
            assert len(old[m]) == len(new[m])
            for a, z in zip(old[m], new[m]):
                assert (a.e, a.x, a.reason, a.jump) == (z.e_gd, z.x_gd, z.reason, z.jump)
                assert a.X == pytest.approx(z.X) and a.X_adv == pytest.approx(z.Xa)


def test_locked_bars_lim_matches_at_30_and_widens_at_15():
    o, h, l, c = (np.array(x, float) for x in ([100, 86, 85], [101, 86, 87], [99, 86, 84], [100, 86, 85]))
    assert B.locked_bars_lim(o, h, l, c, np.full(3, 0.30)).tolist() == M.locked_bars(o, h, l, c).tolist()
    assert B.locked_bars_lim(o, h, l, c, np.full(3, 0.15)).tolist() == [False, True, False]


def test_era_cost_net_uses_entry_and_exit_day():
    ctx = B.Ctx(np.array(["2001-01-02", "2001-01-03", "2001-01-04"], dtype="datetime64[D]"),
                np.array([0.013, 0.005, 0.005]))
    p = np.zeros(1, B.POP_DT)
    p[0] = (0, 0, 2, 2, 100.0, 110.0, 110.0, 3, False, 0)
    got = ctx.nets(p)[0]
    assert got == pytest.approx((1 - 0.0025) * 110 / ((1 + 0.0065) * 100) - 1)
