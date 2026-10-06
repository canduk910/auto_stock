"""etf_trend 효율화(2026-10-05) 실행기 단위 테스트 — 합성 입력만(보관소·DB 0).

- 일반화 청산 ``sim_v`` 가 현행 축에서 판정판 ``sim_b`` 와 같은가
- 계좌용 한 랏 ``EtfPosV`` 를 날마다 걸은 결과가 모든 축에서 ``sim_v`` 와 같은가
- 격자 108 · 현행판 포함 · 블록 부트스트랩 · 기준선 집행
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for p in (_TOOLS, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from replay.audit import indicators as IND  # noqa: E402
from replay.strategies import etf_trend_b as EB  # noqa: E402
from replay.strategies import etf_trend_b_audit as EA  # noqa: E402
from replay.strategies import etf_trend_opt as OP  # noqa: E402

pytestmark = pytest.mark.unit


def _synthetic(seed: int, n: int = 200) -> dict:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0015, 0.013, n)))
    o = np.r_[c[0], c[:-1] * np.exp(rng.normal(0, 0.006, n - 1))]
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.012, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.012, n)))
    return {"ci": np.arange(n), "o": o, "h": h, "l": l, "c": c, "n14": IND.atr_sma(h, l, c, 14),
            "hi_prev20": IND.prior_max(h, 20), "hi_prev60": IND.prior_max(h, 60)}


def _sig(d, j, line):
    return EA.ETFSig(ticker="T", ti=j + 1, gd=int(d["ci"][j + 1]), E=float(d["o"][j + 1]), E_raw=float(d["o"][j + 1]),
                     N=float(d["n14"][j]), line=float(line), m=1.0, tv20=1.0, sig_ci=int(d["ci"][j]))


def test_sim_v_current_axes_equal_sim_b():
    checked = 0
    for seed in range(30):
        d = _synthetic(seed)
        for j in range(30, 190, 5):
            if not (d["n14"][j] > 0):
                continue
            for mode in ("color", "adverse"):
                assert OP.sim_v(d, j, d["hi_prev20"][j], 1.8, 10, True, mode=mode) == EB.sim_b(d, j, mode=mode)
                checked += 1
    assert checked > 600


def test_daily_lot_equals_sim_v_every_axis():
    checked = 0
    for seed in range(8):
        d = _synthetic(seed)
        for j in range(70, 190, 9):
            if not (d["n14"][j] > 0):
                continue
            for line_key, tr, ch, bl in itertools.product(("hi_prev20", "hi_prev60"), OP.TR_GRID, OP.CH_GRID,
                                                          OP.BL_GRID):
                line = d[line_key][j]
                k, px, why = OP.sim_v(d, j, line, tr, ch, bl)
                ps = OP.run_path_v(_sig(d, j, line), d, trail=tr, chan=ch, bl=bl)
                assert (ps.exit_ti, ps.exit_px, ps.exit_reason) == (k, px, why)
                checked += 1
    assert checked > 500


def test_wider_exits_hold_longer_on_average():
    holds = {}
    for tr, ch, bl in ((1.8, 10, True), (None, 20, False)):
        hs = []
        for seed in range(20):
            d = _synthetic(seed)
            for j in range(30, 150, 7):
                if d["n14"][j] > 0:
                    hs.append(OP.sim_v(d, j, d["hi_prev20"][j], tr, ch, bl)[0] - j)
        holds[(tr, ch, bl)] = np.mean(hs)
    assert holds[(None, 20, False)] > holds[(1.8, 10, True)]


def test_grid_is_108_and_contains_current():
    g = OP.grid()
    assert len(g) == 108 and len(set(g)) == 108 and OP.CURRENT in g


def test_mu_filter():
    assert OP.mu_ok(0.5, "gt0") and not OP.mu_ok(0.5, "ge075") and OP.mu_ok(0.75, "ge075")
    assert OP.mu_ok(1.0, "eq1") and not OP.mu_ok(0.75, "eq1")
    assert not OP.mu_ok(0.0, "gt0") and not OP.mu_ok(None, "gt0") and not OP.mu_ok(float("nan"), "eq1")


def _t(ticker, d, rn):
    return {"ticker": ticker, "entry_date": d, "RN": rn}


def test_diff_bootstrap_identical_lists_zero_and_shift_detected():
    A = [_t("A", f"2024-0{1 + i % 9}-0{1 + i % 7}", 0.01 * ((i * 7) % 5 - 2)) for i in range(60)]
    r = OP.diff_bootstrap(A, A, n_boot=2000)
    assert abs(r["diff"]) < 1e-12 and abs(r["lo90"]) < 1e-12
    B = [dict(t, RN=t["RN"] + 0.02) for t in A]
    r2 = OP.diff_bootstrap(B, A, n_boot=2000)
    assert r2["diff"] == pytest.approx(0.02) and r2["lo90"] == pytest.approx(0.02)


def test_baseline_b1_buys_once_b2_follows_m():
    n = 30
    cal = pd.date_range("2024-01-01", periods=n, freq="B")
    px = 10000 * 1.001 ** np.arange(n)
    k = {"ci": np.arange(n), "o": px, "c": px}
    mu = np.ones(n)
    mu[10:20] = 0.0
    b1 = OP.baseline(k, mu, cal, (str(cal[1].date()), str(cal[-1].date())), "B1")
    b2 = OP.baseline(k, mu, cal, (str(cal[1].date()), str(cal[-1].date())), "B2")
    yrs = b1["days"] / 252.0
    assert b1["trades_per_year"] * yrs == pytest.approx(1)
    assert b2["trades_per_year"] * yrs == pytest.approx(3)       # 사고 → 팔고 → 다시 산다
    assert b2["cagr"] < b1["cagr"]
