"""donchian — on / off / 위약 8판 × NEW · 씨앗별 자산곡선 (prereg §1·§4).

재사용: 앞 재백테스트 run_d.py 의 signals·book 을 그대로 옮기고(``index_universe_20261015/run_donchian.py`` 의 build·run_book),
요약 직전에 runs 만 받아 둔다.
실행: PYTHONPATH=<shim> /opt/anaconda3/envs/upbit-trader/bin/python run_d.py <scratch>
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as CM  # noqa: E402

SRC = os.path.join(HERE, "..", "index_universe_20261015", "run_donchian.py")
sys.argv = [SRC, sys.argv[1]]
spec = importlib.util.spec_from_file_location("rd", SRC)
RD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RD)
Y, DK, DA, J, BK, C = RD.Y, RD.DK, RD.DA, RD.J, RD.BK, RD.C

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

    def book(sg, w, op):
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
        op = make_op("off" if vn == "off" else "enforce")
        wins = ("T", "V", "H") if vn in ("on", "off") else ("T", "V")
        for w in wins:
            bk = book(sg, w, op)
            R["book"][(vn, w)] = bk
            R["curves"][(vn, w)] = CM.curves(CM.take(), cal, RD.WINDOWS[w])
            RD.log(vn, w, round(bk["cagr"], 5), round(bk["mdd"], 5))
    CM.dump(os.path.join(sys.argv[1], "mr", "donchian.pkl"), R)
    RD.log("done")


if __name__ == "__main__":
    main()
