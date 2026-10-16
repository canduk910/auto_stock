"""공용 후보 루프 (prereg §1·§3). 후보마다 on(T,V,H) + 위약 8판(T,V). off 는 한 번(T,V,H)."""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mu_riskoff_20261016"))
import common as CM  # noqa: E402  (앞 재측정 공용 — wrap·take·curves·shifted·mval)
import mvar  # noqa: E402

SCR = None


def slim(cs):
    return [{"dates": c["dates"], "eq": c["eq"].astype(np.float64), "inv": c["inv"].astype(np.float32),
             "npos": c["npos"].astype(np.int16)} for c in cs]


def run(tag, cal, src, MU, base, setm, book, wins, prev_pkl, log):
    names = [x for x in os.environ.get("VARIANTS", ",".join(mvar.BASIC)).split(",") if x]
    fx = os.environ.get("V6PICK", "")
    f_star, x_star = (fx.split("+") + [None])[:2] if fx else (None, None)
    MS = mvar.all_days(cal, src, MU, names, f_star, x_star)
    prev = pickle.load(open(prev_pkl, "rb"))
    if "V0" in names:
        for mk in ("kospi", "kosdaq"):
            a, b = MS["V0"][mk], np.asarray(prev["m"][mk], float)
            same = np.array_equal(np.isnan(a), np.isnan(b)) and np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)])
            log("repro-m", mk, same)
            if not same:
                raise SystemExit("V0 m 계열 불일치 — 중단")
    R = {"cal": np.asarray(cal), "m": MS, "book": {}, "curves": {}}
    plan = []
    if "V0" in names:
        plan.append(("off", None, ("T", "V", "H")))
    for nm in names:
        plan.append((nm, (MS[nm]["kospi"], MS[nm]["kosdaq"]), ("T", "V", "H")))
        for sh in CM.SHIFTS:
            plan.append((f"{nm}|plc{sh}", (CM.shifted(MS[nm]["kospi"], sh), CM.shifted(MS[nm]["kosdaq"], sh)), ("T", "V")))
    for vn, mm, ws in plan:
        sg = setm(base, mm)
        for wn in ws:
            bk = book(sg, wn, vn)
            R["book"][(vn, wn)] = bk
            R["curves"][(vn, wn)] = slim(CM.curves(CM.take(), cal, wins[wn]))
            if vn in ("off", "V0"):
                pv = prev["book"][("on" if vn == "V0" else "off", wn)]
                d = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                log("repro-book", vn, wn, d)
                if d > 1e-9:
                    raise SystemExit("V0/off 계좌 재현 실패 — 중단")
            if "|" not in vn:
                log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    out = os.path.join(SCR, "mv", f"{tag}{'_v6' if fx else ''}.pkl")
    with open(out, "wb") as fh:
        pickle.dump(R, fh, protocol=4)
    log("done", out)
