"""계좌 지표 · 판정 (prereg §6) + 급락장 손실 분해 M6 요약 (§2).

실행: /opt/anaconda3/envs/upbit-trader/bin/python analyze.py <scratch>  → summary.json
지표 함수 = mu_riskoff analyze.py(앞 재측정)의 metrics·summarize·combine 그대로.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = sys.argv[1]
_argv = sys.argv
sys.argv = [_argv[0], SCR]
spec = importlib.util.spec_from_file_location("A0", os.path.join(HERE, "..", "mu_riskoff_20261016", "analyze.py"))
A0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A0)
sys.argv = _argv

STOCK = ("kojiro", "donchian", "bfb", "vcp")
SHIFTS = (126, 252, 378, 504, 756, 1008, 1260, 1512)
KEYS = ("R1_mdd", "R2_worst20", "R3_es5", "R4_crash", "worst_month", "cagr", "calmar", "share_below20", "uw_longest",
        "uw_deep_median", "inv_mean")
FAST = {"2011": ("2011-07-25", "2011-09-30"), "2020": ("2020-01-20", "2020-03-31")}


def load(k):
    with open(os.path.join(SCR, "xr", f"acct_{k}.pkl"), "rb") as fh:
        R = pickle.load(fh)
    for key in list(R["curves"]):
        for c in R["curves"][key]:
            c.setdefault("inv", np.zeros(len(c["eq"])))
            c.setdefault("npos", np.zeros(len(c["eq"])))
    return R


def fill_missing(R, names):
    for nm in names:
        for wn in ("T", "V", "H"):
            if (nm, wn) not in R["curves"] and ("V0", wn) in R["curves"]:
                R["curves"][(nm, wn)] = R["curves"][("V0", wn)]
                if ("V0", wn) in R.get("trades", {}):
                    R["trades"][(nm, wn)] = R["trades"][("V0", wn)]


def trade_stats(df):
    if df is None or len(df) == 0:
        return {}
    d = df[~df.why.isin(["OPEN", "END", "end"])]
    w = d.whip.dropna()
    return {"n_per_seed": float(len(d) / max(1, d.seed.nunique())), "exp": float(d.net.mean()),
            "win": float((d.net > 0).mean()), "whip": float(w.mean()) if len(w) else None,
            "n_loss_exits": int(len(w)), "why": d.why.value_counts(normalize=True).round(4).to_dict()}


def evaluate(C, names, trades=None):
    res = {}
    for wn in ("T", "V", "H"):
        W, mets = {}, {}
        for nm in names:
            if (nm, wn) not in C:
                continue
            s, ms = A0.summarize(C[(nm, wn)])
            mets[nm] = ms
            row = {k: s[k] for k in KEYS}
            if trades is not None:
                row["trades"] = trade_stats(trades.get((nm, wn)))
            if wn in ("T", "V") and (f"{nm}|plc126", wn) in C:
                pl = {sh: A0.summarize(C[(f"{nm}|plc{sh}", wn)])[0] for sh in SHIFTS}
                row["timing"] = {k: int(sum(1 for sh in SHIFTS if s[k] > pl[sh][k])) for k in ("R1_mdd", "R4_crash")}
                row["timing_ok"] = bool(all(v >= 6 for v in row["timing"].values()))
            W[nm] = row
        for nm in mets:
            if nm == "V0":
                continue
            for k in ("R1_mdd", "R2_worst20", "R4_crash"):
                W[nm][f"seeds_better_{k}"] = int(sum(a[k] > b[k] for a, b in zip(mets[nm], mets["V0"])))
        res[wn] = W
    return res


def exp_of(W, nm):
    t = W[nm].get("trades") or {}
    return t.get("exp")


def guard(W, nm):
    a, b = W[nm], W["V0"]
    ok = a["R1_mdd"] >= b["R1_mdd"] - 0.010 and a["R4_crash"] >= b["R4_crash"] - 0.020 and a["cagr"] >= b["cagr"] - 0.015
    ea, eb = exp_of(W, nm), exp_of(W, "V0")
    if ea is not None and eb is not None:
        ok = ok and ea >= eb - 0.003
    return bool(ok)


def improve(W, nm):
    a, b = W[nm], W["V0"]
    r4 = a["R4_crash"] >= b["R4_crash"] + 0.030 and a.get("seeds_better_R4_crash", 0) >= 10
    r1 = a["R1_mdd"] >= b["R1_mdd"] + 0.030 and a.get("seeds_better_R1_mdd", 0) >= 10
    r2 = a["R2_worst20"] >= b["R2_worst20"] + 0.020 and a.get("seeds_better_R2_worst20", 0) >= 10
    return bool(r4 or r1 or r2), {"R4": bool(r4), "R1": bool(r1), "R2": bool(r2)}


def judge(ev, nm, has_crash):
    T, V, H = ev["T"], ev["V"], ev["H"]
    g = guard(T, nm) and guard(V, nm)
    iv, ivd = improve(V, nm)
    it, _ = improve(T, nm)
    mir_ok = True
    if "MIRROR" in V and nm == "DSTAR":
        mi, _ = improve(V, "MIRROR")
        mir_ok = not (mi and guard(V, "MIRROR") and guard(T, "MIRROR"))
    tim = True
    if has_crash:
        tim = bool(T[nm].get("timing_ok") and V[nm].get("timing_ok"))
    if not g:
        lab = "기각"
    elif not iv:
        lab = "개선 없음"
    elif mir_ok and tim:
        lab = "채택 후보"
    else:
        lab = "개선 있으나 대조 미통과"
    hrev = bool(H[nm]["R1_mdd"] < H["V0"]["R1_mdd"] - 0.010 and H[nm]["R4_crash"] < H["V0"]["R4_crash"] - 0.020)
    conf = ("높음" if (it and not hrev) else "중간") if lab == "채택 후보" else "낮음"
    return {"label": lab + (" (H 반전)" if hrev else ""), "guard_T": guard(T, nm), "guard_V": guard(V, nm), "I_V": ivd,
            "I_T": it, "mirror_ok": mir_ok, "timing_ok": tim, "confidence": conf}


def m6_summary(R, wn, nm="V0"):
    rows = R["m6"].get((nm, wn))
    if rows is None:
        return None
    cal = pd.DatetimeIndex(R["cal"])
    keys = ("pre_line", "pre_gap", "pre_other", "pre_open", "pre_hold", "new_line", "new_gap", "new_other", "new_open")
    out = {}
    for tag, (a, b) in [("all", (None, None))] + list(FAST.items()):
        per = []
        for seed_rows in rows:
            acc = {k: 0.0 for k in keys}
            npre = nnew = 0
            for r in seed_rows:
                d0 = cal[r["a"]]
                if a is not None and not (pd.Timestamp(a) <= d0 <= pd.Timestamp(b)):
                    continue
                for k in keys:
                    acc[k] += r[k] / r["eq0"]
                npre += r["n_pre"]
                nnew += r["n_new"]
            acc["n_pre"], acc["n_new"] = npre, nnew
            per.append(acc)
        if not per:
            continue
        med = {k: float(np.median([p[k] for p in per])) for k in per[0]}
        pre_act = med["pre_line"] + med["pre_gap"] + med["pre_other"] + med["pre_open"]
        med["pre_actual"] = pre_act
        med["blocked_share"] = (1 - pre_act / med["pre_hold"]) if med["pre_hold"] < 0 else None
        out[tag] = med
    return out


def main():
    V = json.load(open(os.path.join(HERE, "variants.json")))
    Rs = {k: load(k) for k in STOCK}
    names = ["V0", "DSTAR", "MIRROR"]
    for k in STOCK:
        fill_missing(Rs[k], names)
    out = {"strategies": {}, "book4": {}, "m6": {}}
    for k in STOCK:
        has_crash = any(s.get("crash") is not None for s in V[k].values())
        nm_list = ["V0"] + [n for n in V[k] if n != "V0" and "|" not in n]
        ev = evaluate(Rs[k]["curves"], nm_list, Rs[k]["trades"])
        jd = {n: judge(ev, n, has_crash) for n in nm_list if n != "V0"}
        out["strategies"][k] = {"eval": ev, "judge": jd, "derived_change": "DSTAR" in V[k]}
        out["m6"][k] = {wn: m6_summary(Rs[k], wn) for wn in ("T", "V", "H")}
        if "DSTAR" in V[k]:
            out["m6"][k].update({f"DSTAR_{wn}": m6_summary(Rs[k], wn, "DSTAR") for wn in ("T", "V", "H")})
    RC = {"curves": {}}
    for nm in names:
        for wn in ("T", "V", "H"):
            RC["curves"][(nm, wn)] = A0.combine(Rs, nm, wn)
    tr = {}
    for nm in names:
        for wn in ("T", "V", "H"):
            tr[(nm, wn)] = pd.concat([Rs[k]["trades"][(nm, wn)].assign(strat=k) for k in STOCK], ignore_index=True)
    ev = evaluate(RC["curves"], names, tr)
    any_crash = any(s.get("crash") is not None for k in STOCK for s in V[k].values())
    out["book4"] = {"eval": ev, "judge": {n: judge(ev, n, any_crash) for n in ("DSTAR", "MIRROR")}}
    # 묶음 M6 (전략별 비중 가중 합)
    wts = {k: A0.WEIGHTS[k] / sum(A0.WEIGHTS.values()) for k in STOCK}
    bm = {}
    for wn in ("T", "V", "H"):
        bm[wn] = {}
        for tag in ("all", "2011", "2020"):
            parts = [out["m6"][k][wn].get(tag) if out["m6"][k][wn] else None for k in STOCK]
            if any(p is None for p in parts):
                continue
            agg = {key: float(sum(wts[k] * p[key] for k, p in zip(STOCK, parts))) for key in parts[0] if key not in ("n_pre", "n_new", "blocked_share")}
            agg["blocked_share"] = (1 - agg["pre_actual"] / agg["pre_hold"]) if agg["pre_hold"] < 0 else None
            bm[wn][tag] = agg
    out["m6"]["book4"] = bm
    if os.path.exists(os.path.join(SCR, "xr", "acct_etf.pkl")):
        Re = load("etf")
        fill_missing(Re, ["V0", "DSTAR", "MIRROR"])
        nm_e = ["V0"] + [n for n in V["etf"] if n != "V0" and "|" not in n]
        eve = evaluate(Re["curves"], nm_e, Re["trades"])
        out["strategies"]["etf"] = {"eval": eve, "judge": {n: judge(eve, n, False) for n in nm_e if n != "V0"},
                                    "derived_change": "DSTAR" in V["etf"]}
    json.dump(out, open(os.path.join(HERE, "summary.json"), "w"), ensure_ascii=False, indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
    for k, v in out["strategies"].items():
        print(k, {n: j["label"] for n, j in v["judge"].items()})
    print("book4", {n: j["label"] for n, j in out["book4"]["judge"].items()})


if __name__ == "__main__":
    main()
