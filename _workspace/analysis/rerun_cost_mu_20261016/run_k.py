"""kojiro — 시장 유닛 on/off × 비용 NEW/OLD(+ERA 재현) (prereg §1~§4).

재사용: ``index_universe_20261015/run_kojiro.py`` 의 books·stats·live_params·sectors(그 파일이 쓰는 kojiro_y30 엔진 그대로).
실행: /opt/anaconda3/envs/upbit-trader/bin/python -I run_k.py <scratch>
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_kojiro.py")
sys.argv = [SRC, sys.argv[1]]
spec = importlib.util.spec_from_file_location("rk", SRC)
RK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RK)
Y, KJ, KO, KOR, MU, C = RK.Y, RK.KJ, RK.KO, RK.KOR, RK.MU, RK.C

NEW = (0.00014, 0.002)
OLD = (0.00142, 0.002)
BUD = {"w030": 1_091_063, "w025": 909_219}


def const_cost(cal, fee, tax, name):
    return Y.Cost(np.full(len(cal), fee), np.full(len(cal), tax), name)


def main():
    Y.patch_fast_ewm()
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
    costs = {"ERA": Y.era_cost(cal), "NEW": const_cost(cal, *NEW, "new"), "OLD": const_cost(cal, *OLD, "old")}
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

    def sigs(off):
        sg, _ = KJ.build_signals(st.bars, feats, uA, M["kospi"], p, sec)
        out = []
        for s in sg:
            b = st.bars[s.ticker]
            i = s.ti - 1
            s.extra["mem"] = bool(b["mem"][i])
            s.extra["kq"] = bool(b["kq"][i])
            if s.extra["kq"]:
                v = M["kosdaq"][s.gd]
                s.m = 1.0 if not np.isfinite(v) else float(v)
            if off:
                s = copy.copy(s)
                s.extra = dict(s.extra)
                s.m = 1.0
            out.append(s)
        return KO.select(out, "cur", None)

    cfg = KOR.exit_cfg(KOR.CURRENT)
    R = {"costs": {"NEW": NEW, "OLD": OLD}}
    S = {"on": sigs(False), "off": sigs(True)}
    for mu, sg in S.items():
        R[mu] = {"n_sig": len(sg)}
        memo = Y.PathMemo(st.bars, feats, p)
        for wn, win in RK.W.items():
            g0, g1 = Y.gd_range(cal, win)
            insig = [s for s in sg if g0 <= s.gd <= g1]
            pop = Y.population(sg, memo, cfg, g0, g1, RK.SLIP)
            d = {"m0_share_sig": float(np.mean([s.m <= 0 for s in insig])) if insig else None,
                 "sig_per_day": len(insig) / max(1, g1 - g0 + 1)}
            cks = ("ERA", "NEW", "OLD") if mu == "on" else ("NEW", "OLD")
            for ck in cks:
                d[f"pop_{ck}"] = RK.stats(pop, cal, costs[ck])
                C.BUDGET_C7 = 4_707_820
                d[f"book_{ck}"] = RK.books(sg, st.bars, feats, p, cal, win, costs[ck], 0.0)
            if mu == "on":
                for bn, bv in BUD.items():
                    C.BUDGET_C7 = bv
                    d[f"book_NEW_{bn}"] = RK.books(sg, st.bars, feats, p, cal, win, costs["NEW"], 0.0)
                C.BUDGET_C7 = 4_707_820
            R[mu][wn] = d
            RK.log(mu, wn, {ck: (d[f"pop_{ck}"]["n"], round(d[f"pop_{ck}"]["mean"], 5)) for ck in cks})
            with open(os.path.join(HERE, "result_kojiro.json"), "w") as fh:
                json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    RK.log("done")


if __name__ == "__main__":
    main()
