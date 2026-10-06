"""30년 재검증 — OU 2단계(판정·표). 사전 등록 ``mr_regime/prereg.frozen.md`` §2.

입력 = 1단계 피클(``y30_mr_ou stage1``) + 같은 폴더의 ``panel.pkl``(계좌 평가용 수정 종가).
출력 = ``<out_dir>/ou_results.json``.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import time
from datetime import date

import numpy as np
from scipy.stats import norm, spearmanr

from replay import y30_mr_data as Y
from replay import y30_mr_ou as OU
from replay.strategies.mean_reversion.ou import efficiency_ratio

SEED = 20261001
C7 = 4_707_820
T5_BUDGET = 5_000_000 * 0.95 * 0.05
P1_LO, T1_LO, P3_MDD, P4_FILLS, P4_UNAFF, MIN_H = -0.002, -0.001, -0.35, 12, 0.50, 15
SEG_NAMES = ("T", "V", "H")


def years(win) -> float:
    return (date.fromisoformat(win[1]) - date.fromisoformat(win[0])).days / 365.25


def cboot(values, keys, *, n_boot=2000, seed=SEED, q=0.05, chunk=250):
    """(평균, q 분위, 1−q 분위, 표준편차) — 군집 복원 추출(``mrband.cboot`` 와 같은 방식)."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return (float(v.mean()) if len(v) else float("nan"),) + (float("nan"),) * 3
    _, idx = np.unique(np.asarray(keys), return_inverse=True)
    K = int(idx.max()) + 1
    s1 = np.bincount(idx, weights=v, minlength=K)
    s0 = np.bincount(idx, minlength=K).astype(float)
    rng = np.random.default_rng(seed)
    st = []
    left = n_boot
    while left > 0:
        m = min(chunk, left)
        pick = rng.integers(0, K, size=(m, K))
        st.append(s1[pick].sum(1) / s0[pick].sum(1))
        left -= m
    st = np.concatenate(st)
    return float(v.mean()), float(np.percentile(st, 100 * q)), float(np.percentile(st, 100 * (1 - q))), float(st.std(ddof=1))


def cboot_diff(va, ka, vb, kb, *, n_boot=2000, seed=SEED, q=0.05, chunk=250):
    """mean(a) − mean(b) — 공통 군집 공간에서 같이 재표집."""
    va, vb = np.asarray(va, float), np.asarray(vb, float)
    if len(va) < 2 or len(vb) < 2:
        return (float("nan"),) * 4
    allk = np.concatenate([np.asarray(ka), np.asarray(kb)])
    _, idx = np.unique(allk, return_inverse=True)
    ia, ib = idx[:len(va)], idx[len(va):]
    K = int(idx.max()) + 1
    a1, a0 = np.bincount(ia, weights=va, minlength=K), np.bincount(ia, minlength=K).astype(float)
    b1, b0 = np.bincount(ib, weights=vb, minlength=K), np.bincount(ib, minlength=K).astype(float)
    rng = np.random.default_rng(seed)
    st = []
    left = n_boot
    while left > 0:
        m = min(chunk, left)
        pick = rng.integers(0, K, size=(m, K))
        with np.errstate(invalid="ignore", divide="ignore"):
            st.append(a1[pick].sum(1) / a0[pick].sum(1) - b1[pick].sum(1) / b0[pick].sum(1))
        left -= m
    st = np.concatenate(st)
    st = st[np.isfinite(st)]
    return (float(va.mean() - vb.mean()), float(np.percentile(st, 100 * q)), float(np.percentile(st, 100 * (1 - q))),
            float(st.std(ddof=1)))


class Ctx:
    def __init__(self, payload, panel):
        self.p = payload
        self.dates = payload["dates"]
        self.segi = Y.seg_index(self.dates)
        self.week = self.dates.astype("datetime64[W]").astype(np.int64)
        self.cost = payload["cost"]
        self.mu = payload["mu"]
        self.bench = payload["bench"]
        self.panel = panel
        self.year = self.dates.astype("datetime64[Y]").astype(int) + 1970
        er = np.array([efficiency_ratio(self.bench, t, 20) for t in range(len(self.bench))])
        a, b = Y.seg_bounds(self.dates, Y.T_WIN)
        v = er[a:b + 1]
        v = v[np.isfinite(v)]
        self.er_bounds = (float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3)))
        self.er = er
        self.er_b = np.full(len(er), -1)
        f = np.isfinite(er)
        self.er_b[f & (er <= self.er_bounds[0])] = 0
        self.er_b[f & (er > self.er_bounds[0]) & (er <= self.er_bounds[1])] = 1
        self.er_b[f & (er > self.er_bounds[1])] = 2

    def net(self, a, flat=False):
        return a["gross"].astype(float) - (Y.FLAT_COST if flat else a["cost"].astype(float))

    def keys(self, a):
        return a["tj"].astype(np.int64) * 100000 + (self.week[a["ei"]] - self.week.min())

    def in_seg(self, a, k):
        return self.segi[a["sig"]] == k

    def in_win(self, a, win):
        lo, hi = Y.seg_bounds(self.dates, win)
        return (a["sig"] >= lo) & (a["sig"] <= hi)


