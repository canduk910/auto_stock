"""후보별 위험·깜빡임·급락·위약 지표 → 판정 (prereg §3~§5).

실행: /opt/anaconda3/envs/upbit-trader/bin/python analyze.py <scratch> [select|final]
  select = T 결과만으로 V6 의 F*·X* 를 고른다(§5) · final = V6 포함 전체 판정 → summary.json
지표 함수는 앞 재측정 analyze.py 를 그대로 불러 쓴다.
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
SCR, MODE = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "final")
_argv = sys.argv
sys.argv = [_argv[0], SCR]
spec = importlib.util.spec_from_file_location("A0", os.path.join(HERE, "..", "mu_riskoff_20261016", "analyze.py"))
A0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A0)
sys.argv = _argv

STR = ("kojiro", "donchian", "bfb", "vcp")
SHIFTS = A0.SHIFTS
BASIC = ("V0", "V1a", "V1b", "V2a", "V2b", "V3", "V4", "V5a", "V5b")
FLICK, CRASH = ("V1a", "V1b", "V2a", "V2b"), ("V3", "V4", "V5a", "V5b")
FAST = ("2011", "2020")
RK4 = A0.RKEYS


def load():
    Rs = {}
    for k in STR:
        with open(os.path.join(SCR, "mv", f"{k}.pkl"), "rb") as fh:
            Rs[k] = pickle.load(fh)
        p6 = os.path.join(SCR, "mv", f"{k}_v6.pkl")
        if os.path.exists(p6):
            with open(p6, "rb") as fh:
                R6 = pickle.load(fh)
            Rs[k]["m"]["V6"] = R6["m"]["V6"]
            Rs[k]["curves"].update(R6["curves"])
            Rs[k]["book"].update(R6["book"])
    return Rs


def book4(Rs):
    RC = {"cal": Rs["kojiro"]["cal"], "m": Rs["kojiro"]["m"], "curves": {}}
    for key in Rs["kojiro"]["curves"]:
        if all(key in Rs[k]["curves"] for k in A0.WEIGHTS):
            RC["curves"][key] = A0.combine(Rs, *key)
    return RC


def union_spells(cal, mk, mq, wd):
    om = (np.array([A0.mval(v) for v in mk]) <= 0) | (np.array([A0.mval(v) for v in mq]) <= 0)
    d0, d1 = pd.Timestamp(wd[0]), pd.Timestamp(wd[-1])
    sp, i = [], 0
    while i < len(cal):
        if om[i]:
            j = i
            while j < len(cal) and om[j]:
                j += 1
            if d0 <= cal[i] <= d1:
                sp.append((i, j))
            i = j
        else:
            i += 1
    return sp


def spell_delta(cal, sp, c_on, c_off, wd):
    """씨앗별 [(Δ per spell)]."""
    dpos = {d: k for k, d in enumerate(pd.DatetimeIndex(wd))}
    d1 = pd.Timestamp(wd[-1])
    out = []
    for sd in range(len(c_on)):
        xo, xf = A0.path(c_on[sd]["eq"]), A0.path(c_off[sd]["eq"])
        ds = []
        for (i, j) in sp:
            a = dpos.get(cal[i])
            e = dpos.get(min(cal[min(j + 20, len(cal) - 1)], d1))
            if a is None or e is None:
                continue
            ds.append((xo[e + 1] / xo[a] - 1.0) - (xf[e + 1] / xf[a] - 1.0))
        out.append(ds)
    return out


def flicker_market(cal, mm, wd):
    """시장 쪽 깜빡임(씨앗 무관)."""
    sp = union_spells(cal, mm["kospi"], mm["kosdaq"], wd)
    lens = [j - i for i, j in sp]
    ci = (cal >= pd.Timestamp(wd[0])) & (cal <= pd.Timestamp(wd[-1]))
    yrs = max((pd.Timestamp(wd[-1]) - pd.Timestamp(wd[0])).days, 1) / 365.25
    out = {"n_spells": len(sp), "n_short": int(sum(1 for x in lens if x <= 3)),
           "out_share": float(np.mean([any(A0.mval(mm[m][i]) <= 0 for m in ("kospi", "kosdaq")) for i in np.nonzero(ci)[0]]))}
    for mk in ("kospi", "kosdaq"):
        v = np.array([A0.mval(x) for x in mm[mk][ci]])
        ch = np.nonzero(v[1:] != v[:-1])[0] + 1
        rev = 0
        for t in ch:
            prev = v[t - 1]
            if any(v[t + h] == prev for h in range(1, 4) if t + h < len(v)):
                rev += 1
        out[f"{mk}_changes_per_yr"] = float(len(ch) / yrs)
        out[f"{mk}_revert3"] = int(rev)
    return out


def evaluate_target(R, kind, names):
    """R = {'cal', 'm': {name: {kospi,kosdaq}}, 'curves'} — book4 또는 단일 전략."""
    cal = pd.DatetimeIndex(R["cal"])
    C = R["curves"]
    res = {}
    for wn in ("T", "V", "H"):
        wd = C[("V0", wn)][0]["dates"]
        off = C[("off", wn)]
        sp0 = [(i, j) for (i, j) in union_spells(cal, R["m"]["V0"]["kospi"], R["m"]["V0"]["kosdaq"], wd) if j - i <= 3]
        W = {"off": A0.summarize(off)[0]}
        mets = {}
        for nm in names:
            if (nm, wn) not in C:
                continue
            s, ms = A0.summarize(C[(nm, wn)])
            mets[nm] = ms
            row = {k: s[k] for k in RK4 + ("worst_month", "cagr", "calmar", "inv_mean", "days_in_mkt", "ret_per_exposure")}
            dk = spell_delta(cal, sp0, C[(nm, wn)], off, wd)
            k3 = [sum(max(-x, 0.0) for x in ds) for ds in dk]
            row["K3"] = A0.med(k3)
            row["_k3_seeds"] = k3
            Rv = {"cal": R["cal"], "m": R["m"][nm]}
            cst = A0.spells_cost(Rv, kind, C[(nm, wn)], off, wd)
            row["B"], row["K"], row["BmK"], row["n_spells_own"] = cst["B_med"], cst["K_med"], cst["B_minus_K_med"], cst["n_spells"]
            ep = A0.episodes(Rv, kind, C[(nm, wn)], wd)
            row["episodes"] = {e: {"acct": v["acct_med"], "kospi": v["kospi"], "m0_kospi": v["m0_kospi"], "m0_kosdaq": v["m0_kosdaq"]}
                               for e, v in ep.items()}
            row["flicker_mkt"] = flicker_market(cal, R["m"][nm], wd)
            if wn in ("T", "V") and (f"{nm}|plc126", wn) in C:
                pl = {sh: A0.summarize(C[(f"{nm}|plc{sh}", wn)])[0] for sh in SHIFTS}
                row["timing"] = {k: int(sum(1 for sh in SHIFTS if s[k] > pl[sh][k])) for k in ("R1_mdd", "R4_crash")}
                row["timing_ok"] = bool(all(v >= 6 for v in row["timing"].values()))
                row["placebo_med"] = {k: float(np.median([pl[sh][k] for sh in SHIFTS])) for k in ("R1_mdd", "R4_crash", "cagr", "inv_mean")}
            W[nm] = row
        if "V0" in mets:
            for nm in mets:
                if nm == "V0":
                    continue
                W[nm]["seeds_better_R1"] = int(sum(a["R1_mdd"] > b["R1_mdd"] for a, b in zip(mets[nm], mets["V0"])))
                W[nm]["seeds_better_R4"] = int(sum(a["R4_crash"] > b["R4_crash"] for a, b in zip(mets[nm], mets["V0"])))
                W[nm]["seeds_better_K3"] = int(sum(a < b for a, b in zip(W[nm]["_k3_seeds"], W["V0"]["_k3_seeds"])))
        for nm in mets:
            W[nm].pop("_k3_seeds", None)
        res[wn] = W
    return res


def guard(W, nm, r4=True):
    a, b = W[nm], W["V0"]
    ok = a["R1_mdd"] >= b["R1_mdd"] - 0.010 and a["cagr"] >= b["cagr"] - 0.015
    return bool(ok and (a["R4_crash"] >= b["R4_crash"] - 0.020 if r4 else True))


def improve(W, nm):
    a, b = W[nm], W["V0"]
    fl = bool(a["K3"] <= 0.7 * b["K3"] and a.get("seeds_better_K3", 0) >= 10)
    cr = bool(a["R4_crash"] >= b["R4_crash"] + 0.030 and a.get("seeds_better_R4", 0) >= 10)
    return fl, cr


def judge(ev, nm):
    T, V, H = ev["T"], ev["V"], ev["H"]
    g = guard(T, nm) and guard(V, nm)
    fl, cr = improve(V, nm)
    flT, crT = improve(T, nm)
    lab = "기각(위험·수익 악화)" if not g else ("채택 후보" if (fl or cr) else "개선 없음")
    hrev = bool(H[nm]["R1_mdd"] < H["V0"]["R1_mdd"] - 0.010 and H[nm]["R4_crash"] < H["V0"]["R4_crash"] - 0.020)
    tt = (T[nm].get("timing_ok"), V[nm].get("timing_ok"))
    tim = "T·V 둘 다" if all(tt) else ("없음" if not any(tt) else "한쪽")
    same_T = (fl and flT) or (cr and crT)
    if nm == "V6":
        same_T = False                                   # T 는 선정에 쓴 창 — (I) 근거 아님(§5)
    conf = ("높음" if same_T and not hrev else "중간") if lab == "채택 후보" else "낮음"
    return {"label": lab + (" (H 반전)" if hrev else ""), "guard_T": guard(T, nm), "guard_V": guard(V, nm),
            "I_flicker_V": fl, "I_crash_V": cr, "I_flicker_T": flT, "I_crash_T": crT, "placebo_timing": tim, "confidence": conf}


def select_v6(ev):
    T = ev["T"]
    fc = [nm for nm in FLICK if guard(T, nm)]
    xc = [nm for nm in CRASH if guard(T, nm, r4=False)]
    f = min(fc, key=lambda n: (T[n]["K3"], -T[n]["cagr"])) if fc else None
    x = max(xc, key=lambda n: (T[n]["R4_crash"], T[n]["cagr"])) if xc else None
    return {"F": f, "X": x, "F_pass": fc, "X_pass": xc,
            "T_K3": {n: T[n]["K3"] for n in FLICK}, "T_R4": {n: T[n]["R4_crash"] for n in CRASH}}


def main():
    Rs = load()
    names = [n for n in BASIC + ("V6",) if n in Rs["kojiro"]["m"]]
    RC = book4(Rs)
    ev = evaluate_target(RC, "book4", names)
    if MODE == "select":
        sel = select_v6(ev)
        json.dump(sel, open(os.path.join(HERE, "v6_selection.json"), "w"), ensure_ascii=False, indent=1)
        print(json.dumps(sel, ensure_ascii=False))
        return
    out = {"book4": {"eval": ev, "judge": {n: judge(ev, n) for n in names if n != "V0"}}}
    for k in STR:
        e = evaluate_target(Rs[k], k, names)
        out[k] = {"eval": e, "judge": {n: judge(e, n) for n in names if n != "V0"}}
    with open(os.path.join(HERE, "summary.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    for n in names:
        if n == "V0":
            continue
        print(n, out["book4"]["judge"][n])


if __name__ == "__main__":
    main()
