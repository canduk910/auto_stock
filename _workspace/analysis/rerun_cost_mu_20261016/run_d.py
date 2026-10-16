"""donchian — 시장 유닛 on/off × 비용 NEW/OLD(+ERA 재현) (prereg §1~§4).

재사용: ``index_universe_20261015/run_donchian.py`` 의 build·run_book 과 main 안 함수(signals·rows·st_·book)를 그대로 옮겼다
(그 파일이 쓰는 donchian_y30 엔진 · 유니버스 U0 · 원천 mkt = 종목 소속 시장 종합지수).
실행: /opt/anaconda3/envs/upbit-trader/bin/python -I run_d.py <scratch>
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_donchian.py")
sys.argv = [SRC, sys.argv[1]]
spec = importlib.util.spec_from_file_location("rd", SRC)
RD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RD)
Y, DK, DA, J, BK, C = RD.Y, RD.DK, RD.DA, RD.J, RD.BK, RD.C

NEW = (0.00014, 0.002)
OLD = (0.00142, 0.002)


def const_costs(cal, fee, tax, tag):
    c = Y.Costs(cal, 0.0)
    c.buy = np.full(len(cal), fee)
    c.sell = np.full(len(cal), fee + tax)
    c.tag = tag
    return c


def main():
    st, M, info = RD.build()
    cal = st.cal
    Y._CAL["cal"] = cal
    bars = st.bars
    costs = {"ERA": Y.Costs(cal), "NEW": const_costs(cal, *NEW, "new"), "OLD": const_costs(cal, *OLD, "old")}
    kk = Y.kk_of(Y.EXIT0)
    feats = {}
    for t, b in bars.items():
        bb = dict(b)
        bb["mem"] = b["common"]
        feats[t] = Y.features_y30(bb, entry_n=20, vol_mult=1.5, clv=None, tv_mode="pct")
    RD.log("features")

    def signals():
        fv = {}
        for t, f in feats.items():
            g = dict(f)
            g["cond"] = f["cond"] & bars[t]["mem"]
            fv[t] = g
        sg = DK.build_signals(bars, fv, M["kospi"])
        for s in sg:
            if bars[s.ticker]["kq"][s.ti - 1]:
                v = M["kosdaq"][s.gd]
                s.m = 1.0 if not np.isfinite(v) else float(v)
        sg = [s for s in sg if not DA.r_half_blocked(s.E, s.N, kk)]
        for s in sg:
            b = bars[s.ticker]
            s.mem = bool(b["mem"][s.ti - 1])
            s.kq = bool(b["kq"][s.ti - 1])
            s.mcap_rank = None
        return sg

    def gwin(w):
        a, b = RD.WINDOWS[w]
        return int(cal.searchsorted(pd.Timestamp(a))), int(cal.searchsorted(pd.Timestamp(b), side="right")) - 1

    def rows(pop, end_gd, cst):
        out = []
        for p in pop:
            cr = cst.rt(p.s.gd, p.exit_gd if p.exit_gd is not None else end_gd)
            net = p.exit_px / p.E - 1 - cr
            out.append({"t": p.s.ticker, "gd": p.s.gd, "m": p.s.m, "net": net, "kq": p.s.kq, "why": p.exit_reason})
        return out

    def st_(rs):
        if not rs:
            return {"n": 0}
        r = J.p1([x["net"] for x in rs], [x["t"] for x in rs], [cal[x["gd"]].date() for x in rs])
        return {"n": r["n"], "mean": r["mean"], "lo90": r["lo90"], "win": float(np.mean([x["net"] > 0 for x in rs])),
                "kq_share": float(np.mean([x["kq"] for x in rs])), "why": dict(Counter(x["why"] for x in rs))}

    cls = RD.load_strategy_class(RD.BRANCH, "DonchianSwingStrategy", "du_branch")

    def make_op(mode):
        return RD.OpSizer(cls, "donchian_swing", {"market_unit_mode": mode, "risk_pct": 0.012, "position_ratio": 0.15,
                                                  "max_positions": 6, "kk_r_floor_pct": 8.0, "kk_r_atr_mult": 1.5})

    def book(sg, w, cst, op):
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
        return {"cagr": sm["cagr_median"], "mdd": sm["mdd_median"], "fills_y": sm["fills_per_year_median"],
                "per_seed": [x["cagr"] for x in sm["per_seed"]], "per_seed_mdd": [x["mdd"] for x in sm["per_seed"]]}

    base = signals()
    R = {"costs": {"NEW": NEW, "OLD": OLD}}
    for mu in ("on", "off"):
        sg = base
        if mu == "off":   # Y.mu_apply("off") 와 같은 뜻 — Sig 에 붙인 mem·kq 때문에 재생성 대신 복사
            sg = []
            for s in base:
                s2 = copy.copy(s)
                s2.m = 1.0
                sg.append(s2)
        op = make_op("enforce" if mu == "on" else "off")
        R[mu] = {"n_sig": len(sg)}
        for w in ("T", "V", "H"):
            g = gwin(w)
            insig = [s for s in sg if g[0] <= s.gd <= g[1]]
            pop = Y.population(sg, bars, feats, g[0], g[1], kk=kk)
            d = {"m0_share_sig": float(np.mean([s.m <= 0 for s in insig])) if insig else None}
            cks = ("ERA", "NEW", "OLD") if mu == "on" else ("NEW", "OLD")
            for ck in cks:
                d[f"pop_{ck}"] = st_(rows(pop, g[1], costs[ck]))
                d[f"book_{ck}"] = book(sg, w, costs[ck], op)
            R[mu][w] = d
            RD.log(mu, w, {ck: (d[f"pop_{ck}"].get("n"), round(d[f"pop_{ck}"].get("mean", np.nan), 5),
                                round(d[f"book_{ck}"]["cagr"], 4)) for ck in cks})
            with open(os.path.join(HERE, "result_donchian.json"), "w") as fh:
                json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    RD.log("done")


if __name__ == "__main__":
    main()
