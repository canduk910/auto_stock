#!/usr/bin/env python3
"""volatility_breakout 30년 재검증 실행 — prereg §6 재현 대조 → §4 A(현행 30년) → §5 B(최적화).

사전 고정 = ``_workspace/analysis/strategy_30y_20261006/vb/prereg.md``(sha256 동결 — B 실행 전 확인).
출력 = 스크래치 ``opt/vb_y30/*.json`` + 표준출력 요약.

실행:
  python3 tools/replay/strategies/vb_y30_run.py repro     # 5년 재현 대조(동결 전 허용)
  python3 tools/replay/strategies/vb_y30_run.py A         # 현행 규칙 30년 판정
  python3 tools/replay/strategies/vb_y30_run.py B         # 최적화(T 선택 · V 판정 · H 부호)
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from statistics import NormalDist

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

from replay.audit import config as C  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import vb as VB  # noqa: E402
from replay.strategies import vb_y30 as Y  # noqa: E402

OUT = os.path.join(os.path.dirname(C.SCRATCH), "opt", "vb_y30")
PREREG = os.path.join(C.REPO, "_workspace/analysis/strategy_30y_20261006/vb/prereg.md")
WIN = {"T": ("1997-01-02", "2012-12-28"), "T1": ("1997-01-02", "2004-12-30"), "T2": ("2005-01-03", "2012-12-28"),
       "V": ("2013-01-02", "2020-12-30"), "H": ("2021-01-04", "2026-10-02")}
ERAS = [("1997-2001", "1997-01-01", "2001-12-31"), ("2002-2006", "2002-01-01", "2006-12-31"),
        ("2007-2011", "2007-01-01", "2011-12-31"), ("2012-2016", "2012-01-01", "2016-12-31"),
        ("2017-2021", "2017-01-01", "2021-12-31"), ("2022-2026", "2022-01-01", "2026-10-02")]
FILLS = {"base": Y.FILL_BASE, "target": Y.FILL_TARGET, "vb": Y.FILL_VB}
CUR = (1.3, "C", "intraday", -5.0, "F0")
KM = (0.8, 1.3, 2.0)
HOLDS = ("C", "N", "W")
STOPS = (("intraday", -5.0), ("intraday", -8.0), ("close", -5.0))
FILTS = ("F0", "F1", "F2", "F3", "F4", "F5", "F6")
MIN_TPY = 30


def jdump(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if isinstance(o, np.generic) else str(o))


def load(drop_jumps=True):
    os.makedirs(OUT, exist_ok=True)
    pk = os.path.join(OUT, f"store_{'dj' if drop_jumps else 'raw'}.pkl")
    if os.path.exists(pk):
        with open(pk, "rb") as fh:
            return pickle.load(fh)
    st, meta = Y.build(drop_jumps=drop_jumps)
    with open(pk, "wb") as fh:
        pickle.dump((st, meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    return st, meta


def m_day_of(cal):
    s = Y.index_series()
    return MU.m_for_days(cal, pd.DatetimeIndex(s.date), s.close.to_numpy(float))


def gwin(cal, w):
    a = int(cal.searchsorted(pd.Timestamp(w[0])))
    b = int(cal.searchsorted(pd.Timestamp(w[1]), side="right")) - 1
    return a, b


class Ctx:
    def __init__(self, st, meta):
        self.st, self.meta, self.cal = st, meta, st.cal
        self.m_day = m_day_of(self.cal)
        self.cost = Y.cost_rt_for_dates(self.cal, Y.load_costs())
        assert np.isfinite(self.cost).all()
        self.cd = Y.candidates(st, meta["X"], self.m_day, Y.load_limits())
        self.fm = {f: Y.filter_mask(self.cd, f) for f in FILTS}
        self.wk = None
        self._sig = {}

    def sig(self, km, filt, fill):
        k = (km, filt, fill)
        if k not in self._sig:
            self._sig[k] = Y.signals(self.cd, km, filt, fill, self.fm)
        return self._sig[k]

    def pop(self, km, hold, mode, stop, filt, fill, version):
        """P1 모집단 전체 기간 — (신호 행, 순수익(시기별 비용), 총수익, 사유, 청산 gd)."""
        sg = self.sig(km, filt, fill)
        px, why, xg = Y.outcome(self.cd, sg, hold, mode, stop, version)
        keep = Y.cooldown_keep(self.cd, sg, xg)
        gross = px[keep] / sg.E[keep] - 1
        gd = self.cd.gd[sg.idx[keep]]
        return {"row": sg.idx[keep], "gd": gd, "gross": gross, "net": gross - self.cost[gd], "why": why[keep],
                "xg": xg[keep], "E": sg.E[keep], "px": px[keep]}


def sub(p, g):
    m = (p["gd"] >= g[0]) & (p["gd"] <= g[1])
    return {k: v[m] for k, v in p.items()}


def stats(ctx, p, boot=True, net_key="net"):
    r = p[net_key]
    d = {"n": int(len(r))}
    if len(r) == 0:
        return d
    d.update(mean=float(r.mean()), gross=float(p["gross"].mean()), win=float((r > 0).mean()),
             stop_share=float(np.isin(p["why"], (1, 2, 3)).mean()), median=float(np.median(r)),
             mean_c038=float((p["gross"] - C.COST_RT_JUDGE).mean()))
    if boot and len(r) > 1:
        keys = Y.week_keys(ctx.cal, ctx.cd.names, ctx.cd.tk[p["row"]], p["gd"])
        est, lo, hi = Y.cluster_boot(r, keys)
        d.update(lo90=lo, hi90=hi, p1=bool(est > 0 and lo > C.P1_LO))
    return d


def vb_sizer(ext=None):
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    ext = ext or PN.load_db_extract()
    cols = ext["strategy_config"][0]
    row = dict(zip(cols, dict((r[0], r) for r in ext["strategy_config"][1])["volatility_breakout"]))
    params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
    return VB.lot_qty_operating(OpSizer(VolatilityBreakoutStrategy, "volatility_breakout", params)), params


def book(ctx, p, g, sizer):
    sbg = defaultdict(list)
    cd = ctx.cd
    # 계좌는 쿨다운 전 신호 전부를 받아 스스로 쿨다운을 건다 → 모집단 대신 신호 전체가 필요
    for j in range(len(p["row"])):
        gd = int(p["gd"][j])
        if not (g[0] <= gd <= g[1]):
            continue
        r = int(p["row"][j])
        t = cd.names[int(cd.tk[r])]
        sbg[gd].append(Y.BSig(t, gd, float(p["E"][j]), float(p["E"][j] * cd.raw[r]), float(p["px"][j]),
                              int(p["why"][j]), int(p["xg"][j]), float(cd.C[r])))
    runs = [Y.run_book_var(sbg, sizer, ctx.cal, g[0], g[1], seed, start_equity=float(C.BUDGET_C7),
                           cost_rt_gd=ctx.cost, max_pos=VB.VB_OP["max_pos"]) for seed in C.BOOK_SEEDS]
    sm = Y.book_summary(runs, float(C.BUDGET_C7))
    sm["P3"] = bool(sm["cagr_median"] > 0 and sm["mdd_median"] >= C.P3_MDD)
    sm["P4"] = bool(sm["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR
                    and not (sm["unaffordable_ratio_median"] == sm["unaffordable_ratio_median"]
                             and sm["unaffordable_ratio_median"] >= C.P4_UNAFF))
    return sm


def allsig(ctx, km, hold, mode, stop, filt, fill, version):
    """계좌용 — 쿨다운 전 신호 전부(계좌가 산 종목에만 쿨다운)."""
    sg = ctx.sig(km, filt, fill)
    px, why, xg = Y.outcome(ctx.cd, sg, hold, mode, stop, version)
    return {"row": sg.idx, "gd": ctx.cd.gd[sg.idx], "E": sg.E, "px": px, "why": why, "xg": xg}


# ── 재현 대조 ────────────────────────────────────────────────────────────

def run_repro():
    t0 = time.time()
    st, meta = load(drop_jumps=False)
    print("[y30-vb] store raw", meta, f"{time.time()-t0:.0f}s", flush=True)
    m_day = m_day_of(st.cal)
    cd = Y.candidates(st, meta["X"], m_day, Y.load_limits(), absolute=(5e10, 5e10))
    sg = Y.signals(cd, 1.3, "F0", 1.0)
    out = {}
    g = gwin(st.cal, C.W5Y)
    for v in ("pes", "opt"):
        px, why, xg = Y.outcome(cd, sg, "C", "intraday", -5.0, v)
        keep = Y.cooldown_keep(cd, sg, xg)
        gd = cd.gd[sg.idx]
        m = keep & (gd >= g[0]) & (gd <= g[1])
        r = px[m] / sg.E[m] - 1 - C.COST_RT_JUDGE
        out[v] = {"n": int(m.sum()), "mean": float(r.mean()), "stop_share": float((why[m] == 1).mean())}
    out["expect"] = {"n": 14011, "pes": -0.02487, "opt": -0.00358}
    out["signals_W5y"] = int(((cd.gd[sg.idx] >= g[0]) & (cd.gd[sg.idx] <= g[1])).sum())
    out["expect_signals_W5y"] = 19034
    print("[y30-vb] repro", out, f"{time.time()-t0:.0f}s", flush=True)
    jdump(os.path.join(OUT, "repro.json"), out)


# ── A ──────────────────────────────────────────────────────────────────

def prereg_sha():
    h = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    frozen = open(PREREG.replace(".md", ".sha256")).read().split()[0]
    if h != frozen:
        raise SystemExit(f"[y30-vb] prereg sha 불일치 — 멈춘다 {h} != {frozen}")
    return h


def run_A():
    t0 = time.time()
    sha = prereg_sha()
    st, meta = load()
    ctx = Ctx(st, meta)
    cal, cd = ctx.cal, ctx.cd
    print("[y30-vb] A loaded", meta["X"], "jump_rows", meta["jump_rows_dropped"], "cands", len(cd.gd),
          f"{time.time()-t0:.0f}s", flush=True)
    out = {"prereg_sha256": sha, "meta": meta, "n_cands": int(len(cd.gd))}
    gw = {k: gwin(cal, w) for k, w in WIN.items()}
    out["windows_days"] = {k: g[1] - g[0] + 1 for k, g in gw.items()}
    # 후보 수
    nc = np.bincount(cd.gd, minlength=len(cal))
    out["cand_per_day"] = {k: {"median": float(np.median(nc[g[0]:g[1] + 1])),
                               "p10": float(np.percentile(nc[g[0]:g[1] + 1], 10)),
                               "max": int(nc[g[0]:g[1] + 1].max())} for k, g in gw.items() if k in ("T", "V", "H")}
    out["cand_per_day_by_era"] = {}
    for nm, a, b in ERAS:
        g = gwin(cal, (a, b))
        out["cand_per_day_by_era"][nm] = float(np.median(nc[g[0]:g[1] + 1]))
    sizer, params = vb_sizer()
    out["op_params"] = {k: params.get(k) for k in ("position_ratio", "max_positions", "max_lot_ratio_mult",
                                                   "k_value_krx_main", "stop_loss_main", "k_period")}
    km, hold, mode, stop, filt = CUR
    A = {}
    pops = {}
    for fn, fill in FILLS.items():
        for v in ("pes", "opt"):
            p = ctx.pop(km, hold, mode, stop, filt, fill, v)
            pops[(fn, v)] = p
            row = {}
            for w in ("T", "V", "H"):
                row[w] = stats(ctx, sub(p, gw[w]))
            for nm, a, b in ERAS:
                row["era_" + nm] = stats(ctx, sub(p, gwin(cal, (a, b))), boot=(fn == "base"))
            yrs = defaultdict(list)
            for j, gd in enumerate(p["gd"]):
                yrs[cal[gd].year].append(j)
            row["years"] = {str(y): {"n": len(ix), "mean": float(p["net"][ix].mean()),
                                     "gross": float(p["gross"][ix].mean())} for y, ix in sorted(yrs.items())}
            A[f"{fn}_{v}"] = row
            print(f"[y30-vb] A {fn} {v}", {w: {k: row[w].get(k) for k in ("n", "mean", "lo90", "gross", "p1")}
                                          for w in ("T", "V", "H")}, f"{time.time()-t0:.0f}s", flush=True)
    out["A_pop"] = A
    # P3·P4 (기본판 두 판 + 보고: VB 실측판)
    bk = {}
    for fn in ("base", "vb"):
        for v in ("pes", "opt"):
            sall = allsig(ctx, km, hold, mode, stop, filt, FILLS[fn], v)
            for w in ("T", "V", "H"):
                bk[f"{fn}_{v}_{w}"] = book(ctx, sall, gw[w], sizer)
                print(f"[y30-vb] book {fn} {v} {w}", {k: bk[f'{fn}_{v}_{w}'][k] for k in
                      ("cagr_median", "mdd_median", "fills_per_year_median", "unaffordable_ratio_median", "P3", "P4")},
                      f"{time.time()-t0:.0f}s", flush=True)
    out["A_book"] = bk
    # 기준선
    idx = Y.index_series()
    md = dict(zip(cal, ctx.m_day))
    mfn = lambda d: md.get(d, np.nan)  # noqa: E731
    out["baseline"] = {w: Y.baseline(idx, mfn, *WIN[w]) for w in ("T", "V", "H")}
    out["baseline_era"] = {nm: Y.baseline(idx, mfn, a, b) for nm, a, b in ERAS}
    # 판정
    P = {}
    for fn in FILLS:
        for v in ("pes", "opt"):
            r = A[f"{fn}_{v}"]
            P[f"{fn}_{v}"] = {"P1": {w: r[w].get("p1") for w in ("T", "V", "H")},
                              "signs": {w: float(np.sign(r[w]["mean"])) for w in ("T", "V", "H")},
                              "P2_same_sign_3": len({np.sign(r[w]["mean"]) for w in ("T", "V", "H")}) == 1}
    P["P5_flip"] = {fn: {w: bool(np.sign(A[f"{fn}_pes"][w]["mean"]) != np.sign(A[f"{fn}_opt"][w]["mean"]))
                         for w in ("T", "V", "H")} for fn in FILLS}
    bo = P["base_opt"]
    pass_all = (all(bo["P1"][w] for w in ("T", "V", "H")) and not any(P["P5_flip"]["base"].values())
                and all(bk[f"base_opt_{w}"]["P3"] and bk[f"base_opt_{w}"]["P4"] for w in ("T", "V", "H")))
    fails_both = all(sum(1 for w in ("T", "V", "H") if not P[f"base_{v}"]["P1"][w]) >= 2 for v in ("pes", "opt"))
    P["label"] = "30년 통과" if pass_all else ("30년 실패" if fails_both else "혼재")
    out["A_judge"] = P
    print("[y30-vb] A judge", json.dumps(P, ensure_ascii=False, default=str), flush=True)
    # 보고판
    rep = {}
    for v in ("pes", "opt"):
        p = pops[("base", v)]
        rows = p["row"]
        mu = defaultdict(list)
        for j, r in enumerate(rows):
            mv = cd.m[r]
            mu["nan" if not np.isfinite(mv) else f"{mv:g}"].append(j)
        rep[f"by_mu_{v}"] = {k: {"n": len(ix), "mean": float(p["net"][ix].mean())} for k, ix in sorted(mu.items())}
        rep[f"why_{v}"] = dict(Counter(int(x) for x in p["why"]))
        nu = cd.near_up[rows]
        rep[f"near_upper_{v}"] = {"n": int(nu.sum()), "mean": float(p["net"][nu].mean()) if nu.any() else None,
                                  "rest_mean": float(p["net"][~nu].mean())}
        sat = np.array([cal[g].dayofweek == 5 for g in p["gd"]])
        rep[f"saturday_{v}"] = {"n": int(sat.sum()), "mean": float(p["net"][sat].mean()) if sat.any() else None}
        # 무작위 시가 진입 대조군(그날 후보에서 신호 수만큼 · 시가 진입 · 같은 청산 · 시기별 비용 · 씨앗 4)
        ctrl = {w: [] for w in ("T", "V", "H")}
        by_gd = defaultdict(list)
        for r in range(len(cd.gd)):
            by_gd[int(cd.gd[r])].append(r)
        nsig = Counter(int(g) for g in p["gd"])
        for sd in range(4):
            rng = np.random.default_rng(C.BOOT_SEED + sd)
            for gd, n in sorted(nsig.items()):
                lst = by_gd.get(gd, [])
                pick = rng.choice(len(lst), size=min(n, len(lst)), replace=False)
                rr = np.array([lst[x] for x in pick])
                sgr = Y.Sigs(rr, cd.O[rr].copy(), cd.O[rr].copy())
                px, _w, _x = Y.outcome(cd, sgr, "C", "intraday", -5.0, v)
                net = px / cd.O[rr] - 1 - ctx.cost[gd]
                for w in ("T", "V", "H"):
                    if gw[w][0] <= gd <= gw[w][1]:
                        ctrl[w].extend(net.tolist())
        rep[f"random_open_{v}"] = {w: {"n": len(x), "mean": float(np.mean(x))} for w, x in ctrl.items()}
    out["report"] = rep
    out["elapsed_s"] = time.time() - t0
    jdump(os.path.join(OUT, "A_result.json"), out)
    print("[y30-vb] A report", json.dumps(rep, ensure_ascii=False, default=str), f"{out['elapsed_s']:.0f}s", flush=True)


# ── B ──────────────────────────────────────────────────────────────────

def grid():
    return [(km, h, m, s, f) for km in KM for h in HOLDS for (m, s) in STOPS for f in FILTS]


def run_B():
    t0 = time.time()
    sha = prereg_sha()
    st, meta = load()
    ctx = Ctx(st, meta)
    cal = ctx.cal
    gw = {k: gwin(cal, w) for k, w in WIN.items()}
    yrs_T = (gw["T"][1] - gw["T"][0] + 1) / 252.0
    sizer, _params = vb_sizer()
    G = grid()
    assert len(G) == 189 and CUR in G
    out = {"prereg_sha256": sha, "n_grid": len(G)}
    for track, fill in (("base", Y.FILL_BASE), ("vb", Y.FILL_VB)):
        rows = []
        for key in G:
            km, hold, mode, stop, filt = key
            row = {"key": key}
            for v in ("pes", "opt"):
                p = ctx.pop(km, hold, mode, stop, filt, fill, v)
                row[f"T_{v}"] = stats(ctx, sub(p, gw["T"]))
                for nm in ("T1", "T2"):
                    row[f"{nm}_{v}"] = stats(ctx, sub(p, gw[nm]), boot=False)
            row["tpy"] = row["T_opt"]["n"] / yrs_T
            row["eligible"] = row["tpy"] >= MIN_TPY
            row["score"] = min(row["T_opt"].get("lo90", -9), row["T_pes"].get("lo90", -9))
            a, b = row["T1_opt"].get("mean", np.nan), row["T2_opt"].get("mean", np.nan)
            row["robust_T"] = bool(np.isfinite(a) and np.isfinite(b) and np.sign(a) == np.sign(b))
            rows.append(row)
        print(f"[y30-vb] B {track} grid done", f"{time.time()-t0:.0f}s", flush=True)
        elig = [r for r in rows if r["eligible"]]
        elig.sort(key=lambda r: (r["score"], r["T_opt"]["mean"]), reverse=True)
        chosen = elig[0]
        alt = max(elig, key=lambda r: (r["T_opt"]["lo90"], r["T_opt"]["mean"]))
        cur = next(r for r in rows if r["key"] == CUR)
        tr = {"chosen_key": chosen["key"], "chosen_T": chosen, "current_T": cur, "alt_5y_rule_key": alt["key"],
              "alt_5y_rule_T": alt, "n_eligible": len(elig), "top10": elig[:10]}
        # V 판정
        ck = chosen["key"]
        pv = {nm: {v: sub(ctx.pop(*k[:5], fill, v), gw["V"]) for v in ("pes", "opt")}
              for nm, k in (("chosen", ck), ("current", CUR))}
        V = {nm: {v: stats(ctx, pv[nm][v]) for v in ("pes", "opt")} for nm in pv}
        a, b = pv["chosen"]["opt"], pv["current"]["opt"]
        d = Y.week_block_diff(a["net"], Y.week_keys(cal, [], np.zeros(len(a["gd"]), int), a["gd"]),
                              b["net"], Y.week_keys(cal, [], np.zeros(len(b["gd"]), int), b["gd"]))
        z = NormalDist().inv_cdf(1 - 0.05 / len(G))
        d["bonf_lo"] = d["diff"] - z * d["se"]
        V["J1_diff"] = d
        V["J1"] = bool(d["diff"] > 0 and d["lo90"] > 0)
        V["J1b"] = bool(d["bonf_lo"] > 0)
        co = V["chosen"]["opt"]
        V["J2"] = bool(co["mean"] > 0 and co["lo90"] > C.P1_LO)
        V["J3_flip"] = bool(np.sign(co["mean"]) != np.sign(V["chosen"]["pes"]["mean"]))
        V["J4"] = chosen["robust_T"]
        for nm, k in (("chosen", ck), ("current", CUR)):
            for v in ("pes", "opt"):
                V[f"book_{nm}_{v}"] = book(ctx, allsig(ctx, *k[:5], fill, v), gw["V"], sizer)
        V["J5"] = bool(V["book_chosen_opt"]["P3"] and V["book_chosen_opt"]["P4"])
        Hh = {nm: {v: stats(ctx, sub(ctx.pop(*k[:5], fill, v), gw["H"]), boot=False) for v in ("pes", "opt")}
              for nm, k in (("chosen", ck), ("current", CUR))}
        Hh["sign_kept_opt"] = bool(np.sign(Hh["chosen"]["opt"]["mean"]) == np.sign(co["mean"]))
        Hh["sign_kept_pes"] = bool(np.sign(Hh["chosen"]["pes"]["mean"]) == np.sign(V["chosen"]["pes"]["mean"]))
        if not V["J2"]:
            label = "폐기 권고"
        elif V["J1"] and V["J4"] and V["J5"] and not V["J3_flip"] and Hh["sign_kept_opt"] and Hh["sign_kept_pes"]:
            label = "채택 권고"
        else:
            label = "보류"
        tr.update(V=V, H=Hh, label=label)
        # 보고: 축별 평균 · 상위 10 의 V(진단) · 최대 비용 전 총수익 · 양수 조합 수
        ax = {}
        for i, nm in enumerate(("km", "hold", "stop_mode", "stop", "filt")):
            vals = sorted({r["key"][i] for r in rows}, key=str)
            ax[nm] = {str(x): {v: float(np.mean([r[f"T_{v}"]["mean"] for r in rows if r["key"][i] == x]))
                               for v in ("opt", "pes")} for x in vals}
        tr["axis_T"] = ax
        diag = []
        for r in elig[:10]:
            k = r["key"]
            pp = {v: sub(ctx.pop(*k[:5], fill, v), gw["V"]) for v in ("pes", "opt")}
            diag.append({"key": k, "T_score": r["score"], "T_opt": r["T_opt"]["mean"], "T_pes": r["T_pes"]["mean"],
                         "V_opt": float(pp["opt"]["net"].mean()), "V_pes": float(pp["pes"]["net"].mean()),
                         "V_n": int(len(pp["opt"]["net"]))})
        tr["top10_in_V"] = diag
        tr["spearman_top10"] = float(pd.Series([x["T_score"] for x in diag]).rank().corr(
            pd.Series([x["V_opt"] for x in diag]).rank()))
        tr["n_T_opt_mean_pos"] = sum(1 for r in elig if r["T_opt"]["mean"] > 0)
        tr["n_T_pes_mean_pos"] = sum(1 for r in elig if r["T_pes"]["mean"] > 0)
        tr["n_T_both_lo_pos"] = sum(1 for r in elig if r["score"] > 0)
        tr["max_T_gross_opt"] = max(({"key": r["key"], "gross": r["T_opt"]["gross"]} for r in elig),
                                    key=lambda x: x["gross"])
        out[track] = tr
        print(f"[y30-vb] B {track}", json.dumps({"chosen": ck, "alt": alt["key"], "label": label,
                                                 "T": {v: chosen[f"T_{v}"] for v in ("opt", "pes")},
                                                 "V": {k2: V[k2] for k2 in ("chosen", "current", "J1", "J1b", "J2",
                                                                            "J3_flip", "J4", "J5")},
                                                 "H": Hh}, ensure_ascii=False, default=str),
              f"{time.time()-t0:.0f}s", flush=True)
    out["elapsed_s"] = time.time() - t0
    jdump(os.path.join(OUT, "B_result.json"), out)
    print("[y30-vb] B done", f"{out['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "A"
    {"repro": run_repro, "A": run_A, "B": run_B}[mode]()