def trade_block(ctx: Ctx, a, win_years: float, boot=True) -> dict:
    n = len(a)
    out = {"n": int(n), "per_year": n / win_years if win_years else float("nan")}
    if n == 0:
        return out
    v = ctx.net(a)
    vf = ctx.net(a, flat=True)
    out.update(mean=float(v.mean()), mean_flat=float(vf.mean()), median=float(np.median(v)),
               win=float(np.mean(v > 0)), mean_gross=float(a["gross"].mean()), mean_cost=float(a["cost"].mean()),
               held=float(np.mean(a["xi"] - a["ei"])),
               reasons={OU.REASONS[i]: float(np.mean(a["reason"] == i)) for i in range(len(OU.REASONS))},
               rb_stat=float(np.mean((a["reason"] == 3) & (a["rb"] == 1))),
               rb_unmeas=float(np.mean((a["reason"] == 3) & (a["rb"] == 2))),
               z_entry=float(np.nanmean(a["z_entry"])), mae=float(np.nanmean(a["mae"])),
               mfe=float(np.nanmean(a["mfe"])))
    pos, neg = v[v > 0].sum(), -v[v < 0].sum()
    out["pf"] = float(pos / neg) if neg > 0 else float("inf")
    if boot and n >= 2:
        est, lo, hi, se = cboot(v, ctx.keys(a))
        out.update(lo90=lo, hi90=hi, se=se)
        _, lof, hif, _ = cboot(vf, ctx.keys(a))
        out.update(lo90_flat=lof, hi90_flat=hif)
        dm = {}
        for s, x in zip(a["sig"], v):
            dm.setdefault(int(s), []).append(x)
        out["day_weighted_mean"] = float(np.mean([np.mean(x) for x in dm.values()]))
    return out


# ── 계좌 ───────────────────────────────────────────────────────────────────────

