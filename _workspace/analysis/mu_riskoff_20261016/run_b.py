"""BFB·VCP — on / off / 위약 8판 × NEW · 씨앗별 자산곡선 (prereg §1·§4).

재사용: 앞 재백테스트 run_b.py 와 같이 ``index_universe_20261015/run_bv.py`` 의 books·m_series·attach_mem 그대로.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python run_b.py <scratch> vcp|bfb
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as CM  # noqa: E402

SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_bv.py")
sys.argv = [SRC, sys.argv[1], sys.argv[2]]
spec = importlib.util.spec_from_file_location("rb", SRC)
RB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RB)
YB, Y, OP, C, KIND = RB.YB, RB.Y, RB.OP, RB.C, RB.KIND

NEW = (0.00014, 0.002)


def main():
    CM.wrap(YB, "book_summary")
    cls, featf = YB._classes(KIND)
    st, meta = Y.build()
    cal = st.cal
    RB.attach_mem(st)
    M = RB.m_series(cal)
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

    def variant(mk, mq):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.m = 1.0 if mk is None else CM.mval((mq if s2.kq else mk)[s2.gd])
            out.append(s2)
        return out

    V = {"on": (M["kospi"], M["kosdaq"]), "off": (None, None)}
    for sh in CM.SHIFTS:
        V[f"plc{sh}"] = (CM.shifted(M["kospi"], sh), CM.shifted(M["kosdaq"], sh))
    R = {"cal": np.asarray(cal), "m": {"kospi": M["kospi"], "kosdaq": M["kosdaq"]}, "book": {}, "curves": {}}
    for vn, (mk, mq) in V.items():
        sg = variant(mk, mq)
        wins = ("T", "V", "H") if vn in ("on", "off") else ("T", "V")
        for wn in wins:
            win = RB.W[wn]
            bk = RB.books(sg, st, feats, p, cls, win, cost, 0.0)
            R["book"][(vn, wn)] = {"cagr": bk["cagr"], "mdd": bk["mdd"]}
            R["curves"][(vn, wn)] = CM.curves(CM.take(), cal, win)
            RB.log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    CM.dump(os.path.join(sys.argv[1], "mr", f"{KIND}.pkl"), R)
    RB.log("done")


if __name__ == "__main__":
    main()
