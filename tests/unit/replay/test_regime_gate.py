"""장세 문 연구 — 쉬는 집합 후보 · 쉼 마스크 · 60/40 변형 일정(데이터 없이)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import global_alloc_b as GB  # noqa: E402
from replay import regime_gate as RG  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402


def _mkt(n=90):
    dates = pd.bdate_range("2020-01-01", periods=n)
    z = np.zeros((n, GB.N))
    return GB.Mkt(dates, z.copy(), z.copy(), np.full(n, 1 / 365), np.zeros(GB.N, bool), np.zeros(GB.N))


def test_subsets_are_0_to_5_cells_in_tiebreak_order():
    s = RG.subsets()
    assert len(s) == 63
    assert s[0] == ()
    assert s[1] == ("UL",)
    assert all(len(x) <= 5 for x in s)
    assert [len(x) for x in s] == sorted(len(x) for x in s)


def test_rest_mask_ignores_missing_label():
    m = RG.rest_mask(np.array(["UL", None, "SL", "DH"], dtype=object), ("UL", "DH"))
    assert m.tolist() == [True, False, False, True]


def test_gated_schedule_switches_to_cash_on_rest_and_back():
    m = _mkt()
    st = np.array(["SL"] * 30 + ["DH"] * 20 + ["SL"] * 40, dtype=object)
    sc = RA.gated_schedule(m, "B1", ("DH",), 0, 89, st)
    assert sc[30][GB.I_CASH] == 1.0 and sc[0][GB.COLS.index("K200")] == 0.6
    assert sc[50][GB.COLS.index("K200")] == 0.6


def test_variants_v1_v2_v3():
    m = _mkt()
    st = np.array(["SL"] * 20 + ["UL"] * 20 + ["SH"] * 50, dtype=object)
    lk = GB.COLS.index("LK200")
    for kind, before, after in (("V1", "N", "N"), ("V2", "C", "C"), ("V3", "N", "C")):
        sc, cat = RA.variant_schedule(m, kind, 0.9, "LK200", 0, 89, st)
        assert cat[10] == before and cat[25] == "L" and cat[60] == after
        assert abs(sc[20][lk] - 0.9) < 1e-12 and abs(sc[20][GB.I_CASH] - 0.1) < 1e-12
        assert 40 in sc                                   # 이탈일이 결정일이다
