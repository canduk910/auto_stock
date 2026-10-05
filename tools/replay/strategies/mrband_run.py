"""평균회귀 재검증 — 횡보장 전용 볼린저 밴드 실행기 (사전 등록 ``mrband/prereg.frozen.md``).

    python3 -m tools.replay.strategies.mrband_run [stock|etf|all]

1차: 세 팔(F-keep · F-liq · NF) × 108 조합의 구간별 요약(학습 T 선택 점수 포함).
2차: 고른 판만 다시 돌려 판정(P1 · J0 · P3 · P4 · P5 · H)과 보고판을 만든다.
결과 = ``_workspace/analysis/strategy_opt_20261005/mrband/results_{stock,etf}.json``.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

from tools.replay.audit import config as C
from tools.replay.audit import panel as PN
from tools.replay.strategies import mrband as M

OUT = os.path.join(C.REPO, "_workspace/analysis/strategy_opt_20261005/mrband")
LABELS_REF = os.path.join(os.path.dirname(C.SCRATCH), "regime", "final_labels.csv")

T_WIN = ("2021-01-29", "2023-09-29")
V_WIN = ("2023-10-04", "2025-10-02")
H_WIN = C.H1Y
T_SUB = (("2021-01-29", "2021-12-30"), ("2022-01-03", "2022-12-29"), ("2023-01-02", "2023-09-29"))
COST = C.COST_RT_JUDGE
NS, KS = (10, 20, 30), (1.5, 2.0, 2.5)
EXITS = ("mid", "upper", "mid_close")
ARMS = ("F-keep", "F-liq", "NF")
GRID = list(itertools.product(NS, KS, M.ENTRIES, EXITS, M.STOPS))
assert len(GRID) == 108
MIN_CAP, MIN_TV = 50_000_000_000, 1_000_000_000
BOOK = {"stock": (0.20, 5), "etf": (0.50, 2)}
ETF_TICKERS = ("069500", "229200")


# ── 데이터 ─────────────────────────────────────────────────────────────────────

def load_stock():
    from tools.replay.strategies import bfb_vcp_audit as BV
    st, _m, master, ext, ext_sha, bench = BV.load("vcp")
    sig_ok = {}
    for t, b in st.bars.items():
        mc = b["mktcap"].astype(float).copy()
        db = b["src"] == 1
        if db.any():
            hts = master.get(t, {}).get("hts_avls_eok")
            last = b["c_raw"][db][-1]
            mc[db] = float(hts) * 1e8 * b["c_raw"][db] / last if (hts and last > 0) else np.nan
        with np.errstate(invalid="ignore"):
            sig_ok[t] = (np.nan_to_num(mc) >= MIN_CAP) & (np.nan_to_num(b["tv"]) >= MIN_TV) & ~b["notrade"]
    return st, sig_ok, bench, {"db_extract_sha256": ext_sha, "store": st.meta}


def load_etf(ext=None):
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    arch = PN.load_archive(C.ETF_ARCHIVE)
    arch = arch[arch.ticker.isin(ETF_TICKERS)].copy()
    ext = ext or PN.load_db_extract()
    db = PN.db_daily_frame(ext, "2026-09-24", C.H1Y[1])
    db = db[db.ticker.isin(ETF_TICKERS)].copy()
    for k in ("open", "high", "low", "close", "volume", "trade_value"):
        db[k] = pd.to_numeric(db[k], errors="coerce")
    db["name"] = db.ticker
    st = PN.build_store(arch, db=db, nontrade="flag", junction_rescale=True)
    sig_ok = {t: ~b["notrade"] for t, b in st.bars.items()}
    k = st.bars["069500"]
    bench = pd.Series(k["c"], index=st.cal[k["di"]])
    return st, sig_ok, bench, {"db_extract_sha256": PN.sha256(C.DB_EXTRACT), "store": st.meta}


def labels_for(st, bench) -> "tuple[np.ndarray, dict]":
    F = M.regime_labels(bench)
    ref = pd.read_csv(LABELS_REF, parse_dates=["d"]).set_index("d")
    common = ref.index.intersection(F.index)
    mism = int((ref.loc[common, "reg"] != F.loc[common, "reg"]).sum())
    gate = {"ref_days": int(len(ref)), "mine_days": int(len(F)), "common": int(len(common)),
            "mismatch": mism, "ref_span": [str(ref.index[0].date()), str(ref.index[-1].date())],
            "mine_span": [str(F.index[0].date()), str(F.index[-1].date())]}
    if mism or len(common) != len(ref):
        raise SystemExit(f"[mrband] 장세 라벨 재현 관문 실패 — 멈춘다: {gate}")
    lab = np.zeros(len(st.cal), dtype=np.int64)
    s = F.code.reindex(st.cal)
    lab[s.notna().to_numpy()] = s.dropna().astype(int).to_numpy()
    return lab, gate


def gwin(cal, w):
    return int(cal.searchsorted(pd.Timestamp(w[0]))), int(cal.searchsorted(pd.Timestamp(w[1]), side="right")) - 1


# ── 1차: 전 조합 요약 ─────────────────────────────────────────────────────────

POP_COLS = ("tid", "e_gd", "x_gd", "E", "X", "Xa", "reg", "jump", "reason")


def build_pops(st, sig_ok, lab, nk_list, ec_list, bars=None, keep_all=frozenset()):
    """{(arm, N, k, entry, exit, stop): pop 배열 dict}. ``keep_all`` 의 키는 겹치는 후보 전부도 반환(계좌용)."""
    bars = bars or st.bars
    tickers = sorted(bars)
    tid = {t: i for i, t in enumerate(tickers)}
    acc, allc = {}, {}
    for t in tickers:
        b = bars[t]
        for (n, k) in nk_list:
            if len(b["o"]) < n + 2:
                continue
            ind = M.ticker_ind(b, lab, n, k)
            for (ex, sp) in ec_list:
                em = M.EXITS[ex]
                ck = M.candidates_for_ticker(t, b, lab, sig_ok[t], n=n, k=k, exit_mode=em, stop=sp, liq=False,
                                             sideways_only=False, ind=ind)
                cl = M.candidates_for_ticker(t, b, lab, sig_ok[t], n=n, k=k, exit_mode=em, stop=sp, liq=True,
                                             sideways_only=True, ind=ind)
                for en in M.ENTRIES:
                    arms = {"NF": ck[en], "F-keep": [c for c in ck[en] if c.reg in M.SIDEWAYS], "F-liq": cl[en]}
                    for arm, cands in arms.items():
                        key = (arm, n, k, en, ex, sp)
                        rows = acc.setdefault(key, [])
                        for c in M.population(cands):
                            rows.append((tid[t], c.e_gd, c.x_gd, c.E, c.X, c.X_adv, c.reg, c.jump, c.reason))
                        if key in keep_all:
                            allc.setdefault(key, []).extend(cands)
    out = {}
    for key, rows in acc.items():
        a = np.array(rows, dtype=float) if rows else np.zeros((0, len(POP_COLS)))
        out[key] = {c: a[:, i] for i, c in enumerate(POP_COLS)}
        for c in ("tid", "e_gd", "x_gd", "reg", "reason"):
            out[key][c] = out[key][c].astype(np.int64)
        out[key]["jump"] = out[key]["jump"].astype(bool)
    return out, tickers, allc


def nets(p, cost=COST, adverse=False):
    X = p["Xa"] if adverse else p["X"]
    return (1 - cost / 2) * X / ((1 + cost / 2) * p["E"]) - 1


def sel(p, cal, win, *, jump_ok=False):
    g0, g1 = gwin(cal, win)
    m = (p["e_gd"] >= g0) & (p["e_gd"] <= g1)
    if not jump_ok:
        m &= ~p["jump"]
    return m


def keys_tw(p, m, weekid):
    return p["tid"][m] * 100000 + weekid[p["e_gd"][m]]


def summarize_all(pops, cal, weekid, t_years):
    rows = []
    for key, p in pops.items():
        r = {"arm": key[0], "N": key[1], "k": key[2], "entry": key[3], "exit": key[4], "stop": key[5]}
        v = nets(p)
        for nm, w in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN)):
            m = sel(p, cal, w)
            r[f"{nm}_n"] = int(m.sum())
            r[f"{nm}_mean"] = float(v[m].mean()) if m.any() else float("nan")
        mT = sel(p, cal, T_WIN)
        r["T_per_year"] = r["T_n"] / t_years
        if r["T_n"] >= 2:
            est, lo, hi, se = M.cboot(v[mT], keys_tw(p, mT, weekid))
        else:
            lo = float("nan")
        r["T_lo90"] = lo
        r["T_sub"] = [float(v[sel(p, cal, w)].mean()) if sel(p, cal, w).any() else float("nan") for w in T_SUB]
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


# ── 2차: 고른 판 상세 ─────────────────────────────────────────────────────────

def trade_block(p, cal, win, weekid, *, jump_ok=False, cost=COST):
    m = sel(p, cal, win, jump_ok=jump_ok)
    v = nets(p, cost)[m]
    out = {"n": int(m.sum())}
    if not m.any():
        return out
    keys = keys_tw(p, m, weekid)
    est, lo, hi, se = M.cboot(v, keys)
    out.update(mean=est, lo90=lo, hi90=hi, se=se, win_rate=float((v > 0).mean()),
               hold_days=float(np.mean(p["x_gd"][m] - p["e_gd"][m] + 1)),
               adverse_mean=float(nets(p, cost, adverse=True)[m].mean()),
               reasons={M.REASONS[k]: float(c / m.sum()) for k, c in Counter(p["reason"][m].tolist()).items()},
               top1pct_ex_mean=float(np.sort(v)[:max(1, int(len(v) * 0.99))].mean()))
    # 사후 발견 S1(보고만) — 같은 날 몰린 신호의 상관: 주 군집 · 신호일 같은 무게
    e = p["e_gd"][m]
    _, wlo, whi, _ = M.cboot(v, weekid[e])
    dm = pd.Series(v).groupby(e).mean()
    sz = pd.Series(v).groupby(e).size().sort_values(ascending=False)
    out.update(week_lo90=wlo, week_hi90=whi, day_weighted_mean=float(dm.mean()), signal_days=int(len(dm)),
               top10_days_share=float(sz.head(10).sum() / len(v)),
               top_days=[str(int(g)) for g in sz.index[:5]])
    for M_ in (108, 324):
        out[f"bonf_lo_{M_}"] = float(est - norm.ppf(1 - 0.05 / M_) * se) if se == se else float("nan")
    return out


def regime_cells(p, cal, win, weekid):
    m0 = sel(p, cal, win)
    v = nets(p)
    out = {}
    for code in range(1, 7):
        m = m0 & (p["reg"] == code)
        name = M.REG_NAMES[[k for k, c in M.REG_CODE.items() if c == code][0]]
        if m.sum() >= 2:
            est, lo, hi, _ = M.cboot(v[m], p["e_gd"][m])
            out[name] = {"n": int(m.sum()), "mean": est, "lo90": lo, "hi90": hi}
        else:
            out[name] = {"n": int(m.sum()), "mean": float(v[m].mean()) if m.any() else None}
    return out


def books(allc, st, cal, win, kind):
    pr, mp = BOOK[kind]
    g0, g1 = gwin(cal, win)
    cands = [c for c in allc if not c.jump]
    runs = [M.run_book(cands, st.bars, cal, g0, g1, s, start_equity=C.BUDGET_C7, cost_rt=COST,
                       pos_ratio=pr, max_pos=mp) for s in C.BOOK_SEEDS]
    yrs = (g1 - g0 + 1) / 252.0
    cg = [M.cagr(r["equity"], C.BUDGET_C7) for r in runs]
    md = [M.mdd(r["equity"], C.BUDGET_C7) for r in runs]
    fills = [r["counts"].get("fill", 0) for r in runs]
    ua = []
    for r in runs:
        c = r["counts"]
        free = c.get("signal", 0) - c.get("slot_full", 0)
        ua.append(c.get("zero_funds", 0) / free if free > 0 else float("nan"))
    return {"cagr_median": float(np.median(cg)), "cagr_min": float(min(cg)), "cagr_max": float(max(cg)),
            "mdd_median": float(np.median(md)), "fills_per_year_median": float(np.median(fills) / yrs),
            "unaffordable_median": float(np.nanmedian(ua)) if any(u == u for u in ua) else float("nan"),
            "slot_full_ratio_seed0": (runs[0]["counts"].get("slot_full", 0) /
                                      max(1, runs[0]["counts"].get("signal", 0))),
            "recon_max_abs": float(max(abs(r["recon"]) for r in runs)), "counts_seed0": runs[0]["counts"]}


def judge(v_blk, h_blk, v_book):
    r = {}
    r["P1"] = bool(v_blk.get("mean", -1) > 0 and v_blk.get("lo90", -1) > C.P1_LO)
    r["J0"] = bool(v_blk.get("lo90", -1) > 0)
    r["J0_bonf108"] = bool(v_blk.get("bonf_lo_108", -1) > 0)
    r["J0_bonf324"] = bool(v_blk.get("bonf_lo_324", -1) > 0)
    r["P3"] = bool(v_book["cagr_median"] > 0 and v_book["mdd_median"] >= C.P3_MDD)
    ua = v_book["unaffordable_median"]
    r["P4"] = bool(v_book["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR and not (ua == ua and ua >= C.P4_UNAFF))
    r["P5_flip"] = bool(np.sign(v_blk.get("mean", 0)) != np.sign(v_blk.get("adverse_mean", 0)))
    if h_blk.get("n", 0) < C.P2_MIN_N:
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


def week_vals(p, cal, win, weekid_str):
    m = sel(p, cal, win)
    return nets(p)[m], [weekid_str[g] for g in p["e_gd"][m]]


def run(kind: str):
    t0 = time.time()
    st, sig_ok, bench, meta = (load_stock() if kind == "stock" else load_etf())
    cal = st.cal
    lab, gate = labels_for(st, bench)
    print(f"[{kind}] loaded {meta['store']} label gate {gate} {time.time()-t0:.0f}s", flush=True)
    iso = [cal[i].isocalendar() for i in range(len(cal))]
    wk_str = [f"{y}-W{w:02d}" for y, w, _ in iso]
    _, weekid = np.unique(wk_str, return_inverse=True)
    gT = gwin(cal, T_WIN)
    t_years = (gT[1] - gT[0] + 1) / 252.0
    nk = list(itertools.product(NS, KS))
    ec = list(itertools.product(EXITS, M.STOPS))
    pops, tickers, _ = build_pops(st, sig_ok, lab, nk, ec)
    print(f"[{kind}] pass1 pops {len(pops)} {time.time()-t0:.0f}s", flush=True)
    rows = summarize_all(pops, cal, weekid, t_years)
    print(f"[{kind}] pass1 summary {time.time()-t0:.0f}s", flush=True)
    chosen = {arm: choose(rows, arm) for arm in ARMS}
    fk, fl = chosen["F-keep"], chosen["F-liq"]
    prim = None
    if fk or fl:
        prim = max([x for x in (fk, fl) if x], key=lambda r: r["T_lo90"])["arm"]
    out = {"kind": kind, "prereg_sha256": open(os.path.join(OUT, "prereg.md.sha256")).read().split()[0],
           "inputs": meta, "label_gate": gate, "t_years": t_years, "grid_rows": rows,
           "chosen": chosen, "primary_arm": prim}
    # 과적합 진단 · 필터 기여 (c)
    diag = {}
    for arm in ARMS:
        a = [r for r in rows if r["arm"] == arm and r["T_n"] >= 10 and r["V_n"] >= 10]
        if len(a) >= 3:
            rho = spearmanr([r["T_mean"] for r in a], [r["V_mean"] for r in a]).correlation
            diag[arm] = {"n_combos": len(a), "spearman_T_V_mean": float(rho)}
    idx = {(r["arm"],) + tuple(r[x] for x in ("N", "k", "entry", "exit", "stop")): r for r in rows}
    for per in ("T", "V"):
        better, tot = 0, 0
        for g in GRID:
            a, b = idx.get(("F-keep",) + g), idx.get(("NF",) + g)
            if a and b and a[f"{per}_n"] >= 10 and b[f"{per}_n"] >= 10:
                tot += 1
                better += int(a[f"{per}_mean"] > b[f"{per}_mean"])
            diag[f"Fkeep_gt_NF_{per}"] = {"better": better, "of": tot}
        for arm in ARMS:
            vals = [r[f"{per}_mean"] for r in rows if r["arm"] == arm and r[f"{per}_n"] >= 10]
            diag[f"{arm}_{per}_mean_dist"] = ({"median": float(np.median(vals)), "max": float(np.max(vals)),
                                               "share_pos": float(np.mean(np.array(vals) > 0)), "n": len(vals)}
                                              if vals else None)
    out["diag"] = diag
    # 2차
    want = {}
    for arm, r in chosen.items():
        if r:
            want[(arm, r["N"], r["k"], r["entry"], r["exit"], r["stop"])] = arm
    if prim:
        r = chosen[prim]
        want.setdefault(("NF", r["N"], r["k"], r["entry"], r["exit"], r["stop"]), "NF@primary")
    nk2 = sorted({(k[1], k[2]) for k in want})
    ec2 = sorted({(k[4], k[5]) for k in want})
    pops2, _, allc = build_pops(st, sig_ok, lab, nk2, ec2, keep_all=frozenset(want))
    # H 잠정 종가 표시 행 = 거래 없음
    bars_p = {}
    for t, b in st.bars.items():
        if "prov" in b and np.asarray(b["prov"]).astype(bool).any():
            nb = dict(b)
            nb["notrade"] = np.asarray(b["notrade"], bool) | np.asarray(b["prov"]).astype(bool)
            bars_p[t] = nb
        else:
            bars_p[t] = b
    sig_p = {t: sig_ok[t] & ~bars_p[t]["notrade"] for t in st.bars}
    pops_p = build_pops(st, sig_p, lab, nk2, ec2, bars=bars_p)[0] if kind == "stock" else None
    detail = {}
    for key, tag in want.items():
        p = pops2[key]
        d = {"key": list(key), "tag": tag}
        for nm, w in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN)):
            d[nm] = trade_block(p, cal, w, weekid)
            d[nm + "_cost028"] = trade_block(p, cal, w, weekid, cost=0.0028).get("mean")
            d[nm + "_cost048"] = trade_block(p, cal, w, weekid, cost=0.0048).get("mean")
            d[nm + "_with_jump"] = trade_block(p, cal, w, weekid, jump_ok=True).get("mean")
            d[nm + "_jump_excluded_n"] = int((sel(p, cal, w, jump_ok=True) & p["jump"]).sum())
            d[nm + "_regime"] = regime_cells(p, cal, w, weekid)
        if pops_p is not None:
            d["H_prov_halt"] = trade_block(pops_p[key], cal, H_WIN, weekid)
        d["book"] = {nm: books(allc[key], st, cal, w, kind) for nm, w in (("T", T_WIN), ("V", V_WIN),
                                                                          ("H", H_WIN))}
        d["judge"] = judge(d["V"], d["H"], d["book"]["V"])
        detail[tag] = d
        print(f"[{kind}] {tag} {key} V {d['V'].get('mean')} lo {d['V'].get('lo90')} judge {d['judge']['label']} "
              f"{time.time()-t0:.0f}s", flush=True)
    out["detail"] = detail
    # 필터 기여 (a)(b) — V 주 블록
    contrib = {}
    if prim:
        kp = [k for k, t in want.items() if t == prim][0]
        kn_same = ("NF",) + kp[1:]
        a_v, a_w = week_vals(pops2[kp], cal, V_WIN, wk_str)
        b_v, b_w = week_vals(pops2[kn_same], cal, V_WIN, wk_str)
        if len(a_v) and len(b_v):
            contrib["same_params_V"] = dict(zip(("diff", "lo90", "hi90"), M.diff_week_boot(a_v, a_w, b_v, b_w)))
        if chosen["NF"]:
            kn = [k for k, t in want.items() if t == "NF"][0]
            c_v, c_w = week_vals(pops2[kn], cal, V_WIN, wk_str)
            if len(a_v) and len(c_v):
                contrib["best_vs_best_V"] = dict(zip(("diff", "lo90", "hi90"),
                                                     M.diff_week_boot(a_v, a_w, c_v, c_w)))
    out["filter_contrib"] = contrib
    out["regime_days"] = {nm: {M.REG_NAMES[k]: int((lab[gwin(cal, w)[0]:gwin(cal, w)[1] + 1] == c).sum())
                               for k, c in M.REG_CODE.items()}
                          for nm, w in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN))}
    out["elapsed_s"] = time.time() - t0
    with open(os.path.join(OUT, f"results_{kind}.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=float)
    print(f"[{kind}] done {time.time()-t0:.0f}s", flush=True)
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    for kd in (("etf", "stock") if what == "all" else (what,)):
        run(kd)
