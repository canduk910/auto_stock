"""30년 재검증(2026-10-06) — 봉 걷기(시대별 하한가 잠김) · 모집단 표시 행 제외 · 계좌(날짜별 비용) 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_30y_20261006/bfb/prereg.md``.
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

from replay.audit import book as BK  # noqa: E402
from replay.strategies import bfb_vcp_engine as EN  # noqa: E402
from replay.strategies import bfb_vcp_opt as OP  # noqa: E402
from replay.strategies import y30_bfbvcp as YB  # noqa: E402

pytestmark = pytest.mark.unit


def _bars(o, h, l, c, lim=0.30, jump=None):
    n = len(c)
    return {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
            "vol": np.full(n, 1000.0), "di": np.arange(n), "notrade": np.zeros(n, bool), "raw": np.ones(n),
            "lim": np.full(n, lim), "jump": np.zeros(n, bool) if jump is None else np.array(jump, bool),
            "tv": np.full(n, 1e9)}


def _feats(n, i, line, low=90.0, atr=2.0, target=np.nan):
    cand = np.zeros(n, bool)
    cand[i] = True
    f = {"cand": cand, "line": np.full(n, np.nan), "low": np.full(n, np.nan), "avg": np.zeros(n),
         "atr": np.full(n, atr), "ema50": np.full(n, np.nan), "target": np.full(n, np.nan)}
    f["line"][i], f["low"][i], f["avg"][i], f["target"][i] = line, low, 1000.0, target
    return f


CAL = pd.date_range("2024-01-01", periods=40, freq="D")


def _rand_path(seed, lim=0.30):
    rng = np.random.default_rng(seed)
    n = 30
    c = 100 * np.cumprod(1 + rng.normal(0.002, 0.04, n))
    o = c * (1 + rng.normal(0, 0.02, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.02, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.02, n)))
    b = _bars(o, h, l, c, lim=lim)
    f = _feats(n, 0, line=float(c[0] * 1.01), low=float(c[0] * 0.9), target=float(c[0] * 1.3))
    f["atr"] = np.abs(h - l) + 0.5
    return b, f


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("mode", ["color", "adverse"])
def test_walk_equals_opt_position_in_30pct_era(seed, mode):
    b, f = _rand_path(seed)
    p = OP.params_for("bfb", "cur", "X0")
    s = EN.Sig("X", 1, 1, float(b["o"][1]), float(b["o"][1]), 2.0, f["line"][0], f["low"][0], f["target"][0],
               1.0, True, "gap")
    ref = OP.run_path(s, b, f, 29, kind="bfb", p=p, cal=CAL, mode=mode)
    got = YB.run_path(s, b, f, 29, kind="bfb", p=p, cal=CAL, mode=mode)
    assert (got.exit_px, got.exit_reason, got.exit_gd) == (ref.exit_px, ref.exit_reason, ref.exit_gd)


def test_old_era_limit_down_lock_defers_exit():
    # 12% 시대: 둘째 날 시가 = 전일 종가 × 0.88, 고가 = 저가(잠김) → 그날 못 팔고 다음 날 시가
    o = [100, 100, 88.0, 85.0]
    h = [100, 101, 88.0, 86.0]
    l = [99, 99, 88.0, 84.0]
    c = [100, 100, 88.0, 85.0]
    b = _bars(o, h, l, c, lim=0.12)
    f = _feats(4, 0, line=99.0, low=95.0)
    p = OP.params_for("bfb", "cur", "X0")
    s = EN.Sig("X", 1, 1, 100.0, 100.0, 2.0, 99.0, 95.0, float("nan"), 1.0, True, "gap")
    got = YB.run_path(s, b, f, 3, kind="bfb", p=p, cal=CAL)
    assert got.exit_gd == 3 and got.exit_px == 85.0
    ref = OP.run_path(s, b, f, 3, kind="bfb", p=p, cal=CAL)        # 0.71 문턱이면 잠김이 아니라 88 에 판다
    assert ref.exit_gd == 2 and ref.exit_px == 88.0


def test_population_excludes_trades_spanning_jump_rows_but_keeps_cooldown():
    o = [100, 100, 101, 102, 103, 104, 105, 106]
    b = _bars(o, [x + 1 for x in o], [x - 1 for x in o], o, jump=[0, 0, 0, 1, 0, 0, 0, 0])
    f = _feats(8, 0, line=99.0, low=50.0)
    p = OP.params_for("bfb", "cur", "X0")
    s = EN.Sig("X", 1, 1, 100.0, 100.0, 2.0, 99.0, 50.0, float("nan"), 1.0, True, "gap")
    pop, jumped = YB.population([s], {"X": b}, {"X": f}, 0, 7, kind="bfb", p=p, cal=CAL)
    assert pop == [] and jumped == 1
    b2 = _bars(o, [x + 1 for x in o], [x - 1 for x in o], o)
    pop2, j2 = YB.population([s], {"X": b2}, {"X": f}, 0, 7, kind="bfb", p=p, cal=CAL)
    assert len(pop2) == 1 and j2 == 0


def test_rows_use_era_cost_by_entry_and_exit_day():
    cal = pd.DatetimeIndex(["1997-06-02", "1997-06-03", "2026-06-01", "2026-06-02"])
    cost = YB.EraCostY(cal)

    class P:
        pass
    ps = P()
    ps.s = EN.Sig("X", 0, 0, 100.0, 100.0, 2.0, 99.0, 90.0, float("nan"), 1.0, True, "gap")
    ps.E, ps.exit_px, ps.exit_gd, ps.exit_reason = 100.0, 110.0, 3, "TRAILING_STOP"
    r = YB.rows_of([ps], cal, cost, 3)[0]
    assert r["r"] == pytest.approx(0.10 - cost.buy(0) - cost.sell(3))
    assert r["g"] == pytest.approx(0.10)


def test_book_with_const_cost_equals_shared_book():
    """날짜별 비용 계좌가 일정 비용일 때 공용 ``book.run_book`` 과 평가액이 같다."""
    rng = np.random.default_rng(7)
    n = 30
    bars, feats, sigs = {}, {}, []
    for t in ("A", "B", "C"):
        c = 100 * np.cumprod(1 + rng.normal(0.003, 0.03, n))
        o = c * (1 + rng.normal(0, 0.01, n))
        h = np.maximum(o, c) * 1.01
        l = np.minimum(o, c) * 0.99
        bars[t] = _bars(o, h, l, c)
        feats[t] = _feats(n, 0, line=float(c[0]), low=float(c[0] * 0.8))
        feats[t]["atr"] = np.full(n, 2.0)
        for d in (2, 9, 17):
            sigs.append(EN.Sig(t, d, d, float(o[d]), float(o[d]), 2.0, float(c[0]), float(c[0] * 0.8),
                               float("nan"), 1.0, True, "gap"))
    cal = pd.date_range("2024-01-01", periods=n, freq="B")
    p = OP.params_for("bfb", "cur", "X0")
    sbg = {}
    for s in sigs:
        sbg.setdefault(s.gd, []).append(s)

    def size_fn(s, B, used):
        return int(B * 0.25 // s.E_raw), "ok"

    def mk(cls):
        return lambda s, q: cls(s, bars[s.ticker], feats[s.ticker], q, kind="bfb", p=p, cal=cal)
    ref = BK.run_book(sbg, mk(OP.OPos), size_fn, cal, str(cal[0].date()), str(cal[-1].date()), 3,
                      start_equity=1e6, cost_side=0.0019, max_pos=2)
    got = YB.run_book(sbg, mk(YB.YPos), size_fn, cal, str(cal[0].date()), str(cal[-1].date()), 3,
                      start_equity=1e6, cost=YB.EraCostY(cal, const=0.0038), max_pos=2)
    assert np.allclose(got["equity"], ref["equity"])
    assert abs(got["recon"]) < 1e-6 and got["counts"] == {k: v for k, v in ref["counts"].items()}
