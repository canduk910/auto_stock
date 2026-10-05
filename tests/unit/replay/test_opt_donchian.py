"""donchian_swing 효율화(2026-10-05) — ``tools/replay/strategies/donchian_opt.py`` 단위 테스트.

현행 인자에서 확장 층이 전수 점검 운영 해석판과 같은 값을 내는지, 새 필터·청산 인자가 뜻대로 거르는지,
두 판 차이 부트스트랩이 상식대로 움직이는지 본다. 네트워크·DB·보관소 파일 0 — 합성 입력만 쓴다.
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

from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_opt as DO  # noqa: E402

pytestmark = pytest.mark.unit


def _series(n=400, seed=0):
    rng = np.random.default_rng(seed)
    c = 10000 * np.exp(np.cumsum(rng.normal(0.003, 0.02, n)))
    o = c * (1 + rng.normal(0, 0.005, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    vol[rng.random(n) < 0.15] *= 4
    return {"di": np.arange(n), "o": o, "h": h, "l": l, "c": c, "c_raw": c, "vol": vol,
            "tv": np.full(n, 300e8), "notrade": np.zeros(n, bool)}


def test_grid_size_matches_prereg():
    assert (len(DO.GRID_A), len(DO.GRID_B), len(DO.GRID_C)) == (32, 72, 15)
    assert DO.ENTRY0 in DO.GRID_A and DO.EXIT0 in DO.GRID_B and DO.ACCT0 in DO.GRID_C
    for g in DO.GRID_C:                                   # 불변식 position_ratio × max_positions ≤ 1.0
        assert g["slots"][0] * g["slots"][1] <= 1.0 + 1e-12


@pytest.mark.parametrize("seed", range(5))
def test_current_args_reproduce_operating_features(seed):
    b = _series(seed=seed)
    mem = np.ones(len(b["c"]), bool)
    kc = np.linspace(100, 130, len(b["c"]))
    f0 = DK.features(b, mem, turnover="cv")
    f1 = DO.features_opt(b, mem, kc)
    assert np.array_equal(f0["cond"], f1["cond"]) and f0["cond"].any()
    # 돌파 길이 20 을 「항 갈아 끼우기」 경로로 다시 만들어도 같아야 한다(55 경로의 식 검증)
    ph = f0["prior_high"]
    with np.errstate(invalid="ignore"):
        brk = np.nan_to_num((b["c"] > ph) & (ph > 0)).astype(bool)
    assert np.array_equal(DO._cond_wo_breakout(b, f0, mem, 1.5) & brk, f0["cond"])


def test_filters_only_narrow():
    b = _series(seed=3)
    mem = np.ones(len(b["c"]), bool)
    kc = np.linspace(100, 130, len(b["c"]))
    base = DO.features_opt(b, mem, kc)["cond"]
    for kw in (dict(vol_mult=2.5), dict(rs=True), dict(clv=0.6)):
        sub = DO.features_opt(b, mem, kc, **kw)["cond"]
        assert not (sub & ~base).any()


def test_rs_filter_blocks_when_market_stronger():
    b = _series(seed=1)
    mem = np.ones(len(b["c"]), bool)
    huge = np.exp(np.linspace(0, 10, len(b["c"])))          # 시장이 종목보다 훨씬 세다
    assert not DO.features_opt(b, mem, huge, rs=True)["cond"].any()


def test_clv_rejects_long_upper_wick():
    b = _series(seed=2)
    mem = np.ones(len(b["c"]), bool)
    kc = np.ones(len(b["c"]))
    b2 = dict(b, h=b["h"].copy())
    b2["h"] = np.maximum(b["h"], b["c"] * 1.10)            # 모든 봉 윗꼬리 10% — CLV 낮음
    b2["l"] = np.minimum(b["l"], b["c"] * 0.995)
    assert not DO.features_opt(b2, mem, kc, clv=0.6)["cond"].any()


def test_mu_filter():
    s = [DK.Sig("A", 0, 0, 1, 1, 1, 1, 1.0), DK.Sig("B", 0, 0, 1, 1, 1, 1, 0.75), DK.Sig("C", 0, 0, 1, 1, 1, 1, 0.5)]
    assert [x.ticker for x in DO.mu_filter(s, "m1")] == ["A"]
    assert DO.mu_filter(s, "cur") is s


def _flat(n=60):
    return {"di": np.arange(n), "o": np.full(n, 100.0), "h": np.full(n, 101.0), "l": np.full(n, 99.0),
            "c": np.full(n, 100.0), "notrade": np.zeros(n, bool)}


def test_time_exit_bars_param():
    b = _flat()
    sig = DK.Sig("T", 0, 0, 100.0, 100.0, 2.0, 0.0, 1.0)
    f = {"chan10": np.full(60, np.nan)}
    for bars in (10, 20, 30):
        kk = DO.kk_of(dict(DO.EXIT0, time_bars=bars))
        ps = DK.run_path(sig, b, f, 59, kk=kk)
        assert (ps.exit_reason, ps.exit_gd) == ("TIME_EXIT", bars - 1)


def test_r_definition_and_breakeven_param():
    b = _flat()
    sig = DK.Sig("T", 0, 0, 100.0, 100.0, 2.0, 0.0, 1.0)
    f = {"chan10": np.full(60, np.nan)}
    b["l"][3] = 93.5                                         # R 6% 면 94 손절, R 8% 면 견딘다
    assert DK.run_path(sig, b, f, 59, kk=DO.kk_of(dict(DO.EXIT0, r=(6.0, 1.5)))).exit_reason == "STOP_LOSS"
    assert DK.run_path(sig, b, f, 59, kk=DO.kk_of(DO.EXIT0)).exit_reason != "STOP_LOSS"
    kk = DO.kk_of(dict(DO.EXIT0, r=(6.0, 2.5)))                  # R = max(6, 2.5×2=5) = 6
    assert DK.KKPos(sig, b, f, 1, kk=kk).Rw == pytest.approx(6.0)
    kk = DO.kk_of(dict(DO.EXIT0, r=(6.0, 2.5)))
    sig4 = DK.Sig("T", 0, 0, 100.0, 100.0, 4.0, 0.0, 1.0)        # 2.5×4 = 10 > 6
    assert DK.KKPos(sig4, b, f, 1, kk=kk).Rw == pytest.approx(10.0)
    # 무장 R 2 → 고점 116 에서 무장(손절선 본전)
    b2 = _flat()
    b2["h"][2] = 116.5
    b2["l"][5] = 99.0
    ps = DK.KKPos(sig, b2, f, 1, kk=DO.kk_of(dict(DO.EXIT0, be_r=2.0)))
    ps.intraday_phase(0, 0, True)
    ps.intraday_phase(1, 1, False)
    ps.intraday_phase(2, 2, False)
    assert ps.armed and ps.stop == 100.0


def test_feats_view_channel():
    f = {"chan10": np.array([1.0]), "chan20": np.array([2.0])}
    assert DO.feats_view(f, 10) is f
    assert DO.feats_view(f, 20)["chan10"][0] == 2.0
    with pytest.raises(ValueError):
        DO.feats_view(f, 15)


def test_diff_boot_sign_and_identity():
    cal = pd.bdate_range("2024-01-01", periods=200)
    rng = np.random.default_rng(0)
    cur = [{"gd": int(g), "net": float(rng.normal(0, 0.05))} for g in rng.integers(0, 200, 800)]
    same = DO.diff_boot(cur, cur, cal)
    assert same["diff"] == pytest.approx(0.0) and same["q0.05"] == pytest.approx(0.0, abs=1e-12)
    better = [dict(x, net=x["net"] + 0.02) for x in cur]
    d = DO.diff_boot(better, cur, cal)
    assert d["diff"] == pytest.approx(0.02) and d["q0.05"] > 0.019


def test_pick_prefers_robust_then_lo90_then_closeness():
    base = {"a": 1, "b": 1}
    mk = lambda cfg, lo, rob, n=200: {"cfg": cfg, "T": {"n": n, "lo90": lo, "robust": rob}}  # noqa: E731
    c = [mk({"a": 1, "b": 1}, 0.001, True), mk({"a": 2, "b": 2}, 0.009, False), mk({"a": 2, "b": 1}, 0.004, True),
         mk({"a": 1, "b": 2}, 0.004, True), mk({"a": 3, "b": 3}, 0.05, True, n=10)]
    sel, note = DO.pick(c, base, 90)
    assert note == "강건" and sel["T"]["lo90"] == 0.004 and DO.n_changed(sel["cfg"], base) == 1
