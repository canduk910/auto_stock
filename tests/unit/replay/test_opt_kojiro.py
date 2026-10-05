"""kojiro 효율화(2026-10-05) — 탐색 축 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_opt_20261005/kojiro/prereg.frozen.md`` §2·§3. 네트워크·DB·보관소 0.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.strategies import kojiro as KJ  # noqa: E402
from replay.strategies import kojiro_opt as KO  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy  # noqa: E402

pytestmark = pytest.mark.unit

P = {**KojiroStrategy.DEFAULT_PARAMS, "breakeven_promote_atr": 1.5, "sizing_mode": "turtle",
     "position_ratio": 0.166, "max_positions": 6, "market_unit_mode": "enforce"}


def _bars(o, h, l, c):
    n = len(c)
    return {"di": np.arange(n), "o": np.asarray(o, float), "h": np.asarray(h, float), "l": np.asarray(l, float),
            "c": np.asarray(c, float), "o_raw": np.asarray(o, float), "c_raw": np.asarray(c, float),
            "raw": np.ones(n), "tv": np.full(n, 5e9), "vol": np.full(n, 1e5), "mktcap": np.full(n, 1e11),
            "notrade": np.zeros(n, dtype=bool)}


def _flat(n, px=100.0):
    return _bars([px] * n, [px + 0.5] * n, [px - 0.5] * n, [px] * n)


def _feat(n, N=2.0):
    return {"atr": np.full(n, N), "stage": np.ones(n, dtype=np.int8)}


def _sig(ti=1, E=100.0, m=1.0, t="005930", score=0.0, gd=None):
    return KJ.Sig(t, ti, ti if gd is None else gd, E, E, 2.0, m, score=score)


def test_slip_scales_entry_prices_only():
    s = KO.slip_sig(_sig(E=100.0), 0.0076)
    assert s.E == pytest.approx(100.76) and s.E_raw == pytest.approx(100.76)
    assert s.N == 2.0 and s.m == 1.0 and s.ti == 1
    assert KO.slip_sig(_sig(), 0.0) .E == 100.0


def test_slipped_entry_moves_stop_lines():
    b, f = _flat(5), _feat(5)
    ps = KO.OptPos(KO.slip_sig(_sig(), 0.01), b, f, 1, P)
    assert ps.pct_line == pytest.approx(101.0 * 0.92)
    assert ps.floor == pytest.approx(101.0 - 2 * 2.0)


def test_time_exit_on_open_of_bar_after_time_n():
    n = 30
    b, f = _flat(n), _feat(n)
    ps = KO.run_path(_sig(ti=1), b, f, P, end_gd=n - 1, time_n=15)
    assert ps.exit_reason == "TIME_EXIT" and ps.exit_gd == 16 and ps.exit_px == 100.0


def test_no_time_exit_when_none():
    n = 30
    b, f = _flat(n), _feat(n)
    ps = KO.run_path(_sig(ti=1), b, f, P, end_gd=n - 1, time_n=None)
    assert ps.exit_reason == "END"


def test_operating_open_exit_precedes_time_exit():
    n = 20
    o = [100.0] * n
    o[16] = 80.0                      # 16번째 봉 시가가 −8% 받침 아래 → 손절이 먼저
    b = _bars(o, [x + 0.5 for x in o], [x - 0.5 for x in o], o)
    ps = KO.run_path(_sig(ti=1), b, _feat(n), P, end_gd=n - 1, time_n=15)
    assert ps.exit_reason == "STOP_LOSS" and ps.exit_gd == 16


def test_time_exit_waits_for_unlocked_day():
    n = 20
    o, h, l, c = [100.0] * n, [100.5] * n, [99.5] * n, [100.0] * n
    o[16] = h[16] = l[16] = c[16] = 69.0      # 하한가 잠김(시가 ≤ 전일 × 0.71 ∧ 고가 = 저가)
    b = _bars(o, h, l, c)
    ps = KO.run_path(_sig(ti=1), b, _feat(n), {**P, "hard_stop_pct": -50.0, "stop_atr": 40.0}, end_gd=n - 1,
                     time_n=15)
    assert ps.exit_gd == 17 and ps.exit_reason == "TIME_EXIT"


def test_mu_rules():
    assert [KO.mu_keep(m, "cur") for m in (1.0, 0.75, 0.5, 0.0)] == [True, True, True, False]
    assert [KO.mu_keep(m, "only1") for m in (1.0, 0.75, 0.5, 0.0)] == [True, False, False, False]
    assert [KO.mu_keep(m, "no075") for m in (1.0, 0.75, 0.5, 0.0)] == [True, False, True, False]


def test_top_k_keeps_highest_scores_per_day():
    sigs = [_sig(t="A", gd=5, score=0.1), _sig(t="B", gd=5, score=0.9), _sig(t="C", gd=5, score=0.5),
            _sig(t="D", gd=6, score=0.2)]
    got = KO.top_k(sigs, 2)
    assert [s.ticker for s in got] == ["B", "C", "D"]
    assert KO.top_k(sigs, None) == sigs


def test_population_memo_equals_audit_population_at_current_config():
    rng = np.random.default_rng(3)
    bars, feats, sigs = {}, {}, []
    for k, t in enumerate(("000001", "000002", "000003")):
        n = 120
        c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
        o = c * np.exp(rng.normal(0, 0.005, n))
        h, l = np.maximum(o, c) * 1.01, np.minimum(o, c) * 0.99
        bars[t] = _bars(o, h, l, c)
        feats[t] = {"atr": np.full(n, 2.0), "stage": rng.choice([1, 1, 1, 2, 3], n).astype(np.int8)}
        for ti in range(5, 110, 7 + k):
            sigs.append(KJ.Sig(t, ti, ti, float(o[ti]), float(o[ti]), 2.0, [1.0, 0.75, 0.5, 0.0][ti % 4]))
    ref = KJ.population(sorted(sigs, key=lambda s: (s.gd, s.ticker)), bars, feats, P, 0, 115)
    memo = KO.PathMemo(bars, feats, P)
    got = KO.population_memo(sigs, memo, KO.ExitCfg(be=1.5, trail=2.5, time_n=None), 0, 115, 0.0)
    assert [(x.s.ticker, x.s.ti, x.exit_gd, x.exit_reason, round(x.exit_px, 9)) for x in got] == \
        [(x.s.ticker, x.s.ti, x.exit_gd, x.exit_reason, round(x.exit_px, 9)) for x in ref]
    again = KO.population_memo(sigs, memo, KO.ExitCfg(be=1.5, trail=2.5, time_n=None), 0, 115, 0.0)
    assert all(a is b for a, b in zip(got, again))           # 기억된 경로를 다시 쓴다


def test_exit_cfg_overrides_be_and_trail():
    q = KO.ExitCfg(be=0.0, trail=3.5).params(P)
    assert q["breakeven_promote_atr"] == 0.0 and q["trail_atr"] == 3.5 and q["stop_atr"] == P["stop_atr"]
