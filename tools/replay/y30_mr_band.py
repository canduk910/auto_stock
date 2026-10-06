#!/usr/bin/env python3
"""30년 재검증 — 횡보장 전용 볼린저 밴드 (사전 등록 ``mr_regime/prereg.frozen.md`` §3).

5년판(``strategies/mrband.py``·``mrband_run.py``) 규칙 그대로, 바뀌는 것만 여기서 바꾼다:
시기별 가격제한폭(진입 상한가 문 · 하한가 잠김) · 시기별 비용(진입일/2 + 청산일/2) ·
기업행위 거름 = 가격제한폭 위반 표시 행 · 시대 중립 유니버스 · 30년 6장세 라벨 · ETF 판 = 연속 계열 한 종목.

    python -m replay.y30_mr_band <scratch_dir> <out_dir> [stock|etf|all]
"""
from __future__ import annotations

import itertools
import json
import math
import multiprocessing as mp
import os
import pickle
import sys
import time
from collections import Counter
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, ".."), os.path.join(_HERE, "..", "..")):
    _p = os.path.abspath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import y30_mr_data as Y  # noqa: E402
from replay.strategies import mrband as M  # noqa: E402

NS, KS = (10, 20, 30), (1.5, 2.0, 2.5)
EXITS = ("mid", "upper", "mid_close")
ARMS = ("F-keep", "F-liq", "NF")
GRID = list(itertools.product(NS, KS, M.ENTRIES, EXITS, M.STOPS))
assert len(GRID) == 108
BOOK = {"stock": (0.20, 5), "etf": (0.50, 2)}
C7 = 4_707_820
SEEDS = tuple(range(16))
CURRENT = {"stock": ("F-liq", 30, 2.5, "touch", "mid", "atr"), "etf": ("F-liq", 20, 2.0, "touch", "mid", "atr")}
P1_LO, P3_MDD, P4_FILLS, P4_UNAFF, MIN_H = -0.002, -0.35, 12, 0.50, 15


class Cand(NamedTuple):
    tid: int
    e_gd: int
    x_gd: int
    xa_gd: int
    phase: int
    E: float
    X: float
    Xa: float
    reason: int
    reg: int
    jump: bool
    E_raw: float


# ── 신호 · 후보 (mrband.candidates_for_ticker 와 같은 규칙 + 시기별 폭) ──────────

def locked_bars_lim(o, h, l, c, lim) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore"):
        return (pc > 0) & (o <= pc * (1.0 - lim + 0.01)) & (h == l)


def ticker_cands(tid, b, lab_gd, sig_ok, n, k, exit_mode, stop, liq, sideways_only, ind):
    o, h, l, c, g0 = b["o"], b["h"], b["l"], b["c"], b["g0"]
    nb = len(o)
    out = {m: [] for m in M.ENTRIES}
    if nb < n + 2:
        return out
    mid, up, atr, nt, lk, fcs, lab, nonside, pc = (ind[x] for x in ("mid", "up", "atr", "nt", "lk", "fcs", "lab",
                                                                    "nonside", "pc"))
    sig = {m: ind["sig"][m] & sig_ok for m in M.ENTRIES}
    anyday = sig["touch"] | sig["reentry"]
    cache = {}
    for ts in np.nonzero(anyday[:-1])[0]:
        e = ts + 1
        if nt[e] or not (o[e] > 0) or lab[e] == 0:
            continue
        if pc[e] > 0 and o[e] >= pc[e] * (1.0 + b["lim"][e] - 0.01):
            continue
        if sideways_only and lab[e] not in M.SIDEWAYS:
            continue
        if e not in cache:
            sp = M.stop_price(o[e], stop, atr[ts])
            x, X, r, ph = M.sim_trade(o, h, l, c, nt, lk, mid, up, nonside, e, sp, exit_mode, liq, False)
            xa, Xa, _, _ = M.sim_trade(o, h, l, c, nt, lk, mid, up, nonside, e, sp, exit_mode, liq, True)
            j0 = max(0, ts - n + 1)
            jump = bool(fcs[max(x, xa) + 1] - fcs[j0 + 1] > 0)  # mrband 와 같은 창(j0+1 .. 청산 봉)
            cache[e] = Cand(tid, int(e + g0), int(x + g0), int(xa + g0), int(ph), float(o[e]), float(X), float(Xa),
                            int(r), int(lab[e]), jump, float(b["o_raw"][e]))
        for m in M.ENTRIES:
            if sig[m][ts]:
                out[m].append(cache[e])
    return out


