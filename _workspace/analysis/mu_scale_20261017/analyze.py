"""상단 확대 판정 (prereg_scale — 앞 prereg §2~§3 규칙 그대로). 지표 함수는 앞 비교·재측정 analyze.py 를 그대로 불러 쓴다.
실행: /opt/anaconda3/envs/upbit-trader/bin/python analyze.py <scratch>  →  summary.json
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
sys.argv = [_argv[0], SCR, "final"]
spec = importlib.util.spec_from_file_location("AV", os.path.join(HERE, "..", "mu_variants_20261016", "analyze.py"))
AV = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AV)
sys.argv = _argv
A0 = AV.A0

STR = ("kojiro", "donchian", "bfb", "vcp")
CANDS = ("S2", "S3")
NAMES = ("V0",) + CANDS
COST = 2 * 0.00014 + 0.002


def load():
    return {k: pickle.load(open(os.path.join(SCR, "ms", f"{k}.pkl"), "rb")) for k in STR}


def seeds_better(C, a, b, wn, key):
    _, ma = A0.summarize(C[(a, wn)])
    _, mb = A0.summarize(C[(b, wn)])
    return int(sum(x[key] > y[key] for x, y in zip(ma, mb)))


def evaluate(R, kind):
    ev = AV.evaluate_target(R, kind, list(NAMES))
    C = R["curves"]
    for wn in ("T", "V", "H"):
        ev[wn]["off"] = {**ev[wn]["off"], **{k: A0.summarize(C[("off", wn)])[0][k]
                                             for k in ("cagr", "calmar", "inv_mean", "days_in_mkt", "worst_month", "ret_per_exposure")}}
        for nm in NAMES[1:]:
            ev[wn][nm]["seeds_better_cagr"] = seeds_better(C, nm, "V0", wn, "cagr")
    return ev


def guard(W, nm):
    a, b = W[nm], W["V0"]
    return bool(a["R1_mdd"] >= b["R1_mdd"] - 0.010 and a["R4_crash"] >= b["R4_crash"] - 0.020 and a["cagr"] >= b["cagr"] - 0.015)


def improve(W, nm):
    a, b = W[nm], W["V0"]
    ret = bool(a["cagr"] >= b["cagr"] + 0.010 and a["seeds_better_cagr"] >= 10)
    rsk = bool(a["R4_crash"] >= b["R4_crash"] + 0.030 and a["seeds_better_R4"] >= 10)
    return ret, rsk


def judge(ev, nm):
    T, V, H = ev["T"], ev["V"], ev["H"]
    g = guard(T, nm) and guard(V, nm)
    rV, kV = improve(V, nm)
    rT, kT = improve(T, nm)
    lab = "기각(위험·수익 악화)" if not g else ("채택 후보" if (rV or kV) else "개선 없음")
    hrev = bool(H[nm]["R1_mdd"] < H["V0"]["R1_mdd"] - 0.010 and H[nm]["R4_crash"] < H["V0"]["R4_crash"] - 0.020)
    tt = (T[nm].get("timing_ok"), V[nm].get("timing_ok"))
    tim = "T·V 둘 다" if all(tt) else ("없음" if not any(tt) else "한쪽")
    same_T = (rV and rT) or (kV and kT)
    conf = ("높음" if same_T and not hrev else "중간") if lab == "채택 후보" else "낮음"
    return {"label": lab + (" (H 반전)" if hrev else ""), "guard_T": guard(T, nm), "guard_V": guard(V, nm),
            "I_ret_V": rV, "I_risk_V": kV, "I_ret_T": rT, "I_risk_T": kT, "placebo_timing": tim, "confidence": conf}


def strict_verdict(ev, jd):
    T, V = ev["T"], ev["V"]
    zg = guard(T, "Z") and guard(V, "Z")
    z_better = all(W["Z"]["cagr"] >= W["V0"]["cagr"] + 0.010 and W["Z"]["seeds_better_cagr"] >= 10 for W in (T, V))
    too = any(jd[n]["label"].startswith("채택 후보") for n in ("F2", "F3")) or (zg and z_better)
    role = all(((W["V0"]["R1_mdd"] - W["Z"]["R1_mdd"] >= 0.010) or (W["V0"]["R4_crash"] - W["Z"]["R4_crash"] >= 0.020))
               and W["V0"]["cagr"] >= W["Z"]["cagr"] - 0.015 for W in (T, V))
    lab = "상충" if (too and role) else ("지나치게 엄격" if too else ("제 역할을 한다" if role else "판별 불가"))
    contrib = {wn: {k: ev[wn]["V0"][k] - ev[wn]["Z"][k] for k in ("R1_mdd", "R4_crash", "cagr", "calmar", "inv_mean")}
               for wn in ("T", "V", "H")}
    return {"label": lab, "Z_guard": zg, "Z_cagr_better_TV": z_better, "role_TV": role, "V0_minus_Z": contrib}


def trade_table(Rs, wn, strats, vn="off"):
    rows = []
    for k in strats:
        R = Rs[k]
        df = R["trades"].get((vn, wn))
        if df is None or len(df) == 0:
            continue
        df = df[df.gross.notna()].drop_duplicates(["ticker", "gd", "xgd"]).copy()
        mk = np.where(df.kq, "kosdaq", "kospi")
        v0 = R["m"]["V0"]
        df["m"] = [v0[a][g] for a, g in zip(mk, df.gd.to_numpy())]
        df["net"] = df.gross - COST
        df["strat"] = k
        rows.append(df)
    if not rows:
        return None
    D = pd.concat(rows, ignore_index=True)
    D["mb"] = D.m.map(lambda x: "nan" if not np.isfinite(x) else f"{x:g}")
    D["dm"] = D.net - D.groupby("strat").net.transform("mean")
    out = {}
    for b, g in D.groupby("mb"):
        x = g.net.to_numpy()
        out[b] = {"n": int(len(x)), "mean": float(x.mean()), "median": float(np.median(x)), "win": float((x > 0).mean()),
                  "p10": float(np.quantile(x, 0.1)), "p90": float(np.quantile(x, 0.9)), "dm_mean": float(g.dm.mean())}
    z, r = D[D.mb == "0"], D[D.mb != "0"]
    if len(z) > 2 and len(r) > 2:
        diff = z.dm.mean() - r.dm.mean()
        se = np.sqrt(z.dm.var(ddof=1) / len(z) + r.dm.var(ddof=1) / len(r))
        out["m0_minus_rest_dm"] = float(diff)
        out["t"] = float(diff / se)
        out["m0_share"] = float(len(z) / len(D))
    return out


def cuts_table(Rs):
    out = {}
    for k in STR:
        for (vn, wn, m), c in Rs[k]["cuts"].items():
            if wn != "V" or vn not in ("S2", "S3", "V0"):
                continue
            n = max(c.get("n_d1", 0), 1)
            out[f"{k}|{vn}|{m:g}"] = {"calls": int(c["n"]), "eff_mult": c.get("eff_sum", 0) / n, "design_mult": c.get("nom_sum", 0) / n,
                                      "cut_after_design": c.get("cut_vs_design_m", 0) / n, "zero_share": c["zero"] / max(c["n"], 1)}
    cnt = {}
    for k in STR:
        for (vn, wn), c in Rs[k]["counts"].items():
            if wn == "V":
                cnt[f"{k}|{vn}"] = c
    return out, cnt


def main():
    Rs = load()
    RC = AV.book4(Rs)
    out = {}
    ev = evaluate(RC, "book4")
    jd = {n: judge(ev, n) for n in CANDS}
    out["book4"] = {"eval": ev, "judge": jd}
    for k in STR:
        e = evaluate(Rs[k], k)
        j = {n: judge(e, n) for n in CANDS}
        out[k] = {"eval": e, "judge": j}
    out["trades"] = {wn: {"book4": trade_table(Rs, wn, STR), **{k: trade_table(Rs, wn, (k,)) for k in STR}} for wn in ("T", "V", "H")}
    out["cuts"], out["counts_V"] = cuts_table(Rs)
    with open(os.path.join(HERE, "summary.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    for n in CANDS:
        print(n, jd[n])


if __name__ == "__main__":
    main()
