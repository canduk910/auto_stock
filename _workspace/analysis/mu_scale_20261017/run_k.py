"""kojiro — 후보 m 계열 × on/위약 (prereg §1). 설정 코드는 앞 재측정 run_k.py 그대로.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python run_k.py <scratch>
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

SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_kojiro.py")
LP.SCR = sys.argv[1]
sys.argv = [SRC, sys.argv[1]]
spec = importlib.util.spec_from_file_location("rk", SRC)
RK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RK)
Y, KJ, KO, KOR, MU, C = RK.Y, RK.KJ, RK.KO, RK.KOR, RK.MU, RK.C

NEW = (0.00014, 0.002)


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

    def setm(base, mm):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.extra = dict(s.extra)
            s2.m = 1.0 if mm is None else CM.mval((mm[1] if s2.extra["kq"] else mm[0])[s2.gd])
            out.append(s2)
        return KO.select(out, "cur", None)

    def book(sg, wn, vn):
        C.BUDGET_C7 = 4_707_820
        bk = RK.books(sg, st.bars, feats, p, cal, RK.W[wn], cost, 0.0)
        return {"cagr": bk["cagr"], "mdd": bk["mdd"]}

    LP.run("kojiro", cal, src, MU, base, setm, book, RK.W, os.path.join(LP.SCR, "mr", "kojiro.pkl"), RK.log)


if __name__ == "__main__":
    main()
