#!/usr/bin/env python3
"""volatility_breakout 효율화 실행 — prereg §3 선택(T) → §4 판정(V, 고른 판 + 현행판) → H 부호 → 보고판.

출력 = 스크래치 ``opt/vb/vb_opt_result.json`` + 표준출력 요약.
실행: ``python3 tools/replay/strategies/vb_opt_run.py``
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from statistics import NormalDist

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import vb as VB  # noqa: E402
from replay.strategies import vb_opt as VO  # noqa: E402
from replay.strategies import vb_run as VR  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(C.SCRATCH), "opt", "vb")
T = ("2020-10-05", "2023-09-29")
T1 = ("2020-10-05", "2022-03-31")
T2 = ("2022-04-01", "2023-09-29")
V = ("2023-10-04", "2025-10-02")
H = ("2025-10-10", "2026-10-02")
MIN_TRADES_PER_YEAR = 30
POSTHOC = "--posthoc" in sys.argv          # prereg_posthoc.md — 종가 손절 + 재난 손절 −10%
SM = "close" if POSTHOC else "intraday"
N_TESTS = 378 if POSTHOC else 189          # Bonferroni 수(사후 = 본 189 + 사후 189)


def rng_of(cal, w):
    return VR.gd_of(cal, w[0]), VR.gd_of(cal, w[1], "right")


def rets(pop, cost=C.COST_RT_JUDGE):
    return np.array([px / s.E - 1.0 - cost for s, px, _w, _x in pop])


def stats(pop, cal, boot=False):
    r = rets(pop)
    d = {"n": len(r), "mean": float(r.mean()) if len(r) else float("nan")}
    if len(r):
        d["win"] = float((r > 0).mean())
        d["stop_share"] = sum(1 for *_a, w, _x in pop if w == "STOP_LOSS") / len(r)
        d["gross"] = float((r + C.COST_RT_JUDGE).mean())
    if boot and len(r) > 1:
        p = J.p1(r, [s.ticker for s, *_ in pop], [cal[s.gd].date() for s, *_ in pop])
        d.update(lo90=p["lo90"], hi90=p["hi90"], p1_pass=p["pass"])
    return d


def book_runs(sigs, st, hold, stop, version, sizer, w, sm="intraday"):
    sbg = {}
    for s in sigs:
        sbg.setdefault(s.gd, []).append(s)
    runs = []
    for seed in C.BOOK_SEEDS:
        open_pos, size_fn = VO.make_book_fns(st.bars, hold, stop, version, sizer, stop_mode=sm)
        runs.append(BK.run_book(sbg, open_pos, size_fn, st.cal, w[0], w[1], seed,
                                start_equity=float(C.BUDGET_C7), cost_side=C.COST_RT_JUDGE / 2,
                                max_pos=VB.VB_OP["max_pos"]))
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    return {"P3": J.p3(sm), "P4": J.p4(sm),
            **{k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                                  "fills_per_year_median", "unaffordable_ratio_median", "recon_max_abs")}}


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    arch, ext, db, st = VR.load_all()
    cal = st.cal
    mcap_fn = VR.mcap_fn_factory(st, ext)
    mday = VR.m_series(st, ext)
    base = VO.base_candidates(st.bars, mcap_fn)
    gT, gT1, gT2, gV, gH = (rng_of(cal, w) for w in (T, T1, T2, V, H))
    yrs_T = (gT[1] - gT[0] + 1) / 252.0
    out = {"prereg_sha256": open(os.path.join(VR.C.REPO, "_workspace/analysis/strategy_opt_20261005/vb/prereg.sha256"))
           .read().split()[0], "windows": {"T": T, "T1": T1, "T2": T2, "V": V, "H": H},
           "trading_days": {k: g[1] - g[0] + 1 for k, g in (("T", gT), ("V", gV), ("H", gH))}}
    print("[opt-vb] loaded", f"{time.time()-t0:.0f}s", out["trading_days"], flush=True)

    # ── §3 탐색(T) ──
    sig_cache = {}
    rows = []
    for km, hold, stop, filt in VO.grid():
        key = (km, filt)
        if key not in sig_cache:
            sig_cache[key] = VO.signals(base, st.bars, km, filt, mday)
        sigs = sig_cache[key]
        row = {"km": km, "hold": hold, "stop": stop, "filt": filt}
        for v in VB.VERSIONS:
            pT = VO.population(sigs, st.bars, hold, stop, v, *gT, stop_mode=SM)
            s = stats(pT, cal, boot=(v == "opt"))
            row[f"T_{v}"] = s
            for nm, g in (("T1", gT1), ("T2", gT2)):
                row[f"{nm}_{v}"] = {"n": None, **stats([x for x in pT if g[0] <= x[0].gd <= g[1]], cal)}
        row["tpy"] = row["T_opt"]["n"] / yrs_T
        row["eligible"] = row["tpy"] >= MIN_TRADES_PER_YEAR
        a, b = row["T1_opt"]["mean"], row["T2_opt"]["mean"]
        row["robust_T"] = bool(np.isfinite(a) and np.isfinite(b) and np.sign(a) == np.sign(b))
        rows.append(row)
    print("[opt-vb] grid done", len(rows), f"{time.time()-t0:.0f}s", flush=True)
    elig = [r for r in rows if r["eligible"]]
    elig.sort(key=lambda r: (r["T_opt"]["lo90"], r["T_opt"]["mean"]), reverse=True)
    chosen = elig[0]
    ck = (chosen["km"], chosen["hold"], chosen["stop"], chosen["filt"])
    cur = next(r for r in rows if (r["km"], r["hold"], r["stop"], r["filt"]) == VO.CURRENT)
    if POSTHOC:                      # 현행판은 늘 장중 손절 −5(운영 그대로)
        cur = {"km": 1.3, "hold": "C", "stop": -5.0, "filt": "F0"}
        for v in VB.VERSIONS:
            cur[f"T_{v}"] = stats(VO.population(sig_cache[(1.3, "F0")], st.bars, "C", -5.0, v, *gT), cal)
    out["n_grid"] = len(rows)
    out["n_eligible"] = len(elig)
    out["chosen_key"] = ck
    out["current_key"] = VO.CURRENT
    out["chosen_T"] = chosen
    out["current_T"] = cur
    out["top10_T"] = elig[:10]
    out["grid"] = rows
    print("[opt-vb] chosen", ck, json.dumps({k: chosen[k] for k in ("T_opt", "T_pes", "T1_opt", "T2_opt", "tpy")},
                                            default=float), flush=True)
    print("[opt-vb] current", json.dumps({k: cur.get(k) for k in ("T_opt", "T_pes", "T1_opt", "T2_opt", "tpy")},
                                         default=float), flush=True)

    # ── §4 판정(V) ──
    def popsV(key, g, fill=VO.FILL_BASE, sm=SM):
        km, hold, stop, filt = key
        sigs = sig_cache[(km, filt)] if fill == VO.FILL_BASE else VO.signals(base, st.bars, km, filt, mday, fill)
        return {v: VO.population(sigs, st.bars, hold, stop, v, *g, stop_mode=sm) for v in VB.VERSIONS}

    pc, pk = popsV(ck, gV), popsV(VO.CURRENT, gV, sm="intraday")
    vres = {"chosen": {v: stats(pc[v], cal, boot=True) for v in VB.VERSIONS},
            "current": {v: stats(pk[v], cal, boot=True) for v in VB.VERSIONS}}
    d = VO.week_block_diff(rets(pc["opt"]), [cal[s.gd].date() for s, *_ in pc["opt"]],
                           rets(pk["opt"]), [cal[s.gd].date() for s, *_ in pk["opt"]])
    z = NormalDist().inv_cdf(1 - 0.05 / N_TESTS)
    d["bonf_lo"] = d["diff"] - z * d["se"]
    d["bonf_z"] = z
    vres["J1_diff_opt"] = d
    vres["J1"] = bool(d["diff"] > 0 and d["lo90"] > 0)
    vres["J1b_bonf"] = bool(d["bonf_lo"] > 0)
    co = vres["chosen"]["opt"]
    vres["J2"] = bool(co["mean"] > 0 and co["lo90"] > C.P1_LO)
    vres["J3_flip"] = bool(np.sign(co["mean"]) != np.sign(vres["chosen"]["pes"]["mean"]))
    vres["J4"] = chosen["robust_T"]
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    sc_cols = ext["strategy_config"][0]
    vrow = dict(zip(sc_cols, dict((r[0], r) for r in ext["strategy_config"][1])["volatility_breakout"]))
    vparams = vrow["params"] if isinstance(vrow["params"], dict) else json.loads(vrow["params"])
    sizer = VB.lot_qty_operating(OpSizer(VolatilityBreakoutStrategy, "volatility_breakout", vparams))
    for nm, key, sm in (("chosen", ck, SM), ("current", VO.CURRENT, "intraday")):
        sigs = sig_cache[(key[0], key[3])]
        for v in VB.VERSIONS:
            vres[f"book_{nm}_{v}"] = book_runs(sigs, st, key[1], key[2], v, sizer, V, sm)
            print(f"[opt-vb] book V {nm} {v}", json.dumps(vres[f"book_{nm}_{v}"], default=str), flush=True)
    vres["J5"] = bool(vres["book_chosen_opt"]["P3"]["pass"] and vres["book_chosen_opt"]["P4"]["pass"])
    out["V"] = vres
    print("[opt-vb] V", json.dumps({k: v for k, v in vres.items() if not k.startswith("book")}, default=float), flush=True)

    # ── H(부호만) ──
    hc, hk = popsV(ck, gH), popsV(VO.CURRENT, gH, sm="intraday")
    out["H"] = {"chosen": {v: stats(hc[v], cal) for v in VB.VERSIONS},
                "current": {v: stats(hk[v], cal) for v in VB.VERSIONS}}
    out["H"]["sign_kept_opt"] = bool(np.sign(out["H"]["chosen"]["opt"]["mean"]) == np.sign(co["mean"]))
    out["H"]["sign_kept_pes"] = bool(np.sign(out["H"]["chosen"]["pes"]["mean"])
                                     == np.sign(vres["chosen"]["pes"]["mean"]))
    print("[opt-vb] H", json.dumps(out["H"], default=float), flush=True)

    # ── 라벨(prereg §4) ──
    if not vres["J2"]:
        label = "폐기 권고"
    elif vres["J1"] and vres["J4"] and vres["J5"] and not vres["J3_flip"] and out["H"]["sign_kept_opt"]:
        label = "채택 권고"
    else:
        label = "보류"
    out["label"] = label

    # ── 보고판 ──
    rep = {}
    for nm, fill in (("fill_target", 1.0), ("fill_bfb_1p93", VO.FILL_BFB)):
        p = popsV(ck, gV, fill)
        rep[f"chosen_V_{nm}"] = {v: stats(p[v], cal) for v in VB.VERSIONS}
        p = popsV(ck, gT, fill)
        rep[f"chosen_T_{nm}"] = {v: stats(p[v], cal) for v in VB.VERSIONS}
    rep["chosen_V_cost_sens_opt"] = {f"{c:.4f}": float(rets(pc["opt"], c).mean()) for c in C.COST_RT_SENS}
    rep["exit_reasons_V_opt"] = dict(Counter(w for *_a, w, _x in pc["opt"]))
    # 과적합 진단: T 상위 10 의 V 평균(진단만 — 선택에 쓰지 않는다)
    diag = []
    for r in elig[:10]:
        key = (r["km"], r["hold"], r["stop"], r["filt"])
        p = popsV(key, gV)
        diag.append({"key": key, "T_opt_mean": r["T_opt"]["mean"], "T_opt_lo90": r["T_opt"]["lo90"],
                     "V_opt_mean": float(rets(p["opt"]).mean()), "V_pes_mean": float(rets(p["pes"]).mean()),
                     "V_n": len(p["opt"])})
    tr = pd.Series([x["T_opt_mean"] for x in diag]).rank()
    vr = pd.Series([x["V_opt_mean"] for x in diag]).rank()
    rep["top10_T_in_V"] = diag
    rep["top10_spearman_T_V"] = float(np.corrcoef(tr, vr)[0, 1])
    # 비용 전 우위가 가장 큰 조합(T, 낙관판 gross) — 「비용을 이길 엣지가 있는가」 의 상한 확인
    rep["max_T_gross_opt"] = max(({"key": (r["km"], r["hold"], r["stop"], r["filt"]), "gross": r["T_opt"]["gross"],
                                   "n": r["T_opt"]["n"]} for r in elig), key=lambda x: x["gross"])
    rep["n_T_opt_mean_pos"] = sum(1 for r in elig if r["T_opt"]["mean"] > 0)
    rep["n_T_opt_lo_pos"] = sum(1 for r in elig if r["T_opt"]["lo90"] > 0)
    out["report"] = rep
    out["elapsed_s"] = time.time() - t0
    out["posthoc"] = POSTHOC
    with open(os.path.join(OUT_DIR, "vb_opt_posthoc_result.json" if POSTHOC else "vb_opt_result.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if isinstance(o, np.generic) else str(o))
    print("[opt-vb] label", label, "report", json.dumps(rep, default=float), f"{out['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    main()
