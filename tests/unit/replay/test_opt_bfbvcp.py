"""전략 효율화(2026-10-05) — vcp · bfb 탐색 층(``bfb_vcp_opt``) 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_opt_20261005/{vcp,bfb}/prereg.md``.
진입 3종(장중 추격 · 종가 확인 · 다음 날 시가)의 체결가·거름 · 종가 진입 봉 경로 없음 · 익절 끄기 ·
격자 크기 · 월 블록 차이 검정.
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

from replay.strategies import bfb_vcp_engine as EN  # noqa: E402
from replay.strategies import bfb_vcp_opt as OP  # noqa: E402

pytestmark = pytest.mark.unit


def _bars(o, h, l, c, vol=None):
    n = len(c)
    return {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
            "vol": np.array(vol if vol is not None else [1000] * n, float), "di": np.arange(n),
            "notrade": np.zeros(n, bool), "raw": np.ones(n)}


def _feats(n, i, line, low=90.0, avg=1000.0, atr=2.0, target=np.nan):
    cand = np.zeros(n, bool)
    cand[i] = True
    f = {"cand": cand, "line": np.full(n, np.nan), "low": np.full(n, np.nan), "avg": np.zeros(n),
         "atr": np.full(n, atr), "ema50": np.full(n, np.nan), "target": np.full(n, np.nan)}
    f["line"][i], f["low"][i], f["avg"][i], f["target"][i] = line, low, avg, target
    return f


def _one(method, b, f, cap=5.0, k=0.0, **kw):
    n = len(b["c"])
    return OP.build_signals_opt({"X": b}, {"X": f}, np.ones(n + 5), dict(EN.BFB_DB), {"X": np.ones(n, bool)},
                                method=method, cap=cap, k=k, **kw)


def test_grid_sizes_within_cap_and_contains_current():
    for kind in ("vcp", "bfb"):
        g = OP.grid(kind)
        assert len(g) <= 200
        assert len({x["id"] for x in g}) == len(g)
        assert OP.CURRENT_ID in {x["id"] for x in g}


def test_current_params_equal_db():
    for kind, db in (("vcp", EN.VCP_DB), ("bfb", EN.BFB_DB)):
        p = OP.params_for(kind, "cur", "X0")
        assert {k: v for k, v in p.items() if not k.startswith("_")} == db
        assert p["_target"] is True


def test_close_confirm_fills_at_close_and_needs_close_above_line():
    b = _bars([99, 100, 100], [100, 106, 104], [98, 99, 99], [99, 103, 101])
    s = _one("C", b, _feats(3, 0, line=100.0))
    assert len(s) == 1 and s[0].E == 103 and s[0].ti == 1 and s[0].entry == "close"
    # 장중 돌파했지만 종가가 선 아래 → 없음(가짜 돌파 거름)
    b2 = _bars([99, 100, 100], [100, 106, 104], [98, 99, 99], [99, 99.5, 101])
    assert _one("C", b2, _feats(3, 0, line=100.0)) == []


def test_close_confirm_chase_cap_and_volume():
    b = _bars([99, 100, 100], [100, 110, 104], [98, 99, 99], [99, 106, 101], vol=[1000, 1400, 1000])
    assert _one("C", b, _feats(3, 0, line=100.0), cap=5.0) == []          # 종가 +6% > 5%
    assert len(_one("C", b, _feats(3, 0, line=100.0), cap=7.5)) == 1
    assert _one("C", b, _feats(3, 0, line=100.0), cap=7.5, k=1.5) == []   # 1400 < 1.5 × 1000
    assert len(_one("C", b, _feats(3, 0, line=100.0), cap=7.5, k=1.2)) == 1


def test_next_open_fills_next_day_open_with_cap():
    b = _bars([99, 100, 103, 104], [100, 106, 105, 106], [98, 99, 101, 102], [99, 103, 104, 105])
    s = _one("N", b, _feats(4, 0, line=100.0))
    assert len(s) == 1 and s[0].E == 103 and s[0].ti == 2 and s[0].entry == "gap"
    assert _one("N", b, _feats(4, 0, line=100.0), cap=2.0) == []          # 다음 날 시가 103 > 102


def test_intraday_uses_live_slip():
    b = _bars([99, 100, 100], [100, 106, 104], [98, 99, 99], [99, 103, 101])
    s = _one("I", b, _feats(3, 0, line=100.0))
    assert len(s) == 1 and s[0].E == pytest.approx(100 * (1 + OP.LIVE_SLIP))


def test_close_entry_has_no_entry_bar_path():
    b = _bars([99, 100, 100], [100, 106, 104], [98, 80, 99], [99, 103, 101])   # 진입 봉 저가 80
    f = _feats(3, 0, line=100.0, low=95.0)
    s = _one("C", b, f)[0]
    cal = pd.date_range("2024-01-01", periods=10, freq="D")
    ps = OP.run_path(s, b, f, 10, kind="bfb", p=OP.params_for("bfb", "cur", "X0"), cal=cal)
    assert ps.exit_gd != 1                                                    # 종가 뒤 경로만 본다(저가 80 무시)


def test_target_off():
    b = _bars([99, 100, 103, 101], [100, 106, 130, 102], [98, 99, 102, 100], [99, 103, 104, 101])
    f = _feats(4, 0, line=100.0, low=90.0, target=120.0)
    cal = pd.date_range("2024-01-01", periods=10, freq="D")
    s = _one("C", b, f)[0]
    on = OP.run_path(s, b, f, 3, kind="bfb", p=OP.params_for("bfb", "cur", "X0"), cal=cal)
    off = OP.run_path(s, b, f, 3, kind="bfb", p=OP.params_for("bfb", "cur", "X3"), cal=cal)
    assert on.exit_reason == "TAKE_PROFIT" and on.exit_px == 120.0
    assert off.exit_reason != "TAKE_PROFIT"


def test_month_block_diff_sign():
    a = [{"d": f"2024-{m:02d}-01", "r": 0.02} for m in range(1, 13) for _ in range(3)]
    b = [{"d": f"2024-{m:02d}-02", "r": 0.0} for m in range(1, 13) for _ in range(3)]
    r = OP.month_block_diff(a, b, n_boot=500, qs=(0.05,))
    assert r["est"] == pytest.approx(0.02) and r["lower"]["0.05"] > 0
