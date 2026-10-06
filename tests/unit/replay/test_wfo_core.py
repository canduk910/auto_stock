"""주기적 재조정 공통 층 — 학습 창(미래 자료 차단) · 선택 규칙 · 이어 붙이기 · 부트스트랩 동치."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import wfo_core as W  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.strategies import bfb_vcp_opt as OP  # noqa: E402

CAL = pd.bdate_range("1996-01-02", "2026-10-02")


def _tr(gin, gout, r, tick="A"):
    gin = np.asarray(gin)
    return W.Trades(gin, np.asarray(gout), np.asarray(r, float), W.week_keys([tick] * len(gin), gin, CAL))


def test_cluster_boot_equals_judge():
    rng = np.random.default_rng(1)
    v = rng.normal(0.001, 0.05, 500)
    keys = [f"T{rng.integers(30)}|2001-W{rng.integers(1, 50):02d}" for _ in v]
    assert W.cluster_boot(v, keys) == J.cluster_bootstrap(v, keys, order="sorted")


def test_month_block_diff_equals_opt():
    rng = np.random.default_rng(2)
    da = [f"20{rng.integers(10, 20)}-0{rng.integers(1, 9)}-15" for _ in range(200)]
    db = [f"20{rng.integers(10, 20)}-0{rng.integers(1, 9)}-15" for _ in range(150)]
    ra, rb = rng.normal(0, .05, 200), rng.normal(0, .05, 150)
    ref = OP.month_block_diff([{"d": d, "r": r} for d, r in zip(da, ra)], [{"d": d, "r": r} for d, r in zip(db, rb)],
                              n_boot=3000)
    got = W.month_block_diff(ra, [d[:7] for d in da], rb, [d[:7] for d in db], n_boot=3000)
    assert abs(ref["est"] - got["est"]) < 1e-12 and abs(ref["lower"]["0.05"] - got["lower"]["0.05"]) < 1e-12


def test_train_mask_excludes_open_and_future_exits():
    yi = W.YearIndex(CAL)
    f07, f06 = yi.first(2007), yi.first(2006)
    tr = _tr([yi.first(1996), yi.first(1997), f06 + 10, f07 - 3, f07 - 3, f07],
             [yi.first(1997) + 5, yi.first(1997) + 5, f06 + 20, f07 - 1, f07 + 2, f07 + 5], [0.1] * 6)
    m = yi.train_mask(tr, 2007)
    # 1996 진입(창 밖) · 2007 에 청산(미래) · 2007 진입 은 빠진다
    assert m.tolist() == [False, True, True, True, False, False]
    tr2 = _tr([f07 - 3], [W.OPEN_GD], [0.5])
    assert not yi.train_mask(tr2, 2007).any()


def test_select_prefers_lo90_then_mean_and_fallback():
    yi = W.YearIndex(CAL)
    rng = np.random.default_rng(3)
    g = rng.integers(yi.first(1997), yi.first(2006), 400)
    good = _tr(g, g + 3, rng.normal(0.01, 0.01, 400))
    bad = _tr(g, g + 3, rng.normal(-0.01, 0.01, 400))
    cfg = {"a": {"x": 1}, "b": {"x": 2}}
    s = W.select_year(yi, 2007, ["a", "b"], {"a": bad, "b": good}, cfg, {"x": 1}, min_tpy=30, current_id="a")
    assert s["chosen"] == "b" and not s["fallback"]
    s2 = W.select_year(yi, 2007, ["a", "b"], {"a": bad, "b": good}, cfg, {"x": 1}, min_tpy=50, current_id="a")
    assert s2["chosen"] == "a" and s2["fallback"]          # 자격(500건) 미달 → 현행


def test_stitch_takes_each_year_from_its_combo():
    yi = W.YearIndex(CAL)
    a = _tr([yi.first(2007) + 1, yi.first(2008) + 1], [yi.first(2007) + 5, W.OPEN_GD], [1.0, 2.0])
    b = _tr([yi.first(2007) + 2, yi.first(2008) + 2], [yi.first(2007) + 6, yi.first(2008) + 9], [3.0, 4.0])
    s = W.stitch(yi, {2007: "a", 2008: "b"}, {"a": a, "b": b})
    assert sorted(s.r.tolist()) == [1.0, 4.0]


def test_chained_mar():
    c = {2000: np.array([110.0, 99.0, 121.0]), 2001: np.array([100.0, 100.0])}
    m = W.chained_mar(c, [2000, 2001], 100.0)
    # 곡선 1 → 1.1 → 0.99 → 1.21 → 1.21 → 1.21 · 낙폭 −10% · 2년 연 복리 = 1.21^(1/2) − 1 = 10%
    assert abs(m - 0.10 / 0.10) < 1e-9


def test_book_summary_eras_use_segment_start():
    d = pd.bdate_range("2007-01-01", "2012-12-31")
    eq = np.linspace(100, 200, len(d))
    s = W.book_summary([eq], d, 100.0)
    assert s["cagr_median"] > 0 and "2012–2016" in s["eras"] and s["mdd_median"] == 0.0
