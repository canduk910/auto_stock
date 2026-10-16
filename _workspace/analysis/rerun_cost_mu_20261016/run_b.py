"""BFB·VCP — 시장 유닛 on/off × 비용 NEW/OLD(+ERA 재현) (prereg §1~§4).

재사용: ``index_universe_20261015/run_bv.py`` 의 books·m_series·attach_mem(그 파일이 쓰는 y30_bfbvcp 엔진 그대로).
NEW/OLD 는 엔진 주판정 규약대로 0.15%p 가산(매수·매도 반반)을 유지하고 표(수수료·거래세)만 바꾼다.
실행: /opt/anaconda3/envs/upbit-trader/bin/python -I run_b.py <scratch> vcp|bfb
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
SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_bv.py")
sys.argv = [SRC, sys.argv[1], sys.argv[2]]
spec = importlib.util.spec_from_file_location("rb", SRC)
RB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RB)
YB, Y, OP, C, KIND = RB.YB, RB.Y, RB.OP, RB.C, RB.KIND

NEW = (0.00014, 0.002)
OLD = (0.00142, 0.002)


def const_cost(cal, fee, tax):
    c = YB.EraCostY(cal)
    c.fee = np.full(len(cal), fee + YB.SLIPPAGE_ALLOWANCE / 2)
    c.tax = np.full(len(cal), tax)
    return c


def main():
    cls, featf = YB._classes(KIND)
    st, meta = Y.build()
    cal = st.cal
    RB.attach_mem(st)
    M = RB.m_series(cal)
    costs = {"ERA": YB.EraCostY(cal), "NEW": const_cost(cal, *NEW), "OLD": const_cost(cal, *OLD)}
    p = OP.params_for(KIND, "cur", "X0")
    p.update(RB.LIVE_OVR[KIND])
    feats = {t: featf(b, p) for t, b in st.bars.items()}
    uA = Y.universe(st, meta["ratios"], KIND, mode="pct")
    _, meth, cap, k = {e[0]: e for e in OP.entries_for(KIND)}["I"]
    RB.log("ready")

    def sigs(off):
        sg = YB.build_signals(st.bars, feats, M["kospi"], p, uA, method=meth, cap=cap, k=k)
        out = []
        for s in sg:
            b = st.bars[s.ticker]
            s.mem = bool(b["mem"][s.ti - 1])
            s.kq = bool(b["kq"][s.ti - 1])
            if s.kq:
                v = M["kosdaq"][s.gd]
                s.m = 1.0 if not np.isfinite(v) else float(v)
            if off:
                s = copy.copy(s)
                s.m = 1.0
            out.append(s)
        return out

    R = {"kind": KIND, "costs": {"NEW": NEW, "OLD": OLD, "allowance": YB.SLIPPAGE_ALLOWANCE}}
    for mu in ("on", "off"):
        sg = sigs(mu == "off")
        R[mu] = {"n_sig": len(sg)}
        for wn, win in RB.W.items():
            g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
            g1 = int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
            insig = [s for s in sg if g0 <= s.gd <= g1]
            pop, _ = YB.population(sg, st.bars, feats, g0, g1, kind=KIND, p=p, cal=cal)
            yrs = YB.cal_years(cal, g0, g1)
            d = {"m0_share_sig": float(np.mean([s.m <= 0 for s in insig])) if insig else None,
                 "sig_per_day": len(insig) / max(1, g1 - g0 + 1)}
            cks = ("ERA", "NEW", "OLD") if mu == "on" else ("NEW", "OLD")
            for ck in cks:
                rr = YB.rows_of(pop, cal, costs[ck], g1)
                d[f"pop_{ck}"] = YB.stat_block(rr, yrs)
                d[f"book_{ck}"] = RB.books(sg, st, feats, p, cls, win, costs[ck], 0.0)
            R[mu][wn] = d
            RB.log(mu, wn, {ck: (d[f"pop_{ck}"]["n"], round(d[f"pop_{ck}"]["mean"], 5),
                                 round(d[f"book_{ck}"]["cagr"], 4)) for ck in cks})
            with open(os.path.join(HERE, f"result_{KIND}.json"), "w") as fh:
                json.dump(R, fh, ensure_ascii=False, indent=1, default=YB._js)
    RB.log("done")


if __name__ == "__main__":
    main()
