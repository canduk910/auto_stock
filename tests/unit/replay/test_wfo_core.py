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


# ── 학습 창 길이 K(``wfo_window_20261009/prereg.md`` §1) ────────────────────

def _mean_score(tr):
    m = float(tr.r.mean()) if len(tr) else float("nan")
    return m, m


def _window_trades(yi, y):
    """K=3 이면 [Y−3, Y−1] 진입 ∧ Y 첫 거래일 전 청산만 남는다. Y−8 진입은 K=10 에서만 들어간다."""
    f = yi.first
    gin = [f(y - 8) + 5, f(y - 4) + 5, f(y - 3), f(y - 2) + 7, f(y - 1) + 3, f(y) - 4, f(y) - 2, f(y) + 1]
    gout = [f(y - 8) + 9, f(y - 4) + 9, f(y - 3) + 4, f(y - 2) + 9, f(y - 1) + 8, f(y) - 1, f(y) + 2, f(y) + 6]
    r = [9.0, 8.0, 0.1, 0.2, 0.3, 0.4, 7.0, 6.0]
    return _tr(gin, gout, r)


def test_select_year_train_years_window_and_eligibility():
    yi = W.YearIndex(CAL)
    tr = _window_trades(yi, 2010)
    cfg = {"a": {"x": 1}, "cur": {"x": 0}}
    trades = {"a": tr, "cur": _tr([yi.first(2003)], [yi.first(2003) + 1], [0.0])}
    # 남는 거래 = Y−3 첫날 진입 · Y−2 · Y−1 · Y 첫 거래일 직전 청산(4건) — Y−4 · Y−8 진입 · Y 에 청산 · Y 진입은 빠진다
    m = yi.train_mask(tr, 2010, years=3)
    assert m.tolist() == [False, False, True, True, True, True, False, False]
    s = W.select_year(yi, 2010, ["a", "cur"], trades, cfg, {"x": 0}, min_tpy=4 / 3, current_id="cur",
                      score_fn=_mean_score, train_years=3)
    row = {r["id"]: r for r in s["rows"]}["a"]
    assert row["n"] == 4 and row["eligible"]                       # 4 ≥ (4/3)×3
    assert s["chosen"] == "a" and not s["fallback"]
    assert abs(s["chosen_train_mean"] - 0.25) < 1e-12              # (0.1+0.2+0.3+0.4)/4
    # 자격 하한 = min_tpy × 3 — 1.34 × 3 = 4.02 > 4 이면 자격 없음(K=10 이었다면 13.4 라 더 일찍 떨어진다)
    s2 = W.select_year(yi, 2010, ["a", "cur"], trades, cfg, {"x": 0}, min_tpy=1.34, current_id="cur",
                       score_fn=_mean_score, train_years=3)
    assert not {r["id"]: r for r in s2["rows"]}["a"]["eligible"] and s2["fallback"] and s2["chosen"] == "cur"


def test_select_year_default_train_years_is_ten():
    yi = W.YearIndex(CAL)
    tr = _window_trades(yi, 2010)
    cfg = {"a": {"x": 1}}
    kw = dict(min_tpy=0.5, current_id="a", score_fn=_mean_score)
    d = W.select_year(yi, 2010, ["a"], {"a": tr}, cfg, {"x": 1}, **kw)
    t10 = W.select_year(yi, 2010, ["a"], {"a": tr}, cfg, {"x": 1}, train_years=10, **kw)
    t3 = W.select_year(yi, 2010, ["a"], {"a": tr}, cfg, {"x": 1}, train_years=3, **kw)
    assert W.TRAIN_YEARS == 10
    assert d["rows"] == t10["rows"] and d["chosen"] == t10["chosen"]
    assert d["rows"][0]["n"] == 6 and t3["rows"][0]["n"] == 4     # K=10 은 Y−8 · Y−4 진입까지 넣는다
    # 자격 하한도 10 배 — 0.5×10 = 5 ≤ 6 (자격) / 0.7×10 = 7 > 6 (자격 없음)
    assert d["rows"][0]["eligible"]
    assert not W.select_year(yi, 2010, ["a"], {"a": tr}, cfg, {"x": 1}, min_tpy=0.7, current_id="a",
                             score_fn=_mean_score)["rows"][0]["eligible"]


def _run_small(monkeypatch, **kw):
    yi = W.YearIndex(CAL)
    rng = np.random.default_rng(7)

    def mk(mu):
        g = np.sort(rng.integers(yi.first(1998), yi.first(2009) - 10, 300))
        return _tr(g, g + 3, rng.normal(mu, 0.01, 300), tick=f"T{mu}")
    trades = {"a": mk(0.01), "b": mk(-0.01), "c": mk(0.0)}
    cfgs = {"a": {"x": 1}, "b": {"x": 2}, "c": {"x": 3}}
    calls = {"select": [], "mar": []}
    real_sel, real_mar = W.select_year, W.chained_mar

    def spy_sel(*a, **k):
        calls["select"].append(k.get("train_years"))
        return real_sel(*a, **k)

    def spy_mar(curves, years, start):
        calls["mar"].append(list(years))
        return real_mar(curves, years, start)
    monkeypatch.setattr(W, "select_year", spy_sel)
    monkeypatch.setattr(W, "chained_mar", spy_mar)
    monkeypatch.setattr(W, "index_stats", lambda *a, **k: {})
    book = {"cagr_median": 0.0, "mdd_median": 0.0, "P2_pass": False}
    alt = {c: {y: np.array([100.0, 101.0]) for y in range(1996, 2009)} for c in trades}
    res = W.run_wfo(cal=CAL, combos=list(trades), cfgs=cfgs, trades=trades, current_id="c", fixed_b_id=None,
                    base_cfg=cfgs["c"], min_tpy=3, book_fn=lambda p, v: dict(book), years=(2007, 2008),
                    alt_curves=alt, log=lambda *a: None, **kw)
    return res, calls, trades, cfgs


def test_run_wfo_passes_train_years_to_select_and_alt(monkeypatch):
    res, calls, trades, cfgs = _run_small(monkeypatch, train_years=3)
    assert calls["select"] == [3, 3]
    assert calls["mar"][:3] == [[2004, 2005, 2006]] * 3 and calls["mar"][3:] == [[2005, 2006, 2007]] * 3
    yi = W.YearIndex(CAL)
    for y in (2007, 2008):
        ref = W.select_year(yi, y, list(trades), trades, cfgs, cfgs["c"], 3, "c", train_years=3)
        assert res["selection"][y]["chosen"] == ref["chosen"]
        assert res["selection"][y]["chosen_train_n"] == ref["chosen_train_n"]


def test_run_wfo_default_train_years_is_ten(monkeypatch):
    res, calls, _, _ = _run_small(monkeypatch)
    assert calls["select"] == [10, 10]
    assert calls["mar"][0] == list(range(1997, 2007))
