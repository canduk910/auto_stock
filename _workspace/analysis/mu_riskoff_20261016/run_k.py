"""kojiro — on / off / 위약 8판 × NEW · 씨앗별 자산곡선 (prereg §1·§4).

재사용: 앞 재백테스트 run_k.py 와 같이 ``index_universe_20261015/run_kojiro.py`` 를 모듈로 불러 books 를 그대로 쓴다.
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
import common as CM  # noqa: E402

SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_kojiro.py")
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
    M = {nm: MU.m_for_days(cal, pd.DatetimeIndex(ser[nm].dropna().index), ser[nm].dropna().to_numpy(float))
         for nm in ("kospi", "kosdaq")}
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

    def variant(mk, mq):
        out = []
        for s in base:
            s2 = copy.copy(s)
            s2.extra = dict(s.extra)
            if mk is None:
                s2.m = 1.0
            else:
                s2.m = CM.mval((mq if s2.extra["kq"] else mk)[s2.gd])
            out.append(s2)
        return KO.select(out, "cur", None)

    V = {"on": (M["kospi"], M["kosdaq"]), "off": (None, None)}
    for k in CM.SHIFTS:
        V[f"plc{k}"] = (CM.shifted(M["kospi"], k), CM.shifted(M["kosdaq"], k))
    R = {"cal": np.asarray(cal), "m": {"kospi": M["kospi"], "kosdaq": M["kosdaq"]}, "book": {}, "curves": {}}
    for vn, (mk, mq) in V.items():
        sg = variant(mk, mq)
        wins = ("T", "V", "H") if vn in ("on", "off") else ("T", "V")
        for wn in wins:
            win = RK.W[wn]
            C.BUDGET_C7 = 4_707_820
            bk = RK.books(sg, st.bars, feats, p, cal, win, cost, 0.0)
            R["book"][(vn, wn)] = {"cagr": bk["cagr"], "mdd": bk["mdd"]}
            R["curves"][(vn, wn)] = CM.curves(CM.take(), cal, win)
            RK.log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    CM.dump(os.path.join(sys.argv[1], "mr", "kojiro.pkl"), R)
    RK.log("done")


if __name__ == "__main__":
    main()
