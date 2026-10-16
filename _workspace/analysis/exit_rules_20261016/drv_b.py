"""BFB·VCP — 모집단 덤프(pop) · 계좌 변형(acct). 설정 코드는 mu_datadriven run_b.py 그대로.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python drv_b.py <scratch> vcp|bfb pop|acct
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "mu_riskoff_20261016"))
import common as CM  # noqa: E402
import xcommon as X  # noqa: E402

SCR, KIND_, MODE = sys.argv[1], sys.argv[2], sys.argv[3]
SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_bv.py")
sys.argv = [SRC, SCR, KIND_]
spec = importlib.util.spec_from_file_location("rb", SRC)
RB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RB)
YB, Y, OP, C, KIND, MU = RB.YB, RB.Y, RB.OP, RB.C, RB.KIND, RB.MU
NEW = (0.00014, 0.002)
OVR = {"ovr": None, "pos": None, "post": None}
EXIT_KEYS = ("stop_atr", "turtle_min_stop_pct", "turtle_backstop_pct", "atr_trail_mult", "breakeven_promote_atr", "max_hold_days")


def main():
    CM.wrap(YB, "book_summary")
    cls, featf = YB._classes(KIND)
    st, meta = Y.build()
    cal = st.cal
    RB.attach_mem(st)
    cost = YB.EraCostY(cal)
    cost.fee = np.full(len(cal), NEW[0] + YB.SLIPPAGE_ALLOWANCE / 2)
    cost.tax = np.full(len(cal), NEW[1])
    p = OP.params_for(KIND, "cur", "X0")
    p.update(RB.LIVE_OVR[KIND])
    feats = {t: featf(b, p) for t, b in st.bars.items()}
    uA = Y.universe(st, meta["ratios"], KIND, mode="pct")
    _, meth, cap, k = {e[0]: e for e in OP.entries_for(KIND)}["I"]
    M = RB.m_series(cal)
    RB.log("ready")
    base = YB.build_signals(st.bars, feats, M["kospi"], p, uA, method=meth, cap=cap, k=k)
    for s in base:
        b = st.bars[s.ticker]
        s.mem = bool(b["mem"][s.ti - 1])
        s.kq = bool(b["kq"][s.ti - 1])
    prev = pickle.load(open(os.path.join(SCR, "md", f"{KIND}.pkl"), "rb"))
    V0 = (np.asarray(prev["m"]["V0"]["kospi"], float), np.asarray(prev["m"]["V0"]["kosdaq"], float))

    def setm(mm):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.m = CM.mval((mm[1] if s2.kq else mm[0])[s2.gd])
            out.append(s2)
        return out

    sg = setm(V0)
    if MODE == "pop":
        cd = int(p["reentry_cooldown_days"])
        recs = []
        for wn, win in RB.W.items():
            g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
            g1 = int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
            busy = {}
            for s in sorted(sg, key=lambda s: (s.gd, s.ticker)):
                if s.gd < g0 or s.gd > g1 or s.m <= 0 or busy.get(s.ticker, -1) >= s.gd:
                    continue
                ps = YB.run_path(s, st.bars[s.ticker], feats[s.ticker], g1, kind=KIND, p=p, cal=cal)
                busy[s.ticker] = (ps.exit_gd + cd) if ps.exit_gd is not None else 10 ** 9
                recs.append(X.pop_record(ps, st.bars[s.ticker], s.kq, wn))
            RB.log("pop", wn, len(recs))
        X.dump(os.path.join(SCR, "xr", f"pop_{KIND}.pkl"), {"cal": np.asarray(cal), "recs": recs,
                                                            "cur": {k_: p.get(k_) for k_ in EXIT_KEYS}})
        return

    specs = json.load(open(os.path.join(HERE, "variants.json")))[KIND]
    ist = X.index_state(cal, os.path.join(SCR, "series.csv"))
    X.patch_overlay(YB.YPos)
    X.patch_exit_line(YB.YPos, lambda ps: max(l.price for l in ps._lines()))
    X.patch_init_params(YB.YPos, "p", OVR)
    spells = X.crash_spells(cal, os.path.join(SCR, "series.csv"))
    R = {"cal": np.asarray(cal), "book": {}, "curves": {}, "trades": {}, "m6": {}}
    for vn, sp in specs.items():
        OVR["ovr"] = sp.get("ovr") or None
        X.CFG["crash"] = None if sp.get("crash") is None else X.crash_flags(cal, ist, sp["crash"], sp.get("shift", 0))
        X.CFG["stall"] = sp.get("stall")
        for wn in sp["wins"]:
            bk = RB.books(sg, st, feats, p, cls, RB.W[wn], cost, 0.0)
            runs = CM.take()
            R["book"][(vn, wn)] = {"cagr": bk["cagr"], "mdd": bk["mdd"]}
            cv = CM.curves(runs, cal, RB.W[wn])
            R["curves"][(vn, wn)] = [{"dates": c["dates"], "eq": c["eq"], "inv": c["inv"].astype(np.float32),
                                      "npos": c["npos"].astype(np.int16)} for c in cv]
            if "|" not in vn:
                R["trades"][(vn, wn)] = X.trade_rows(runs, st.bars, 2 * NEW[0] + NEW[1] + YB.SLIPPAGE_ALLOWANCE, cal)
                g0 = int(cal.searchsorted(pd.Timestamp(RB.W[wn][0])))
                R["m6"][(vn, wn)] = X.m6(runs, cv, st.bars, cal, spells, g0)
            if vn == "V0":
                pv = prev["book"][("V0", wn)]
                d = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                RB.log("repro-book", wn, d)
                if d > 1e-9:
                    raise SystemExit("V0 계좌 재현 실패 — 중단")
            RB.log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    X.dump(os.path.join(SCR, "xr", f"acct_{KIND}.pkl"), R)
    RB.log("done")


if __name__ == "__main__":
    main()
