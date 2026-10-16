"""donchian — 모집단 덤프(pop) · 계좌 변형(acct). 설정 코드는 mu_datadriven run_d.py 그대로.
손절 폭(R)은 사이징(risk_pct÷R)에도 들어가므로 변형의 kk 값을 사이저에도 같이 넣는다(prereg §4 D-U).
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python drv_d.py <scratch> pop|acct
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import pickle
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "mu_riskoff_20261016"))
import common as CM  # noqa: E402
import xcommon as X  # noqa: E402

SCR, MODE = sys.argv[1], sys.argv[2]
SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_donchian.py")
sys.argv = [SRC, SCR]
spec = importlib.util.spec_from_file_location("rd", SRC)
RD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RD)
Y, DK, DA, J, BK, C, MU = RD.Y, RD.DK, RD.DA, RD.J, RD.BK, RD.C, RD.MU
NEW = (0.00014, 0.002)


def main():
    CM.wrap(BK, "book_summary")
    st, M, info = RD.build()
    cal = st.cal
    Y._CAL["cal"] = cal
    bars = st.bars
    cst = Y.Costs(cal, 0.0)
    cst.buy = np.full(len(cal), NEW[0])
    cst.sell = np.full(len(cal), NEW[0] + NEW[1])
    cst.tag = "new"
    kk0 = Y.kk_of(Y.EXIT0)
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
    base = [s for s in base if not DA.r_half_blocked(s.E, s.N, kk0)]
    for s in base:
        b = bars[s.ticker]
        s.mem = bool(b["mem"][s.ti - 1])
        s.kq = bool(b["kq"][s.ti - 1])
        s.mcap_rank = None
    cls = RD.load_strategy_class(RD.BRANCH, "DonchianSwingStrategy", "du_branch")
    prev = pickle.load(open(os.path.join(SCR, "md", "donchian.pkl"), "rb"))
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
        recs = []
        for wn, win in RD.WINDOWS.items():
            g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
            g1 = int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
            busy = {}
            for s in sorted(sg, key=lambda s: (s.gd, s.ticker)):
                if s.gd < g0 or s.gd > g1 or s.m <= 0 or busy.get(s.ticker, -1) >= s.gd:
                    continue
                ps = Y.run_path(s, bars[s.ticker], feats[s.ticker], g1, kk=kk0)
                busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
                recs.append(X.pop_record(ps, bars[s.ticker], s.kq, wn))
            RD.log("pop", wn, len(recs))
        X.dump(os.path.join(SCR, "xr", "pop_donchian.pkl"), {"cal": np.asarray(cal), "recs": recs,
                                                             "cur": {"r_floor": kk0["r_floor"], "r_atr": kk0["r_atr"],
                                                                     "be_r": kk0["be_r"], "time_bars": kk0["time_bars"]}})
        return

    specs = json.load(open(os.path.join(HERE, "variants.json")))["donchian"]
    ist = X.index_state(cal, os.path.join(SCR, "series.csv"))
    X.patch_overlay(Y.Y30Pos)
    X.patch_exit_line(Y.Y30Pos, lambda ps: max(l.price for l in ps._lines()))
    spells = X.crash_spells(cal, os.path.join(SCR, "series.csv"))

    def make_op(mode, rf, ra):
        return RD.OpSizer(cls, "donchian_swing", {"market_unit_mode": mode, "risk_pct": 0.012, "position_ratio": 0.15,
                                                  "max_positions": 6, "kk_r_floor_pct": rf, "kk_r_atr_mult": ra})

    R = {"cal": np.asarray(cal), "book": {}, "curves": {}, "trades": {}, "m6": {}}
    for vn, sp in specs.items():
        ov = sp.get("ovr") or {}
        kk = dict(kk0, **{k: v for k, v in ov.items() if k in ("r_floor", "r_atr")})
        op = make_op("enforce", kk["r_floor"] * 100.0, kk["r_atr"])
        X.CFG["crash"] = None if sp.get("crash") is None else X.crash_flags(cal, X_ist(ist), sp["crash"], sp.get("shift", 0))
        X.CFG["stall"] = sp.get("stall")

        def opsize(s, B, used, op=op):
            P = int(round(s.E_raw))
            if s.m <= 0 or P <= 0:
                return 0, "mu"
            q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
            return (q, "ok") if q > 0 else (0, "funds" if int(B) - int(used) < P else "design")
        sbg = defaultdict(list)
        for s in sg:
            sbg[s.gd].append(s)

        def open_pos(s, q, kk=kk):
            return Y.Y30Pos(s, bars[s.ticker], feats[s.ticker], q, mode="color", kk=kk)
        for wn in sp["wins"]:
            runs = [RD.run_book(sbg, open_pos, opsize, cal, RD.WINDOWS[wn][0], RD.WINDOWS[wn][1], sd,
                                start_equity=float(C.BUDGET_C7), costs=cst, max_pos=6, daily_cap=3,
                                slip_of=lambda s: 0.0, prio=None) for sd in C.BOOK_SEEDS]
            sm = BK.book_summary(runs, float(C.BUDGET_C7))
            runs = CM.take()
            bk = {"cagr": sm["cagr_median"], "mdd": sm["mdd_median"]}
            R["book"][(vn, wn)] = bk
            cv = CM.curves(runs, cal, RD.WINDOWS[wn])
            R["curves"][(vn, wn)] = [{"dates": c["dates"], "eq": c["eq"], "inv": c["inv"].astype(np.float32),
                                      "npos": c["npos"].astype(np.int16)} for c in cv]
            if "|" not in vn:
                R["trades"][(vn, wn)] = X.trade_rows(runs, bars, 2 * NEW[0] + NEW[1], cal)
                g0 = int(cal.searchsorted(pd.Timestamp(RD.WINDOWS[wn][0])))
                R["m6"][(vn, wn)] = X.m6(runs, cv, bars, cal, spells, g0)
            if vn == "V0":
                pv = prev["book"][("V0", wn)]
                d = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                RD.log("repro-book", wn, d)
                if d > 1e-9:
                    raise SystemExit("V0 계좌 재현 실패 — 중단")
            RD.log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    X.dump(os.path.join(SCR, "xr", "acct_donchian.pkl"), R)
    RD.log("done")


def X_ist(ist):
    return ist


if __name__ == "__main__":
    main()