def account(ctx: Ctx, a, win, *, mode: str) -> dict:
    """mode = "p3"(C7 · 전일 평가액 20% · 5슬롯) | "t5"(23.75만 · 슬롯 2 · 현금 ÷ 빈 슬롯). z 낮은 순 · 시기별 비용."""
    g0, g1 = Y.seg_bounds(ctx.dates, win)
    sel = a[(a["sig"] >= g0) & (a["sig"] <= g1)]
    by = {}
    for i in np.argsort(sel["z_entry"], kind="mergesort"):
        by.setdefault(int(sel["ei"][i]), []).append(i)
    C = ctx.panel.c
    budget, slots = (C7, 5) if mode == "p3" else (T5_BUDGET, 2)
    cash = float(budget)
    pos = {}
    eq_prev = float(budget)
    eq = np.empty(g1 - g0 + 1)
    n_sig = n_full = n_unaff = n_fill = 0
    held_tickers = set()
    for d in range(g0, g1 + 1):
        cs_d = ctx.cost[d] / 2.0
        for k in [k for k, p in pos.items() if p["xi"] == d and p["phase_open"]]:
            p = pos.pop(k)
            cash += p["notional"] * (p["exit_px"] / p["entry_px"]) * (1 - cs_d)
            held_tickers.discard(p["tj"])
        for i in by.get(d, []):
            tr = sel[i]
            tj = int(tr["tj"])
            if tj in held_tickers:
                continue
            n_sig += 1
            if len(pos) >= slots:
                n_full += 1
                continue
            px = float(tr["entry_raw"])
            if not (px > 0 and math.isfinite(px)):
                continue
            alloc = eq_prev * 0.20 if mode == "p3" else cash / (slots - len(pos))
            q = int(alloc // (px * (1 + cs_d)))
            if q * px * (1 + cs_d) > cash:
                q = int(cash // (px * (1 + cs_d)))
            if q < 1:
                n_unaff += 1
                continue
            cash -= q * px * (1 + cs_d)
            n_fill += 1
            pos[i] = dict(notional=q * px, tj=tj, entry_px=float(tr["entry_px"]), exit_px=float(tr["exit_px"]),
                          xi=int(tr["xi"]), phase_open=False, last=float(tr["entry_px"]))
            held_tickers.add(tj)
        for k in [k for k, p in pos.items() if p["xi"] == d]:
            p = pos.pop(k)
            cash += p["notional"] * (p["exit_px"] / p["entry_px"]) * (1 - cs_d)
            held_tickers.discard(p["tj"])
        for p in pos.values():
            p["phase_open"] = True
        mtm = 0.0
        for p in pos.values():
            cl = float(C[p["tj"], d])
            if math.isfinite(cl):
                p["last"] = cl
            mtm += p["notional"] * (p["last"] / p["entry_px"])
        eq[d - g0] = cash + mtm
        eq_prev = eq[d - g0]
    yrs = years(win)
    e = np.concatenate([[budget], eq])
    free = n_sig - n_full
    dr = np.diff(e) / e[:-1]
    return dict(cagr=float((eq[-1] / budget) ** (1 / yrs) - 1), mdd=float((e / np.maximum.accumulate(e) - 1).min()),
                total=float(eq[-1] / budget - 1), fills=n_fill, fills_per_year=n_fill / yrs, signals=n_sig,
                slot_full=n_full, unaffordable=n_unaff,
                unaffordable_ratio=(n_unaff / free) if free else float("nan"),
                daily=dr, g0=g0)


def baseline(ctx: Ctx, win) -> dict:
    g0, g1 = Y.seg_bounds(ctx.dates, win)
    b = ctx.bench[g0 - 1:g1 + 1]
    r = b[1:] / b[:-1] - 1
    m = np.nan_to_num(ctx.mu[g0:g1 + 1], nan=1.0)
    yrs = years(win)
    out = {}
    for nm, rr in (("hold", r), ("mu_prop", r * m)):
        e = np.concatenate([[1.0], np.cumprod(1 + rr)])
        out[nm] = dict(cagr=float(e[-1] ** (1 / yrs) - 1), mdd=float((e / np.maximum.accumulate(e) - 1).min()),
                       total=float(e[-1] - 1))
    return out


def pass_table(ctx: Ctx, results, seg=None):
    out = {}
    for m in ("resid", "price", "shuffle", "rw"):
        u = o = ever = consec = anyu = halt = 0
        codes = np.zeros(9)
        for r in results:
            segs = range(3) if seg is None else (seg,)
            pu = any(r["pass"][m][k]["any_usable"] for k in segs)
            for k in segs:
                ps = r["pass"][m][k]
                u += ps["usable"]
                o += ps["ok"]
                codes += ps["codes"]
                halt += ps["halt"]
            anyu += pu
            ever += any(r["pass"][m][k]["ever"] for k in segs)
            consec += any(r["pass"][m][k]["consec"] for k in segs)
        out[m] = dict(windows=int(u), ok=int(o), rate=o / u if u else float("nan"), halt_windows=int(halt),
                      ever=ever / anyu if anyu else float("nan"), consec=consec / anyu if anyu else float("nan"),
                      tickers=int(anyu),
                      reason_share={k: float(codes[v] / u) if u else float("nan")
                                    for k, v in (("ok", 0), ("adf", 1), ("half_life", 2), ("b_range", 3))})
    out["resid_minus_shuffle_pp"] = 100 * (out["resid"]["rate"] - out["shuffle"]["rate"])
    out["resid_minus_rw_pp"] = 100 * (out["resid"]["rate"] - out["rw"]["rate"])
    return out


def keystr(key) -> str:
    ez, xz, sp, k, mode, mu = key
    return f"z|{ez}|{xz}|{sp}|{k}|{mode}|{mu}"


def main(stage1_path: str, out_dir: str):
    t0 = time.time()
    with open(stage1_path, "rb") as fh:
        payload = pickle.load(fh)
    with open(os.path.join(os.path.dirname(stage1_path), "panel.pkl"), "rb") as fh:
        panel = pickle.load(fh)
    ctx = Ctx(payload, panel)
    tr = payload["trades"]
    res = {"meta": payload["meta"] | {"stage2_started": time.strftime("%Y-%m-%d %H:%M:%S")},
           "er_bounds_T": ctx.er_bounds}
    res["meta"]["panel"] = {k: v for k, v in payload["meta"]["panel"].items() if k != "files"}
    res["meta"]["panel_files_sha16"] = payload["meta"]["panel"]["files"]
    yrs = {nm: years(w) for nm, w in Y.SEGS}
    res["seg_years"] = yrs
    # 통과율 (T2)
    res["pass"] = {"all": pass_table(ctx, payload["results"])}
    for k, nm in enumerate(SEG_NAMES):
        res["pass"][nm] = pass_table(ctx, payload["results"], seg=k)
    hl = np.concatenate([r["hl"][0] for r in payload["results"]])
    hla = np.concatenate([r["hl"][1] for r in payload["results"]])
    hs = np.concatenate([r["hl"][2] for r in payload["results"]])
    res["half_life"] = {nm: {"raw": {str(q): float(np.quantile(hl[hs == k], q)) for q in (0.1, 0.5, 0.9)},
                             "kendall": {str(q): float(np.nanquantile(hla[hs == k], q)) for q in (0.1, 0.5, 0.9)}}
                        for k, nm in enumerate(SEG_NAMES) if (hs == k).any()}
    # 기준선
    res["baseline"] = {nm: baseline(ctx, w) for nm, w in Y.SEGS}
    res["baseline_era"] = {nm: baseline(ctx, w) for nm, w in Y.ERAS}
    print(f"[judge] pass/baseline {time.time()-t0:.0f}s", flush=True)

    # ── A 현행 ──
    cur = tr[OU.CURRENT]
    A = {"key": keystr(OU.CURRENT)}
    for k, (nm, w) in enumerate(Y.SEGS):
        a = cur[ctx.in_seg(cur, k)]
        A[nm] = trade_block(ctx, a, yrs[nm])
        A[nm + "_book"] = {kk: v for kk, v in account(ctx, cur, w, mode="p3").items() if kk not in ("daily", "g0")}
        A[nm + "_t5"] = {kk: v for kk, v in account(ctx, cur, w, mode="t5").items() if kk not in ("daily", "g0")}
        mr = np.array([r["missing_ratio"] for r in payload["results"]])
        jmap = {r["j"]: r["missing_ratio"] for r in payload["results"]}
        miss = np.array([jmap.get(int(j), 0.0) > 0.01 for j in a["tj"]], dtype=bool) if len(a) else np.zeros(0, bool)
        A[nm + "_missing_split"] = {"miss_gt_1pct": trade_block(ctx, a[miss], yrs[nm], boot=False),
                                    "rest": trade_block(ctx, a[~miss], yrs[nm], boot=False)}
        # 시장 유닛 × ER
        cells = {}
        for mu in (1.0, 0.75, 0.5, 0.0):
            for eb in (0, 1, 2):
                m = (a["mu"] == mu) & (ctx.er_b[a["sig"]] == eb)
                v = ctx.net(a[m])
                cells[f"mu={mu}|er={eb}"] = {"n": int(m.sum()), "mean": float(v.mean()) if m.any() else None}
        A[nm + "_mu_er"] = cells
        print(f"[judge] A {nm} n={A[nm]['n']} mean={A[nm].get('mean')} {time.time()-t0:.0f}s", flush=True)
    A["era"] = {}
    for nm, w in Y.ERAS:
        a = cur[ctx.in_win(cur, w)]
        A["era"][nm] = trade_block(ctx, a, years(w))
    # T3 대리 — 계좌(p3) 일 수익 vs 시장 계열 일 수익, ER 하위 삼분위 날
    t3 = {}
    for nm, w in Y.SEGS:
        acc = account(ctx, cur, w, mode="p3")
        g0 = acc["g0"]
        d = acc["daily"]
        b = ctx.bench[g0 - 1:g0 + len(d)]
        br = b[1:] / b[:-1] - 1
        lowd = ctx.er_b[g0 - 1:g0 - 1 + len(d)] == 0      # 그날 신호용 ER = 전일 종가 기준
        ok = lowd & np.isfinite(d) & np.isfinite(br)
        t3[nm] = {"n_days": int(ok.sum()),
                  "corr_vs_market": float(np.corrcoef(d[ok], br[ok])[0, 1]) if ok.sum() > 5 and d[ok].std() > 0 else None,
                  "mr_mean_daily": float(d[ok].mean()) if ok.any() else None,
                  "mkt_mean_daily": float(br[ok].mean()) if ok.any() else None}
    A["T3_proxy"] = t3
    # 문턱
    th = {}
    t1 = {nm: (A[nm].get("mean", -1) > 0 and A[nm].get("lo90", -1) > T1_LO) for nm in SEG_NAMES}
    t1f = {nm: (A[nm].get("mean_flat", -1) > 0 and A[nm].get("lo90_flat", -1) > T1_LO) for nm in SEG_NAMES}
    th["T1"] = {"by_seg": t1, "by_seg_flat038": t1f, "verdict": "통과" if all(t1.values()) else "실패"}
    pa = res["pass"]["all"]
    th["T2"] = {"minus_shuffle_pp": pa["resid_minus_shuffle_pp"], "minus_rw_pp": pa["resid_minus_rw_pp"],
                "by_seg": {nm: (res["pass"][nm]["resid_minus_shuffle_pp"], res["pass"][nm]["resid_minus_rw_pp"])
                           for nm in SEG_NAMES},
                "verdict": "통과" if min(pa["resid_minus_shuffle_pp"], pa["resid_minus_rw_pp"]) >= 5 else "실패"}
    th["T3"] = {"verdict": "판정 불가", "why": "30년 기존 전략 일 수익 없음 — 대리는 A.T3_proxy(참고)"}
    signs = {nm: np.sign(A[nm].get("mean", 0)) for nm in SEG_NAMES}
    py = {nm: A[nm]["per_year"] for nm in SEG_NAMES}
    th["T4"] = {"per_year": py, "signs": {k: float(v) for k, v in signs.items()},
                "verdict": "통과" if (min(py.values()) >= 30 and len(set(signs.values())) == 1) else "실패"}
    ua = {nm: A[nm + "_t5"]["unaffordable_ratio"] for nm in SEG_NAMES}
    th["T5"] = {"unaffordable": ua, "verdict": "통과" if all(x < 0.5 for x in ua.values()) else "실패"}
    th["overall"] = "실패" if any(th[x]["verdict"] == "실패" for x in ("T1", "T2", "T4", "T5")) else "통과(T3 판정 불가)"
    A["thresholds"] = th
    A["P1"] = {nm: bool(A[nm].get("mean", -1) > 0 and A[nm].get("lo90", -1) > P1_LO) for nm in SEG_NAMES}
    A["P3"] = {nm: bool(A[nm + "_book"]["cagr"] > 0 and A[nm + "_book"]["mdd"] >= P3_MDD) for nm in SEG_NAMES}
    A["P4"] = {nm: bool(A[nm + "_book"]["fills_per_year"] >= P4_FILLS and not
                        (A[nm + "_book"]["unaffordable_ratio"] >= P4_UNAFF)) for nm in SEG_NAMES}
    res["A"] = A
    print(f"[judge] A done {th['overall']} {time.time()-t0:.0f}s", flush=True)

    # ── B 최적화 ──
    rows = []
    for key in OU.GRID:
        a = tr[key]
        r = {"key": keystr(key)}
        for k, nm in enumerate(SEG_NAMES):
            s = a[ctx.in_seg(a, k)]
            v = ctx.net(s)
            r[nm + "_n"] = int(len(s))
            r[nm + "_mean"] = float(v.mean()) if len(s) else float("nan")
            r[nm + "_mean_flat"] = float(ctx.net(s, flat=True).mean()) if len(s) else float("nan")
        sT = a[ctx.in_seg(a, 0)]
        r["T_per_year"] = len(sT) / yrs["T"]
        if len(sT) >= 2:
            r["T_lo90"] = cboot(ctx.net(sT), ctx.keys(sT))[1]
            r["T_lo90_flat"] = cboot(ctx.net(sT, flat=True), ctx.keys(sT))[1]
        else:
            r["T_lo90"] = r["T_lo90_flat"] = float("nan")
        r["T_sub"] = []
        for w in Y.T_SUB:
            s = a[ctx.in_win(a, w)]
            r["T_sub"].append(float(ctx.net(s).mean()) if len(s) else float("nan"))
        rows.append(r)
    print(f"[judge] B grid {time.time()-t0:.0f}s", flush=True)

    def choose(score):
        el = [r for r in rows if r["T_per_year"] >= 30 and r[score] == r[score]]
        el.sort(key=lambda r: (-r[score], -r["T_mean"]))
        return (el[0], len(el)) if el else (None, 0)

    best, n_el = choose("T_lo90")
    best_flat, _ = choose("T_lo90_flat")
    B = {"grid": rows, "eligible": n_el, "chosen": best, "chosen_flat038": best_flat["key"] if best_flat else None,
         "M": len(OU.GRID)}
    if best:
        s = np.sign(best["T_mean"])
        B["robust_subs_same_sign"] = int(sum(1 for x in best["T_sub"] if x == x and np.sign(x) == s))
        key = next(k for k in OU.GRID if keystr(k) == best["key"])
        ch = tr[key]
        D = {}
        for k, (nm, w) in enumerate(Y.SEGS):
            a = ch[ctx.in_seg(ch, k)]
            D[nm] = trade_block(ctx, a, yrs[nm])
            D[nm + "_book"] = {kk: v for kk, v in account(ctx, ch, w, mode="p3").items() if kk not in ("daily", "g0")}
        D["era"] = {nm: trade_block(ctx, ch[ctx.in_win(ch, w)], years(w)) for nm, w in Y.ERAS}
        aV, cV = ch[ctx.in_seg(ch, 1)], cur[ctx.in_seg(cur, 1)]
        diff = cboot_diff(ctx.net(aV), ctx.keys(aV), ctx.net(cV), ctx.keys(cV))
        D["diff_vs_current_V"] = dict(zip(("diff", "lo90", "hi90", "se"), diff))
        D["diff_vs_current_V"]["bonf_lo"] = float(diff[0] - norm.ppf(1 - 0.05 / len(OU.GRID)) * diff[3])
        aH, cH = ch[ctx.in_seg(ch, 2)], cur[ctx.in_seg(cur, 2)]
        D["diff_vs_current_H"] = dict(zip(("diff", "lo90", "hi90", "se"),
                                          cboot_diff(ctx.net(aH), ctx.keys(aH), ctx.net(cH), ctx.keys(cH))))
        J = {}
        J["is_current"] = best["key"] == keystr(OU.CURRENT)
        J["J1"] = bool(D["diff_vs_current_V"]["diff"] > 0 and D["diff_vs_current_V"]["lo90"] > 0)
        J["J1_bonf"] = bool(D["diff_vs_current_V"]["bonf_lo"] > 0)
        J["J0"] = bool(D["V"].get("lo90", -1) > 0)
        J["J0_bonf"] = bool(D["V"].get("mean", -1) - norm.ppf(1 - 0.05 / len(OU.GRID)) * D["V"].get("se", 1) > 0)
        J["P1"] = bool(D["V"].get("mean", -1) > 0 and D["V"].get("lo90", -1) > P1_LO)
        J["P3"] = bool(D["V_book"]["cagr"] > 0 and D["V_book"]["mdd"] >= P3_MDD)
        J["P4"] = bool(D["V_book"]["fills_per_year"] >= P4_FILLS and not (D["V_book"]["unaffordable_ratio"] >= P4_UNAFF))
        if D["H"]["n"] < MIN_H:
            J["H"] = "판정 불가"
        else:
            J["H"] = "일치" if np.sign(D["H"]["mean"]) == np.sign(D["V"]["mean"]) else "뒤집힘"
        if J["is_current"]:
            lab = "현행이 최선(선택 = 현행)"
        elif not (J["J1"] and J["J0"]):
            lab = "폐기"
        elif J["H"] == "뒤집힘":
            lab = "보류"
        elif not (J["P1"] and J["P3"] and J["P4"]):
            lab = "폐기(계좌)"
        else:
            lab = "채택 후보"
        J["label"] = lab
        D["judge"] = J
        B["detail"] = D
    a = [r for r in rows if r["T_n"] >= 30 and r["V_n"] >= 30]
    B["spearman_T_V"] = float(spearmanr([r["T_mean"] for r in a], [r["V_mean"] for r in a]).correlation) if len(a) > 3 else None
    B["share_pos"] = {nm: float(np.mean([r[nm + "_mean"] > 0 for r in rows if r[nm + "_n"] > 0])) for nm in SEG_NAMES}
    B["top10_T"] = sorted([r for r in rows if r["T_per_year"] >= 30], key=lambda r: -r["T_lo90"])[:10]
    res["B"] = B
    res["meta"]["stage2_seconds"] = time.time() - t0
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ou_results.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=lambda x: x.tolist() if hasattr(x, "tolist") else float(x))
    print(f"[judge] done {time.time()-t0:.0f}s", flush=True)