def ind_for(b, lab_gd, n, k):
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    mid, lo, up = M.bollinger(c, n, k)
    lab = lab_gd[b["g0"]:b["g0"] + len(o)]
    return {"mid": mid, "lo": lo, "up": up, "atr": M.atr_sma(h, l, c), "nt": np.asarray(b["notrade"], np.bool_),
            "lk": locked_bars_lim(o, h, l, c, b["lim"]), "fcs": np.r_[0, np.cumsum(b["flag"])], "lab": lab,
            "nonside": ~np.isin(lab, M.SIDEWAYS), "pc": np.r_[np.nan, c[:-1]],
            "sig": {m: M.entry_days(c, lo, m) for m in M.ENTRIES}}


def population(cands):
    lst = sorted(cands, key=lambda z: z.e_gd)
    out, last_x = [], -1
    for cd in lst:
        if cd.e_gd > last_x:
            out.append(cd)
            last_x = cd.x_gd
    return out


POP_DT = np.dtype([("tid", "i4"), ("e", "i4"), ("x", "i4"), ("xa", "i4"), ("E", "f8"), ("X", "f8"), ("Xa", "f8"),
                   ("reg", "i1"), ("jump", "?"), ("reason", "i1")])

G: dict = {}


def work(tid):
    b = G["bars"][tid]
    sig_ok = G["sig_ok"][tid]
    lab_gd = G["lab"]
    keys = G["keys"]
    nk = sorted({(k[1], k[2]) for k in keys})
    ec = sorted({(k[4], k[5]) for k in keys})
    out = {}
    allc = {}
    for (n, k) in nk:
        if len(b["o"]) < n + 2:
            continue
        ind = ind_for(b, lab_gd, n, k)
        for (ex, sp) in ec:
            em = M.EXITS[ex]
            ck = ticker_cands(tid, b, lab_gd, sig_ok, n, k, em, sp, False, False, ind)
            cl = ticker_cands(tid, b, lab_gd, sig_ok, n, k, em, sp, True, True, ind)
            for en in M.ENTRIES:
                arms = {"NF": ck[en], "F-keep": [c for c in ck[en] if c.reg in M.SIDEWAYS], "F-liq": cl[en]}
                for arm, cands in arms.items():
                    key = (arm, n, k, en, ex, sp)
                    if key not in keys:
                        continue
                    pop = population(cands)
                    if pop:
                        out[key] = np.array([(c.tid, c.e_gd, c.x_gd, c.xa_gd, c.E, c.X, c.Xa, c.reg, c.jump, c.reason)
                                             for c in pop], dtype=POP_DT)
                    if key in G["keep_all"]:
                        allc[key] = cands
    return tid, out, allc


# ── 데이터 ─────────────────────────────────────────────────────────────────────

