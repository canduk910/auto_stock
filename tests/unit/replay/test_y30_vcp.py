"""30년 재검증(2026-10-06) — 시대 규칙 · 비용 · 유니버스 · 진입 신호(VCP 쪽) 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_30y_20261006/vcp/prereg.md``.
30% 시대에는 전수 점검 · 효율화 엔진과 결과가 같아야 하고(대조), 그 전 시대에는 그 시대 제한폭을 쓴다.
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

from replay.audit import bars as BR  # noqa: E402
from replay.strategies import bfb_vcp_engine as EN  # noqa: E402
from replay.strategies import bfb_vcp_opt as OP  # noqa: E402
from replay.strategies import y30_bfbvcp as YB  # noqa: E402
from replay.strategies import y30_data as Y  # noqa: E402

pytestmark = pytest.mark.unit


def _bars(o, h, l, c, vol=None, lim=0.30, jump=None):
    n = len(c)
    return {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
            "vol": np.array(vol if vol is not None else [1000] * n, float), "di": np.arange(n),
            "notrade": np.zeros(n, bool), "raw": np.ones(n), "lim": np.full(n, lim),
            "jump": np.zeros(n, bool) if jump is None else np.array(jump, bool)}


def _feats(n, i, line, low=90.0, avg=1000.0, atr=2.0, target=np.nan):
    cand = np.zeros(n, bool)
    cand[i] = True
    f = {"cand": cand, "line": np.full(n, np.nan), "low": np.full(n, np.nan), "avg": np.zeros(n),
         "atr": np.full(n, atr), "ema50": np.full(n, np.nan), "target": np.full(n, np.nan)}
    f["line"][i], f["low"][i], f["avg"][i], f["target"][i] = line, low, avg, target
    return f


def _sig_tuple(s):
    return (s.ticker, s.ti, s.gd, round(s.E, 9), round(s.E_raw, 9), s.N, s.line, s.entry)


# ── 시대 규칙 ──────────────────────────────────────────────────────────────

def test_limit_thresholds_equal_operating_in_30pct_era():
    # 30% 시대 = 운영 1.29 · 0.71 과 같은 문턱
    assert YB.limit_up(129.0, 100.0, 0.30) == BR.limit_up_open(129.0, 100.0)
    assert YB.limit_up(128.9, 100.0, 0.30) == BR.limit_up_open(128.9, 100.0)
    assert YB.locked_down(71.0, 71.0, 71.0, 100.0, 0.30) == BR.locked_limit_down(71.0, 71.0, 71.0, 100.0)


def test_limit_thresholds_use_era_limit():
    # 15% 시대: +14.5% 시가 = 상한가(운영 1.29 문턱이면 못 잡는다)
    assert YB.limit_up(114.6, 100.0, 0.15) and not BR.limit_up_open(114.6, 100.0)
    assert not YB.limit_up(113.0, 100.0, 0.15)
    # 6% 시대 하한가 잠김
    assert YB.locked_down(94.0, 94.0, 94.0, 100.0, 0.06)
    assert not YB.locked_down(94.0, 95.0, 94.0, 100.0, 0.06)


def test_limit_table_dates():
    tab = Y.load_limit_table()
    d = pd.DatetimeIndex(["1996-06-03", "1997-06-02", "1998-06-01", "2000-06-01", "2006-06-01", "2016-06-01"])
    kospi = Y.limit_for(np.zeros(6, int), d, tab)
    kosdaq = Y.limit_for(np.ones(6, int), d, tab)
    assert list(kospi) == [0.06, 0.08, 0.12, 0.15, 0.15, 0.30]
    assert list(kosdaq) == [0.30, 0.08, 0.12, 0.12, 0.15, 0.30] or list(kosdaq)[1:] == [0.08, 0.12, 0.12, 0.15, 0.30]


def test_era_cost_main_and_const():
    cal = pd.DatetimeIndex(["1997-06-02", "2000-06-01", "2010-06-01", "2026-06-01"])
    c = YB.EraCostY(cal)
    assert c.rt(0, 0) == pytest.approx(0.0130 + 0.0015)
    assert c.rt(1, 1) == pytest.approx(0.0050 + 0.0015)
    assert c.rt(2, 2) == pytest.approx(0.0036 + 0.0015)
    assert c.rt(3, 3) == pytest.approx(0.0038)                # 규약 문구 「2026 약 0.38%」
    # 매수일·매도일 비용이 다르면 매수 = 그날 수수료, 매도 = 그날 수수료 + 거래세
    assert c.rt(0, 3) == pytest.approx((0.005 + 0.00075) + (0.00015 + 0.00075 + 0.002))
    k = YB.EraCostY(cal, const=0.0038)
    assert all(k.rt(i, j) == pytest.approx(0.0038) for i in range(4) for j in range(4))


def test_universe_pct_and_nominal():
    st = type("S", (), {})()
    n = 3
    st.bars = {"A": {"c_raw": np.full(n, 10_000.0), "notrade": np.zeros(n, bool), "jump": np.array([0, 1, 0], bool),
                     "mc_pct": np.array([0.1, 0.1, 0.99]), "tv_pct": np.array([0.2, 0.2, 0.2]),
                     "mktcap": np.full(n, 2e10), "tv": np.full(n, 2e9)},
               "B": {"c_raw": np.full(n, 1_000.0), "notrade": np.zeros(n, bool), "jump": np.zeros(n, bool),
                     "mc_pct": np.full(n, 0.1), "tv_pct": np.full(n, 0.1), "mktcap": np.full(n, 2e10),
                     "tv": np.full(n, 2e9)}}
    r = {"mcap": 0.9, "tv_vcp": 0.3, "tv_bfb": 0.25}
    u = Y.universe(st, r, "vcp", mode="pct")
    assert list(u["A"]) == [True, False, False]                 # 표시 행 · 시총 순위 밖
    assert not u["B"].any()                                     # 가격 필터 3,000 미만
    un = Y.universe(st, r, "vcp", mode="nominal")
    assert list(un["A"]) == [True, False, True]


# ── 진입 신호 — 30% 시대 대조 ───────────────────────────────────────────────

def _rand_case(seed):
    rng = np.random.default_rng(seed)
    n = 60
    c = 100 * np.cumprod(1 + rng.normal(0, 0.03, n))
    o = c * (1 + rng.normal(0, 0.02, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.02, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.02, n)))
    vol = rng.integers(500, 3000, n).astype(float)
    b = _bars(o, h, l, c, vol)
    f = _feats(n, 0, line=1.0)
    f["cand"][:] = rng.random(n) < 0.3
    f["line"] = c * (1 + rng.uniform(-0.02, 0.06, n))
    f["low"] = c * 0.9
    f["avg"] = np.full(n, 1200.0)
    return b, f


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("slip", [0.0, 0.0193])
def test_intraday_signals_equal_audit_engine_in_30pct_era(seed, slip):
    b, f = _rand_case(seed)
    n = len(b["c"])
    p = dict(EN.VCP_DB)
    ref = EN.build_signals({"X": b}, {"X": f}, np.ones(n + 2), p, {"X": np.ones(n, bool)}, slip=slip)
    got = YB.build_signals({"X": b}, {"X": f}, np.ones(n + 2), p, {"X": np.ones(n, bool)}, method="I",
                           cap=p["max_breakout_extension_pct"], k=0.0, slip=slip)
    assert [_sig_tuple(s) for s in got] == [_sig_tuple(s) for s in ref]


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("meth,k", [("C", 0.0), ("C", 1.5), ("N", 0.0)])
def test_close_and_next_signals_equal_opt_engine_in_30pct_era(seed, meth, k):
    b, f = _rand_case(seed)
    n = len(b["c"])
    p = dict(EN.VCP_DB)
    ref = OP.build_signals_opt({"X": b}, {"X": f}, np.ones(n + 2), p, {"X": np.ones(n, bool)}, method=meth,
                               cap=3.0, k=k)
    got = YB.build_signals({"X": b}, {"X": f}, np.ones(n + 2), p, {"X": np.ones(n, bool)}, method=meth,
                           cap=3.0, k=k)
    assert [_sig_tuple(s) for s in got] == [_sig_tuple(s) for s in ref]


def test_entry_bar_jump_flag_blocks_signal():
    b = _bars([99, 100, 100], [100, 106, 104], [98, 99, 99], [99, 103, 101], jump=[0, 1, 0])
    f = _feats(3, 0, line=100.0)
    for meth in ("I", "C"):
        assert YB.build_signals({"X": b}, {"X": f}, np.ones(5), dict(EN.VCP_DB), {"X": np.ones(3, bool)},
                                method=meth, cap=7.5, k=0.0) == []


def test_old_era_limit_up_open_blocks_intraday_entry():
    # 15% 시대, 시가 +14.6%(상한가) — 돌파선 위 추격 상한 안이어도 못 산다
    b = _bars([100, 114.6, 110], [100, 114.6, 112], [99, 114.6, 108], [100, 114.6, 110], lim=0.15)
    f = _feats(3, 0, line=110.0)
    assert YB.build_signals({"X": b}, {"X": f}, np.ones(5), dict(EN.VCP_DB), {"X": np.ones(3, bool)},
                            method="I", cap=7.5, k=0.0, slip=0.0) == []
    b30 = _bars([100, 114.6, 110], [100, 114.6, 112], [99, 114.6, 108], [100, 114.6, 110], lim=0.30)
    assert len(YB.build_signals({"X": b30}, {"X": f}, np.ones(5), dict(EN.VCP_DB), {"X": np.ones(3, bool)},
                                method="I", cap=7.5, k=0.0, slip=0.0)) == 1


def test_hypothesis_ids_are_in_grid():
    for kind in ("vcp", "bfb"):
        ids = {g["id"] for g in OP.grid(kind)}
        assert set(YB.HYP[kind].values()) <= ids and YB.CURRENT_ID in ids
