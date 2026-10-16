"""donchian — 후보 m 계열 × on/위약 (prereg §1). 설정 코드는 앞 재측정 run_d.py 그대로.
지수 원천 = 앞 재측정과 같은 보관소 index/krx_kospi.csv · krx_kosdaq.csv.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python run_d.py <scratch>
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loop as LP  # noqa: E402
CM = LP.CM

SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_donchian.py")
LP.SCR = sys.argv[1]
sys.argv = [SRC, sys.argv[1]]
spec = importlib.util.spec_from_file_location("rd", SRC)
RD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RD)
Y, DK, DA, J, BK, C, MU = RD.Y, RD.DK, RD.DA, RD.J, RD.BK, RD.C, RD.MU

NEW = (0.00014, 0.002)


def main():
    CM.wrap(BK, "book_summary")
    st, M, info = RD.build()
    cal = st.cal
    src = {}
    for nm, fn in (("kospi", "krx_kospi.csv"), ("kosdaq", "krx_kosdaq.csv")):
        ix = pd.read_csv(os.path.join(RD.LONG, "index", fn))
        ix["date"] = pd.to_datetime(ix["date"])
        ix = ix.dropna(subset=["close"]).sort_values("date")
        src[nm] = (pd.DatetimeIndex(ix.date), ix.close.to_numpy(float))
    Y._CAL["cal"] = cal
    bars = st.bars
    cst = Y.Costs(cal, 0.0)
    cst.buy = np.full(len(cal), NEW[0])
    cst.sell = np.full(len(cal), NEW[0] + NEW[1])
    cst.tag = "new"
    kk = Y.kk_of(Y.EXIT0)
    feats = {}
    for t, b in bars.items():
        bb = dict(b)
        bb["mem"] = b["common"]
        feats[t] = Y.features_y30(bb, entry_n=20, vol_mult=1.5, clv=None, tv_mode="pct")
    RD.log("features")
    fv = {}
    for t, f in feats.items():
        g = dict(f)
        g["cond"] = f["cond"] & bars[t]["mem"]
        fv[t] = g
    base = DK.build_signals(bars, fv, M["kospi"])
    base = [s for s in base if not DA.r_half_blocked(s.E, s.N, kk)]
    for s in base:
        b = bars[s.ticker]
        s.mem = bool(b["mem"][s.ti - 1])
        s.kq = bool(b["kq"][s.ti - 1])
        s.mcap_rank = None
    cls = RD.load_strategy_class(RD.BRANCH, "DonchianSwingStrategy", "du_branch")

    def make_op(mode):
        return RD.OpSizer(cls, "donchian_swing", {"market_unit_mode": mode, "risk_pct": 0.012, "position_ratio": 0.15,
                                                  "max_positions": 6, "kk_r_floor_pct": 8.0, "kk_r_atr_mult": 1.5})
    OPS = {"off": make_op("off"), "enforce": make_op("enforce")}

    def book(sg, w, vn):
        op = OPS["off" if vn == "off" else "enforce"]

        def opsize(s, B, used):
            P = int(round(s.E_raw))
            if s.m <= 0 or P <= 0:
                return 0, "mu"
            q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
            return (q, "ok") if q > 0 else (0, "funds" if int(B) - int(used) < P else "design")
        sbg = defaultdict(list)
        for s in sg:
            sbg[s.gd].append(s)

        def open_pos(s, q):
            return Y.Y30Pos(s, bars[s.ticker], feats[s.ticker], q, mode="color", kk=kk)
        runs = [RD.run_book(sbg, open_pos, opsize, cal, RD.WINDOWS[w][0], RD.WINDOWS[w][1], sd,
                            start_equity=float(C.BUDGET_C7), costs=cst, max_pos=6, daily_cap=3,
                            slip_of=lambda s: 0.0, prio=None) for sd in C.BOOK_SEEDS]
        sm = BK.book_summary(runs, float(C.BUDGET_C7))
        return {"cagr": sm["cagr_median"], "mdd": sm["mdd_median"]}

    def setm(base, mm):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.m = 1.0 if mm is None else CM.mval((mm[1] if s2.kq else mm[0])[s2.gd])
            out.append(s2)
        return out

    LP.run("donchian", cal, src, MU, base, setm, book, RD.WINDOWS, os.path.join(LP.SCR, "mr", "donchian.pkl"), RD.log)


if __name__ == "__main__":
    main()