def load(scratch, kind):
    mk = np.load(os.path.join(scratch, "mkt.npz"))
    lab = mk["reg"]
    if kind == "stock":
        with open(os.path.join(scratch, "panel.pkl"), "rb") as fh:
            P = pickle.load(fh)
        uni = Y.universe_shares(P)
        el_cap = Y.eligible_matrix(P.mktcap, uni["mktcap_share"])
        el_tv = Y.eligible_matrix(P.tv, uni["tv_share"])
        lim = Y.limit_matrix(P)
        cost = Y.cost_vector(P.dates)
        bars, sig_ok, names = [], [], []
        for j, t in enumerate(P.tickers):
            fin = np.where(np.isfinite(P.c[j]))[0]
            if len(fin) < 12 or not (el_cap[j] & el_tv[j]).any():
                continue
            a, z = fin[0], fin[-1] + 1
            b = {"o": P.o[j, a:z].astype(float), "h": P.h[j, a:z].astype(float), "l": P.l[j, a:z].astype(float),
                 "c": P.c[j, a:z].astype(float), "o_raw": P.o_raw[j, a:z].astype(float),
                 "notrade": P.notrade[j, a:z].copy(), "flag": P.flag[j, a:z].astype(np.int64),
                 "lim": lim[j, a:z].astype(float), "g0": int(a)}
            bars.append(b)
            sig_ok.append(el_cap[j, a:z] & el_tv[j, a:z] & ~P.notrade[j, a:z])
            names.append(t)
        dates = P.dates
        meta = {"universe": uni, "tickers_used": len(bars), "panel": {k: v for k, v in P.meta.items() if k != "files"}}
        del P
    else:
        sd, sc = mk["sd"], mk["sc"]
        m = pd.read_csv(os.path.join(Y.LONG_DIR, "index", "market_unit_series.csv"), parse_dates=["date"])
        dates = m["date"].values.astype("datetime64[D]")
        assert np.array_equal(dates, sd)
        with open(os.path.join(scratch, "panel.pkl"), "rb") as fh:
            P = pickle.load(fh)
        pd_dates = P.dates
        del P
        a = int(np.searchsorted(dates, pd_dates[0]))
        o, h, l, c = (m[x].to_numpy(float)[a:] for x in ("open", "high", "low", "close"))
        dates = dates[a:]
        assert np.array_equal(dates, pd_dates)
        nt = ~(np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c))
        tab = Y.load_limit_table()
        lim = np.array([Y.limit_on(str(d), "KOSPI", tab) for d in dates])
        import csv
        rows = list(csv.DictReader(open(os.path.join(Y.LONG_DIR, "meta", "regime_costs.csv"), encoding="utf-8")))
        etab = sorted((r["from"], 2 * float(r["fee_one_way_pct_assumed"]) / 100.0) for r in rows)
        cost = np.array([Y.cost_on(str(d), etab) for d in dates])
        bars = [{"o": o, "h": h, "l": l, "c": c, "o_raw": o, "notrade": nt, "flag": np.zeros(len(c), np.int64),
                 "lim": lim, "g0": 0}]
        sig_ok = [~nt]
        names = ["KOSPI200→069500"]
        src = m["source"].tolist()[a:]
        cut = next(i for i, s in enumerate(src) if "069500" in s)
        meta = {"proxy_until": str(dates[cut - 1]), "etf_from": str(dates[cut]), "cost_table": etab}
    return dates, bars, sig_ok, names, lab, cost, meta


def build(kind, keys, keep_all=frozenset(), nproc=8):
    G["keys"] = set(keys)
    G["keep_all"] = set(keep_all)
    tids = list(range(len(G["bars"])))
    acc, allc = {}, {}
    if kind == "etf" or nproc <= 1:
        it = map(work, tids)
        for tid, out, ac in it:
            for kk, v in out.items():
                acc.setdefault(kk, []).append(v)
            for kk, v in ac.items():
                allc.setdefault(kk, []).extend(v)
    else:
        ctx = mp.get_context("fork")
        with ctx.Pool(nproc) as pool:
            for i, (tid, out, ac) in enumerate(pool.imap_unordered(work, tids, chunksize=4)):
                for kk, v in out.items():
                    acc.setdefault(kk, []).append(v)
                for kk, v in ac.items():
                    allc.setdefault(kk, []).extend(v)
                if (i + 1) % 500 == 0:
                    print(f"    {i+1}/{len(tids)}", flush=True)
    pops = {}
    for kk in keys:
        arr = np.concatenate(acc[kk]) if kk in acc else np.zeros(0, POP_DT)
        pops[kk] = arr[np.lexsort((arr["tid"], arr["e"]))]
    return pops, allc


# ── 판정 도구 ──────────────────────────────────────────────────────────────────

class Ctx:
    def __init__(self, dates, cost):
        self.dates = dates
        self.cost = cost
        iso = pd.DatetimeIndex(dates.astype("datetime64[ns]")).isocalendar()
        self.wk_str = [f"{y}-W{w:02d}" for y, w in zip(iso.year, iso.week)]
        _, self.weekid = np.unique(self.wk_str, return_inverse=True)

    def nets(self, p, flat=False, adverse=False):
        X = p["Xa"] if adverse else p["X"]
        x = p["xa"] if adverse else p["x"]
        if flat:
            ce = cx = np.full(len(p), Y.FLAT_COST)
        else:
            ce, cx = self.cost[p["e"]], self.cost[x]
        return (1 - cx / 2) * X / ((1 + ce / 2) * p["E"]) - 1

    def sel(self, p, win, jump_ok=False):
        g0, g1 = Y.seg_bounds(self.dates, win)
        m = (p["e"] >= g0) & (p["e"] <= g1)
        if not jump_ok:
            m &= ~p["jump"]
        return m

    def keys_tw(self, p, m):
        return p["tid"][m].astype(np.int64) * 100000 + self.weekid[p["e"][m]]


