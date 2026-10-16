"""BFB·VCP — 후보 m 계열 × on/위약 (prereg §1). 설정 코드는 앞 재측정 run_b.py 그대로.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python run_b.py <scratch> vcp|bfb
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loop as LP  # noqa: E402
CM = LP.CM

SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_bv.py")
LP.SCR = sys.argv[1]
sys.argv = [SRC, sys.argv[1], sys.argv[2]]
spec = importlib.util.spec_from_file_location("rb", SRC)
RB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RB)
YB, Y, OP, C, KIND, MU = RB.YB, RB.Y, RB.OP, RB.C, RB.KIND, RB.MU

NEW = (0.00014, 0.002)


def main():
    CM.wrap(YB, "book_summary")
    cls, featf = YB._classes(KIND)
    st, meta = Y.build()
    cal = st.cal
    RB.attach_mem(st)
    M = RB.m_series(cal)
    ser = pd.read_csv(os.path.join(LP.SCR, "series.csv"), index_col=0, parse_dates=True)
    src = {nm: (pd.DatetimeIndex(ser[nm].dropna().index), ser[nm].dropna().to_numpy(float)) for nm in ("kospi", "kosdaq")}
    cost = YB.EraCostY(cal)
    cost.fee = np.full(len(cal), NEW[0] + YB.SLIPPAGE_ALLOWANCE / 2)
    cost.tax = np.full(len(cal), NEW[1])
    p = OP.params_for(KIND, "cur", "X0")
    p.update(RB.LIVE_OVR[KIND])
    feats = {t: featf(b, p) for t, b in st.bars.items()}
    uA = Y.universe(st, meta["ratios"], KIND, mode="pct")
    _, meth, cap, k = {e[0]: e for e in OP.entries_for(KIND)}["I"]
    RB.log("ready")
    base = YB.build_signals(st.bars, feats, M["kospi"], p, uA, method=meth, cap=cap, k=k)
    for s in base:
        b = st.bars[s.ticker]
        s.mem = bool(b["mem"][s.ti - 1])
        s.kq = bool(b["kq"][s.ti - 1])

    def setm(base, mm):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.m = 1.0 if mm is None else CM.mval((mm[1] if s2.kq else mm[0])[s2.gd])
            out.append(s2)
        return out

    def book(sg, wn, vn):
        bk = RB.books(sg, st, feats, p, cls, RB.W[wn], cost, 0.0)
        return {"cagr": bk["cagr"], "mdd": bk["mdd"]}

    LP.run(KIND, cal, src, MU, base, setm, book, RB.W, os.path.join(LP.SCR, "mr", f"{KIND}.pkl"), RB.log)


if __name__ == "__main__":
    main()
