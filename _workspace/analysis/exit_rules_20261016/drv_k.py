"""kojiro — 모집단 덤프(pop) · 계좌 변형(acct). 설정 코드는 mu_datadriven run_k.py 그대로.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python drv_k.py <scratch> pop|acct
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

SCR, MODE = sys.argv[1], sys.argv[2]
SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_kojiro.py")
sys.argv = [SRC, SCR]
spec = importlib.util.spec_from_file_location("rk", SRC)
RK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RK)
Y, KJ, KO, KOR, MU, C = RK.Y, RK.KJ, RK.KO, RK.KOR, RK.MU, RK.C
NEW = (0.00014, 0.002)
OVR = {"ovr": None, "pos": 4, "post": None}


def main():
    Y.patch_fast_ewm()
    CM.wrap(Y, "summary30")
    p = RK.live_params()
    sec = RK.sectors()
    df, meta = Y.load_unified(drop_flags=True)
    etf_names = sorted(n for n in df.name.dropna().unique() if RK.is_etf_like(None, n))
    if etf_names:
        df = df[~df.name.isin(etf_names)]
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    st = Y.build(df, cal=cal)
    del df
    Y.Y30Pos.LIM = Y.limit_table(cal)
    cost = Y.Cost(np.full(len(cal), NEW[0]), np.full(len(cal), NEW[1]), "new")
    mem = pd.read_parquet(os.path.join(RK.SCR, "mem.parquet"))
    by = {t: g.bas_dd.values.astype("datetime64[ns]") for t, g in mem.groupby("ticker")}
    for t, b in st.bars.items():
        d = cal[b["di"]].to_numpy().astype("datetime64[ns]")
        b["mem"] = np.isin(d, by[t]) if t in by else np.zeros(len(d), bool)
        mk = np.asarray(b["mkt"])
        b["kq"] = (mk == 1) if mk.ndim else np.full(len(d), int(mk) == 1)
    ser = pd.read_csv(os.path.join(RK.SCR, "series.csv"), index_col=0, parse_dates=True)
    src = {nm: (pd.DatetimeIndex(ser[nm].dropna().index), ser[nm].dropna().to_numpy(float)) for nm in ("kospi", "kosdaq")}
    M = {nm: MU.m_for_days(cal, *src[nm]) for nm in ("kospi", "kosdaq")}
    band = float(p["atr_ratio_max"])
    feats = {}
    for t, b in st.bars.items():
        f = KJ.features(b, p)
        f["tech"] = f["tech"] & (f["ratio"] <= band)
        feats[t] = f
    uA = {t: Y.universe_era(b) for t, b in st.bars.items()}
    RK.log("ready")
    base, _ = KJ.build_signals(st.bars, feats, uA, M["kospi"], p, sec)
    for s in base:
        b = st.bars[s.ticker]
        s.extra["mem"] = bool(b["mem"][s.ti - 1])
        s.extra["kq"] = bool(b["kq"][s.ti - 1])
    prev = pickle.load(open(os.path.join(SCR, "md", "kojiro.pkl"), "rb"))
    V0 = (np.asarray(prev["m"]["V0"]["kospi"], float), np.asarray(prev["m"]["V0"]["kosdaq"], float))

    def setm(mm):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.extra = dict(s.extra)
            s2.m = CM.mval((mm[1] if s2.extra["kq"] else mm[0])[s2.gd])
            out.append(s2)
        return KO.select(out, "cur", None)

    sg = setm(V0)
    pe = KOR.exit_cfg(KOR.CURRENT).params(p)
    if MODE == "pop":
        recs = []
        for wn, win in RK.W.items():
            g0, g1 = Y.gd_range(cal, win)
            busy = {}
            for s in sorted(sg, key=lambda s: (s.gd, s.ticker)):
                if s.gd < g0 or s.gd > g1 or s.m <= 0 or busy.get(s.ticker, -1) >= s.gd:
                    continue
                s1 = KO.slip_sig(s, RK.SLIP)
                ps = Y.run_path(s1, st.bars[s.ticker], feats[s.ticker], pe, g1)
                busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
                recs.append(X.pop_record(ps, st.bars[s.ticker], s.extra["kq"], wn))
            RK.log("pop", wn, len(recs))
        X.dump(os.path.join(SCR, "xr", "pop_kojiro.pkl"), {"cal": np.asarray(cal), "recs": recs,
                                                           "cur": {k: pe[k] for k in ("hard_stop_pct", "stop_atr", "trail_atr", "breakeven_promote_atr")}})
        return
    # acct
    specs = json.load(open(os.path.join(HERE, "variants.json")))["kojiro"]
    ist = X.index_state(cal, os.path.join(RK.SCR, "series.csv"))
    X.patch_overlay(Y.Y30Pos)
    X.patch_exit_line(Y.Y30Pos, lambda ps: max(ps.stop_line(), ps.trail_line()))
    X.patch_init_params(Y.Y30Pos, "p", OVR)
    spells = X.crash_spells(cal, os.path.join(RK.SCR, "series.csv"))
    R = {"cal": np.asarray(cal), "book": {}, "curves": {}, "trades": {}, "m6": {}}
    for vn, sp in specs.items():
        OVR["ovr"] = sp.get("ovr") or None
        X.CFG["crash"] = None if sp.get("crash") is None else X.crash_flags(cal, ist, sp["crash"], sp.get("shift", 0))
        X.CFG["stall"] = sp.get("stall")
        for wn in sp["wins"]:
            C.BUDGET_C7 = 4_707_820
            bk = RK.books(sg, st.bars, feats, p, cal, RK.W[wn], cost, 0.0)
            runs = CM.take()
            R["book"][(vn, wn)] = {"cagr": bk["cagr"], "mdd": bk["mdd"]}
            cv = CM.curves(runs, cal, RK.W[wn])
            R["curves"][(vn, wn)] = [{"dates": c["dates"], "eq": c["eq"], "inv": c["inv"].astype(np.float32),
                                      "npos": c["npos"].astype(np.int16)} for c in cv]
            if "|" not in vn:
                R["trades"][(vn, wn)] = X.trade_rows(runs, st.bars, 2 * NEW[0] + NEW[1], cal)
                g0, _ = Y.gd_range(cal, RK.W[wn])
                R["m6"][(vn, wn)] = X.m6(runs, cv, st.bars, cal, spells, g0)
            if vn == "V0":
                pv = prev["book"][("V0", wn)]
                d = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                RK.log("repro-book", wn, d)
                if d > 1e-9:
                    raise SystemExit("V0 계좌 재현 실패 — 중단")
            RK.log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    X.dump(os.path.join(SCR, "xr", "acct_kojiro.pkl"), R)
    RK.log("done")


if __name__ == "__main__":
    main()