def years(win):
    return (pd.Timestamp(win[1]) - pd.Timestamp(win[0])).days / 365.25


def summarize(ctx, pops):
    rows = []
    t_years = years(Y.T_WIN)
    for key, p in pops.items():
        r = {"arm": key[0], "N": key[1], "k": key[2], "entry": key[3], "exit": key[4], "stop": key[5]}
        v = ctx.nets(p)
        for nm, w in Y.SEGS:
            m = ctx.sel(p, w)
            r[f"{nm}_n"] = int(m.sum())
            r[f"{nm}_mean"] = float(v[m].mean()) if m.any() else float("nan")
        mT = ctx.sel(p, Y.T_WIN)
        r["T_per_year"] = r["T_n"] / t_years
        r["T_lo90"] = M.cboot(v[mT], ctx.keys_tw(p, mT))[1] if r["T_n"] >= 2 else float("nan")
        r["T_sub"] = [float(v[ctx.sel(p, w)].mean()) if ctx.sel(p, w).any() else float("nan") for w in Y.T_SUB]
        rows.append(r)
    return rows


def choose(rows, arm):
    cand = [r for r in rows if r["arm"] == arm]
    for tag, ok in (("30/yr", lambda r: r["T_per_year"] >= 30), ("완화 12/yr", lambda r: r["T_per_year"] >= 12),
                    ("표본 부족 n≥10", lambda r: r["T_n"] >= 10)):
        el = [r for r in cand if ok(r) and r["T_lo90"] == r["T_lo90"]]
        if el:
            el.sort(key=lambda r: (-r["T_lo90"], -r["T_mean"], r["N"], r["k"]))
            best = dict(el[0])
            best["selection_tier"] = tag
            best["eligible"] = len(el)
            s = np.sign(best["T_mean"])
            best["robust_subs_same_sign"] = int(sum(1 for x in best["T_sub"] if x == x and np.sign(x) == s))
            best["robust"] = best["robust_subs_same_sign"] >= 2
            return best
    return None


def trade_block(ctx, p, win, *, jump_ok=False, flat=False):
    m = ctx.sel(p, win, jump_ok=jump_ok)
    v = ctx.nets(p, flat=flat)[m]
    out = {"n": int(m.sum()), "per_year": float(m.sum() / years(win))}
    if not m.any():
        return out
    est, lo, hi, se = M.cboot(v, ctx.keys_tw(p, m))
    out.update(mean=est, lo90=lo, hi90=hi, se=se, win_rate=float((v > 0).mean()),
               hold_days=float(np.mean(p["x"][m] - p["e"][m] + 1)),
               adverse_mean=float(ctx.nets(p, flat=flat, adverse=True)[m].mean()),
               reasons={M.REASONS[k]: float(c / m.sum()) for k, c in Counter(p["reason"][m].tolist()).items()})
    e = p["e"][m]
    _, wlo, whi, _ = M.cboot(v, ctx.weekid[e])
    dm = pd.Series(v).groupby(e).mean()
    sz = pd.Series(v).groupby(e).size().sort_values(ascending=False)
    out.update(week_lo90=wlo, week_hi90=whi, day_weighted_mean=float(dm.mean()), signal_days=int(len(dm)),
               top10_days_share=float(sz.head(10).sum() / len(v)),
               top_days=[str(ctx.dates[int(g)]) for g in sz.index[:5]])
    for M_ in (108, 324):
        out[f"bonf_lo_{M_}"] = float(est - norm.ppf(1 - 0.05 / M_) * se) if se == se else float("nan")
    return out


def regime_cells(ctx, p, win):
    m0 = ctx.sel(p, win)
    v = ctx.nets(p)
    out = {}
    for code in range(1, 7):
        m = m0 & (p["reg"] == code)
        name = M.REG_NAMES[[k for k, c in M.REG_CODE.items() if c == code][0]]
        if m.sum() >= 2:
            est, lo, hi, _ = M.cboot(v[m], p["e"][m])
            out[name] = {"n": int(m.sum()), "mean": est, "lo90": lo, "hi90": hi}
        else:
            out[name] = {"n": int(m.sum()), "mean": float(v[m].mean()) if m.any() else None}
    return out


def run_book(cands, bars, cost, g0, g1, seed, *, start_equity, pos_ratio, max_pos):
    """``mrband.run_book`` 와 같은 순서 · 비용만 시기별(진입일/2 · 청산일/2)."""
    rng = np.random.default_rng(seed)
    by_e = {}
    for cd in cands:
        if g0 <= cd.e_gd <= g1:
            by_e.setdefault(cd.e_gd, []).append(cd)
    cash = float(start_equity)
    pos = {}
    eq_prev = float(start_equity)
    equity, cnt = [], Counter()

    def close_px(tid, gd):
        b = bars[tid]
        i = min(max(gd - b["g0"], 0), len(b["c"]) - 1)
        while i > 0 and not math.isfinite(b["c"][i]):
            i -= 1
        return b["c"][i]

    def close_out(tid, px, gd):
        nonlocal cash
        cd, q = pos.pop(tid)
        cash += q * cd.E_raw * (px / cd.E) * (1 - cost[gd] / 2)

    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold = set()
        for tid in list(pos):
            cd, q = pos[tid]
            if cd.x_gd == gd and cd.phase == 0:
                close_out(tid, cd.X, gd)
                sold.add(tid)
        todays = list(by_e.get(gd, []))
        rng.shuffle(todays)
        cs = cost[gd] / 2
        for cd in todays:
            if cd.tid in pos or cd.tid in sold:
                continue
            cnt["signal"] += 1
            if len(pos) >= max_pos:
                cnt["slot_full"] += 1
                continue
            q = int(math.floor(B * pos_ratio / cd.E_raw)) if cd.E_raw > 0 else 0
            if q * cd.E_raw * (1 + cs) > cash:
                q = int(math.floor(cash / (cd.E_raw * (1 + cs))))
            if q <= 0:
                cnt["zero_funds"] += 1
                continue
            cash -= q * cd.E_raw * (1 + cs)
            pos[cd.tid] = (cd, q)
            cnt["fill"] += 1
        for tid in list(pos):
            cd, q = pos[tid]
            if cd.x_gd == gd and cd.phase == 1:
                close_out(tid, cd.X, gd)
        eq = cash + sum(q * cd.E_raw * (close_px(t, gd) / cd.E) for t, (cd, q) in pos.items())
        equity.append(eq)
        eq_prev = eq
    return {"equity": np.array(equity), "counts": dict(cnt)}


def books(allc, bars, cost, dates, win, kind):
    pr, mp_ = BOOK[kind]
    g0, g1 = Y.seg_bounds(dates, win)
    cands = [c for c in allc if not c.jump]
    runs = [run_book(cands, bars, cost, g0, g1, s, start_equity=C7, pos_ratio=pr, max_pos=mp_) for s in SEEDS]
    yrs = years(win)
    cg = [float((r["equity"][-1] / C7) ** (1 / yrs) - 1) for r in runs]
    md = [M.mdd(r["equity"], C7) for r in runs]
    fills = [r["counts"].get("fill", 0) for r in runs]
    ua = []
    for r in runs:
        c = r["counts"]
        free = c.get("signal", 0) - c.get("slot_full", 0)
        ua.append(c.get("zero_funds", 0) / free if free > 0 else float("nan"))
    return {"cagr_median": float(np.median(cg)), "cagr_min": float(min(cg)), "cagr_max": float(max(cg)),
            "mdd_median": float(np.median(md)), "fills_per_year_median": float(np.median(fills) / yrs),
            "unaffordable_median": float(np.nanmedian(ua)) if any(u == u for u in ua) else float("nan"),
            "slot_full_ratio_seed0": runs[0]["counts"].get("slot_full", 0) / max(1, runs[0]["counts"].get("signal", 0))}


def judge(v_blk, h_blk, v_book):
    r = {"P1": bool(v_blk.get("mean", -1) > 0 and v_blk.get("lo90", -1) > P1_LO),
         "J0": bool(v_blk.get("lo90", -1) > 0), "J0_bonf108": bool(v_blk.get("bonf_lo_108", -1) > 0),
         "J0_bonf324": bool(v_blk.get("bonf_lo_324", -1) > 0),
         "P3": bool(v_book["cagr_median"] > 0 and v_book["mdd_median"] >= P3_MDD)}
    ua = v_book["unaffordable_median"]
    r["P4"] = bool(v_book["fills_per_year_median"] >= P4_FILLS and not (ua == ua and ua >= P4_UNAFF))
    r["P5_flip"] = bool(np.sign(v_blk.get("mean", 0)) != np.sign(v_blk.get("adverse_mean", 0)))
    if h_blk.get("n", 0) < MIN_H:
        r["H"] = "판정 불가"
    else:
        r["H"] = "일치" if np.sign(h_blk["mean"]) == np.sign(v_blk.get("mean", 0)) else "뒤집힘"
    if not (r["P1"] and r["J0"]):
        lab = "폐기"
    elif r["P5_flip"] or r["H"] == "뒤집힘":
        lab = "보류"
    elif not (r["P3"] and r["P4"]):
        lab = "폐기(계좌)"
    else:
        lab = "채택 후보"
    r["label"] = lab
    return r


def label_gate(dates, lab):
    ref = "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/regime/final_labels.csv"
    if not os.path.exists(ref):
        return {"ref": None}
    r = pd.read_csv(ref, parse_dates=["d"])
    code = r["reg"].map(M.REG_CODE).to_numpy()
    idx = np.searchsorted(dates, r["d"].values.astype("datetime64[D]"))
    ok = (idx < len(dates)) & (dates[np.minimum(idx, len(dates) - 1)] == r["d"].values.astype("datetime64[D]"))
    mine = lab[idx[ok]]
    return {"ref_days": int(len(r)), "common": int(ok.sum()), "mismatch": int((mine != code[ok]).sum()),
            "first_mismatch": [str(x) for x in r["d"].dt.date[ok][mine != code[ok]].head(5)]}


def run(scratch, out_dir, kind):
    t0 = time.time()
    dates, bars, sig_ok, names, lab, cost, meta = load(scratch, kind)
    G.update(bars=bars, sig_ok=sig_ok, lab=lab)
    ctx = Ctx(dates, cost)
    gate = label_gate(dates, lab)
    print(f"[band {kind}] loaded bars {len(bars)} gate {gate} {time.time()-t0:.0f}s", flush=True)
    keys = [(arm,) + g for arm in ARMS for g in GRID]
    nproc = int(os.environ.get("Y30_NPROC", 8))
    pops, _ = build(kind, keys, nproc=nproc)
    print(f"[band {kind}] pass1 {time.time()-t0:.0f}s", flush=True)
    rows = summarize(ctx, pops)
    chosen = {arm: choose(rows, arm) for arm in ARMS}
    fk, fl = chosen["F-keep"], chosen["F-liq"]
    prim = max([x for x in (fk, fl) if x], key=lambda r: r["T_lo90"])["arm"] if (fk or fl) else None
    out = {"kind": kind, "meta": meta, "label_gate": gate, "grid_rows": rows, "chosen": chosen, "primary_arm": prim}
    diag = {}
    for arm in ARMS:
        a = [r for r in rows if r["arm"] == arm and r["T_n"] >= 10 and r["V_n"] >= 10]
        if len(a) >= 3:
            diag[arm] = {"n_combos": len(a), "spearman_T_V_mean": float(spearmanr([r["T_mean"] for r in a],
                                                                                  [r["V_mean"] for r in a]).correlation)}
        for per in ("T", "V", "H"):
            vals = [r[f"{per}_mean"] for r in rows if r["arm"] == arm and r[f"{per}_n"] >= 10]
            diag[f"{arm}_{per}_dist"] = ({"median": float(np.median(vals)), "max": float(np.max(vals)),
                                          "share_pos": float(np.mean(np.array(vals) > 0)), "n": len(vals)}
                                         if vals else None)
    idx = {(r["arm"], r["N"], r["k"], r["entry"], r["exit"], r["stop"]): r for r in rows}
    for per in ("T", "V"):
        better = tot = 0
        for g in GRID:
            a, b = idx.get(("F-keep",) + g), idx.get(("NF",) + g)
            if a and b and a[f"{per}_n"] >= 10 and b[f"{per}_n"] >= 10:
                tot += 1
                better += int(a[f"{per}_mean"] > b[f"{per}_mean"])
        diag[f"Fkeep_gt_NF_{per}"] = {"better": better, "of": tot}
    out["diag"] = diag
    # 2차 — 현행 · 고른 판 · NF@주판
    want = {CURRENT[kind]: "current"}
    want[("NF",) + CURRENT[kind][1:]] = "NF@current"
    for arm, r in chosen.items():
        if r:
            want.setdefault((arm, r["N"], r["k"], r["entry"], r["exit"], r["stop"]), arm)
    if prim:
        r = chosen[prim]
        want.setdefault(("NF", r["N"], r["k"], r["entry"], r["exit"], r["stop"]), "NF@primary")
    pops2, allc = build(kind, list(want), keep_all=frozenset(want), nproc=nproc)
    print(f"[band {kind}] pass2 build {time.time()-t0:.0f}s", flush=True)
    detail = {}
    for key, tag in want.items():
        p = pops2[key]
        d = {"key": list(key), "tag": tag}
        for nm, w in Y.SEGS:
            d[nm] = trade_block(ctx, p, w)
            d[nm + "_flat038"] = trade_block(ctx, p, w, flat=True).get("mean")
            d[nm + "_with_jump"] = trade_block(ctx, p, w, jump_ok=True).get("mean")
            d[nm + "_jump_excluded_n"] = int((ctx.sel(p, w, jump_ok=True) & p["jump"]).sum())
            d[nm + "_regime"] = regime_cells(ctx, p, w)
        d["T_sub"] = [trade_block(ctx, p, w).get("mean") for w in Y.T_SUB]
        d["era"] = {nm: {kk: v for kk, v in trade_block(ctx, p, w).items()
                         if kk in ("n", "per_year", "mean", "lo90", "hi90", "day_weighted_mean")}
                    for nm, w in Y.ERAS}
        d["book"] = {nm: books(allc.get(key, []), bars, cost, dates, w, kind) for nm, w in Y.SEGS}
        d["book_era"] = {nm: books(allc.get(key, []), bars, cost, dates, w, kind) for nm, w in Y.ERAS}
        d["judge"] = judge(d["V"], d["H"], d["book"]["V"])
        detail[tag] = d
        print(f"[band {kind}] {tag} {key} V {d['V'].get('mean')} judge {d['judge']['label']} {time.time()-t0:.0f}s",
              flush=True)
    out["detail"] = detail
    contrib = {}
    if prim:
        c_ = chosen[prim]
        kp = (prim, c_["N"], c_["k"], c_["entry"], c_["exit"], c_["stop"])
        kn = ("NF",) + kp[1:]

        def wv(p):
            m = ctx.sel(p, Y.V_WIN)
            return ctx.nets(p)[m], [ctx.wk_str[g] for g in p["e"][m]]
        a_v, a_w = wv(pops2[kp])
        b_v, b_w = wv(pops2[kn])
        if len(a_v) and len(b_v):
            contrib["same_params_V"] = dict(zip(("diff", "lo90", "hi90"), M.diff_week_boot(a_v, a_w, b_v, b_w)))
        if chosen["NF"]:
            kc = ("NF", chosen["NF"]["N"], chosen["NF"]["k"], chosen["NF"]["entry"], chosen["NF"]["exit"],
                  chosen["NF"]["stop"])
            c_v, c_w = wv(pops2[kc])
            if len(a_v) and len(c_v):
                contrib["best_vs_best_V"] = dict(zip(("diff", "lo90", "hi90"), M.diff_week_boot(a_v, a_w, c_v, c_w)))
    out["filter_contrib"] = contrib
    out["regime_days"] = {nm: {M.REG_NAMES[k]: int((lab[Y.seg_bounds(dates, w)[0]:Y.seg_bounds(dates, w)[1] + 1] == c).sum())
                               for k, c in M.REG_CODE.items()} for nm, w in Y.SEGS}
    out["elapsed_s"] = time.time() - t0
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"band_results_{kind}.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=float)
    print(f"[band {kind}] done {time.time()-t0:.0f}s", flush=True)
    return out


if __name__ == "__main__":
    scratch, out_dir = sys.argv[1], sys.argv[2]
    what = sys.argv[3] if len(sys.argv) > 3 else "all"
    for kd in (("etf", "stock") if what == "all" else (what,)):
        run(scratch, out_dir, kd)
