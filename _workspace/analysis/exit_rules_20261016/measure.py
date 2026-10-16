"""측정 M1~M5 (T 도출 · V/H 보고) → 동결 규칙 D-S/D-U/D-T/D-C/D-N 적용 → derived.json · variants.json (prereg §2~§5).

실행: /opt/anaconda3/envs/upbit-trader/bin/python measure.py <scratch>
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
sys.path.insert(0, HERE)
import xcommon as X  # noqa: E402

STR = ("kojiro", "donchian", "bfb", "vcp", "etf")
STOCK = ("kojiro", "donchian", "bfb", "vcp")
ZG = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0)
XG = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15)
YG = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0)
TH = (-0.03, -0.05, -0.07, -0.09, -0.11, -0.13, -0.15)
NG = (5, 10, 15, 20, 30, 40, 60)
C_ = 0.0025
TMIN, NMIN, MMIN = -2.0, 100, 12
PROMO = 1.5
KMAX_TOUCH, KMAX_TRAIL = 120, 150
SHIFTS = (126, 252, 378, 504, 756, 1008, 1260, 1512)
CENSOR = ("END", "OPEN", "end")


def load(k):
    with open(os.path.join(SCR, "xr", f"pop_{k}.pkl"), "rb") as fh:
        return pickle.load(fh)


def cl_stats(y, g, ref=0.0):
    y = np.asarray(y, float)
    g = np.asarray(g)
    n = len(y)
    if n == 0:
        return {"n": 0, "months": 0, "mean": None, "t": None}
    mu = float(y.mean())
    df = pd.DataFrame({"r": y - mu, "g": g}).groupby("g").r.sum()
    G = len(df)
    se = float(np.sqrt((df ** 2).sum()) / n * np.sqrt(G / max(G - 1, 1))) if G > 1 else float("nan")
    d = mu - ref
    return {"n": int(n), "months": int(G), "mean": mu, "delta": d, "t": (d / se) if se and se > 0 else None}


def ok_sig(st):
    return (st["n"] >= NMIN and st["months"] >= MMIN and st["t"] is not None and st["delta"] <= -C_ and st["t"] <= TMIN)


def enough(st):
    return st["n"] >= NMIN and st["months"] >= MMIN


def first_point(grid, rows):
    """D-S/D-T: 「Δ ≤ −c ∧ 유의 ∧ 표본 충분 ∧ 다음 두 (표본 충분) 격자점 Δ ≤ 0」 인 가장 작은 격자값."""
    for i, v in enumerate(grid):
        st = rows[str(v)]
        if not ok_sig(st):
            continue
        nxt = [rows[str(w)] for w in grid[i + 1:] if enough(rows[str(w)])][:2]
        if all(x["delta"] <= 0 for x in nxt):
            return v
    return None


def month_of(cal, gd):
    d = cal[gd]
    return d.year * 12 + d.month


# ── M2 · M3 (사건 표본) ──────────────────────────────────────────────────────────
def touch_events(recs, H, cal, unit):
    """unit = 'atr' | 'pct'. 반환 = {격자값: (fwd 배열, 월 배열, ATR% 배열)} · f0 표본."""
    grid = ZG if unit == "atr" else XG
    ev = {v: ([], [], []) for v in grid}
    f0, f0m = [], []
    for r in recs:
        c, l, o, h = r["c"], r["l"], r["o"], r["h"]
        E, N = r["E"], r["N"]
        if not (E > 0 and N > 0) or len(c) <= H:
            continue
        f0.append(np.log(c[H] / E))
        f0m.append(month_of(cal, r["di"][0]))
        kmax = min(len(c) - 1 - H, KMAX_TOUCH)
        if kmax < 0:
            continue
        hp = np.maximum.accumulate(h[:kmax + 1])
        prevmax = np.concatenate([[-np.inf], hp[:-1]])
        live = prevmax < E + PROMO * N
        ap = N / E
        for v in grid:
            lvl = E - v * N if unit == "atr" else E * (1 - v / 100.0)
            hit = np.nonzero(live & (l[:kmax + 1] <= lvl))[0]
            if len(hit) == 0:
                continue
            k = int(hit[0])
            fill = lvl if k == 0 else min(float(o[k]), lvl)
            if fill <= 0:
                continue
            ev[v][0].append(np.log(c[k + H] / fill))
            ev[v][1].append(month_of(cal, r["di"][k]))
            ev[v][2].append(ap)
    return ev, np.array(f0), np.array(f0m)


def curve(ev, f0, mask_fn=None):
    out = {}
    for v, (y, g, ap) in ev.items():
        y, g, ap = np.array(y), np.array(g), np.array(ap)
        if mask_fn is not None and len(ap):
            m = mask_fn(ap)
            y, g = y[m], g[m]
        out[str(v)] = cl_stats(y, g, ref=f0)
    return out


def trail_events(recs, H, cal):
    ev = {v: ([], []) for v in YG}
    fa, fam = [], []
    for r in recs:
        c, l, o, h = r["c"], r["l"], r["o"], r["h"]
        E, N = r["E"], r["N"]
        if not (E > 0 and N > 0):
            continue
        kmax = min(len(c) - 1 - H, KMAX_TRAIL)
        if kmax < 1:
            continue
        a_ = np.nonzero(h[:kmax + 1] >= E + PROMO * N)[0]
        if len(a_) == 0:
            continue
        a = int(a_[0])
        fa.append(np.log(c[a + H] / c[a]))
        fam.append(month_of(cal, r["di"][a]))
        hp = np.maximum.accumulate(h[:kmax + 1])
        for v in YG:
            for k in range(a + 1, kmax + 1):
                lvl = hp[k - 1] - v * N
                if l[k] <= lvl:
                    fill = min(float(o[k]), lvl)
                    if fill > 0:
                        ev[v][0].append(np.log(c[k + H] / fill))
                        ev[v][1].append(month_of(cal, r["di"][k]))
                    break
    f0 = float(np.mean(fa)) if fa else 0.0
    return {str(v): cl_stats(np.array(y), np.array(g), ref=f0) for v, (y, g) in ev.items()}, f0, len(fa)


# ── M1 보유일 표 ────────────────────────────────────────────────────────────────
def held_rows(recs, cal, ist):
    cols = {k: [] for k in ("n", "u", "uN", "g", "y", "l10", "mon", "st", "dd", "r5", "vp", "kq")}
    for r in recs:
        if r["why"] in CENSOR:
            continue
        x = int(r["xti"])
        if x < 1:
            continue
        c, o, h, di = r["c"], r["o"], r["h"], r["di"]
        E, N, xp = r["E"], r["N"], r["xpx"]
        d = np.arange(0, x)
        o1 = o[d + 1].astype(float)
        good = o1 > 0
        d = d[good]
        o1 = o1[good]
        if len(d) == 0:
            continue
        mk = "kosdaq" if r["kq"] else "kospi"
        gd = di[d]
        hm = np.maximum.accumulate(h[:x].astype(float))[d]
        cols["n"].append(d)
        cols["u"].append(c[d] / E - 1)
        cols["uN"].append((c[d] - E) / N if N > 0 else np.full(len(d), np.nan))
        cols["g"].append((hm - c[d]) / N if N > 0 else np.full(len(d), np.nan))
        y = np.log(xp / o1)
        cols["y"].append(y)
        cols["l10"].append(xp / o1 - 1 <= -0.10)
        cols["mon"].append(np.array([month_of(cal, int(q)) for q in gd]))
        cols["st"].append(ist[mk]["state"][gd])
        cols["dd"].append(ist[mk]["dd20"][gd])
        cols["r5"].append(ist[mk]["r5"][gd])
        cols["vp"].append(ist[mk]["volp"][gd])
        cols["kq"].append(np.full(len(d), r["kq"]))
    return {k: np.concatenate(v) if v else np.array([]) for k, v in cols.items()}


def region(Hr, m):
    st = cl_stats(Hr["y"][m], Hr["mon"][m])
    st["L10"] = float(Hr["l10"][m].mean()) if m.any() else None
    return st


def binned(Hr, key, edges):
    out = []
    x = Hr[key]
    for a, b in zip(edges[:-1], edges[1:]):
        m = np.isfinite(x) & (x >= a) & (x < b)
        st = region(Hr, m)
        st["bin"] = [a, b]
        out.append(st)
    return out


# ── 해외 일반성 관문 ─────────────────────────────────────────────────────────────
def overseas_gate(theta, Hbar):
    spec = importlib.util.spec_from_file_location("dg", os.path.join(HERE, "..", "mu_datadriven_20261016", "diag.py"))
    sys_argv = sys.argv
    sys.argv = [sys_argv[0], os.path.join(SCR, "_unused.json")]
    DG = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(DG)
    sys.argv = sys_argv
    S = DG.load_all()
    end = pd.Timestamp("2012-12-31")
    ks = S["KOSPI"]
    ks = ks[(ks.index >= pd.Timestamp("1997-01-01")) & (ks.index <= end)]
    sig_k = pd.Series(np.diff(np.log(ks.to_numpy()), prepend=np.nan)).rolling(250, min_periods=250).std().to_numpy()
    sbar = float(np.nanmedian(sig_k))
    zth = theta / sbar
    res = {}
    for nm in ("KOSPI", "KOSDAQ", "SPX", "IXIC", "N225", "HSI", "HSCE", "SSE"):
        s = S[nm]
        s = s[s.index <= end]
        if nm in ("KOSPI", "KOSDAQ"):
            s = s[s.index >= pd.Timestamp("1997-01-01")]
        c = s.to_numpy(float)
        sg = pd.Series(np.diff(np.log(c), prepend=np.nan)).rolling(250, min_periods=250).std().to_numpy()
        mx = pd.Series(c).rolling(20, min_periods=20).max().to_numpy()
        dd = c / mx - 1
        n = len(c)
        k = np.arange(n)
        okk = (k + 1 + Hbar < n) & np.isfinite(sg) & np.isfinite(dd)
        fwd = np.full(n, np.nan)
        fwd[okk] = np.log(c[(k + 1 + Hbar)[okk]] / c[(k + 1)[okk]])
        ev = okk & (dd <= zth * sg)
        res[nm] = {"n_ev": int(ev.sum()), "cond": float(np.nanmean(fwd[ev])) if ev.any() else None,
                   "uncond": float(np.nanmean(fwd[okk])),
                   "worse": bool(ev.sum() >= 20 and np.nanmean(fwd[ev]) < np.nanmean(fwd[okk]))}
    nw = sum(1 for v in res.values() if v["worse"])
    return {"sigma_bar_kospi": sbar, "z_threshold": zth, "per_index": res, "n_worse": nw, "pass": nw >= 5}


def main():
    D = {}
    held = {}
    meta = {}
    for k in STR:
        P = load(k)
        cal = pd.DatetimeIndex(P["cal"])
        recs = P["recs"]
        ist = X.index_state(cal, os.path.join(SCR, "series.csv"))
        RT = [r for r in recs if r["win"] == "T"]
        hold = np.array([r["xti"] for r in RT if r["why"] not in CENSOR], float)
        H = int(np.clip(np.median(hold), 5, 40))
        meta[k] = {"H": H, "cur": P["cur"], "nT": len(RT), "nV": sum(r["win"] == "V" for r in recs),
                   "nH": sum(r["win"] == "H" for r in recs), "hold_med_T": float(np.median(hold))}
        out = {"Hbars": H}
        for wn in ("T", "V", "H"):
            R_ = [r for r in recs if r["win"] == wn]
            if not R_:
                continue
            evA, f0, f0m = touch_events(R_, H, cal, "atr")
            evP, _, _ = touch_events(R_, H, cal, "pct")
            f0v = float(f0.mean()) if len(f0) else 0.0
            w = {"f0": f0v, "n_entries": len(f0), "atr": curve(evA, f0v), "pct": curve(evP, f0v)}
            if wn == "T":
                apT = np.array([r["N"] / r["E"] for r in R_ if r["E"] > 0 and r["N"] > 0])
                q1, q2 = np.quantile(apT, [1 / 3, 2 / 3])
                terc = {}
                for nm, fn, lo, hi in (("lo", lambda a: a < q1, 0, q1), ("mid", lambda a: (a >= q1) & (a < q2), q1, q2),
                                       ("hi", lambda a: a >= q2, q2, 1)):
                    cv = curve(evA, f0v, fn)
                    terc[nm] = {"atr_pct_med": float(np.median(apT[fn(apT)])), "curve": cv, "z_star": first_point(ZG, cv)}
                w["terciles"] = terc
                w["tercile_edges"] = [float(q1), float(q2)]
            tr, fa, na = trail_events(R_, H, cal)
            w["trail"] = {"fA": fa, "n_armed": na, "curve": tr}
            Hr = held_rows(R_, cal, ist)
            if wn == "T":
                held[k] = Hr
            w["M1"] = {"n_days": int(len(Hr["y"])), "all": region(Hr, np.ones(len(Hr["y"]), bool)),
                       "by_n": binned(Hr, "n", [0, 3, 5, 10, 15, 20, 30, 40, 60, 120, 10 ** 6]),
                       "by_uN": binned(Hr, "uN", [-10, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3, 5, 100]),
                       "by_u": binned(Hr, "u", [-1, -0.10, -0.07, -0.05, -0.03, 0, 0.03, 0.05, 0.10, 0.20, 10]),
                       "by_g": binned(Hr, "g", [-1, 0.5, 1, 1.5, 2, 2.5, 3, 4, 100]),
                       "by_state": [dict(region(Hr, Hr["st"] == s), state=int(s)) for s in (0, 1, 2, 3)],
                       "by_dd20": binned(Hr, "dd", [-1, -0.15, -0.11, -0.09, -0.07, -0.05, -0.03, -0.01, 0.0001]),
                       "by_r5": binned(Hr, "r5", [-1, -0.08, -0.05, -0.03, -0.01, 0.01, 0.03, 1]),
                       "by_volp": binned(Hr, "vp", [0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.01]),
                       "stall": {str(n): region(Hr, (Hr["n"] >= n) & (Hr["u"] <= 0)) for n in NG},
                       "crash": {str(t): region(Hr, np.isfinite(Hr["dd"]) & (Hr["dd"] <= t)) for t in TH}}
            out[wn] = w
        D[k] = out
        print(k, "H", H, {w: meta[k][f"n{w}"] for w in ("T", "V", "H")}, flush=True)

    # ── 도출 ──────────────────────────────────────────────────────────────
    der = {}
    for k in STR:
        T = D[k]["T"]
        zs = first_point(ZG, T["atr"])
        xs = first_point(XG, T["pct"])
        tz = [T["terciles"][q]["z_star"] for q in ("lo", "mid", "hi")]
        unit = "불명"
        if all(v is not None for v in tz) and max(tz) - min(tz) <= 0.5:
            unit = "ATR"
        else:
            pe = [T["terciles"][q]["z_star"] * T["terciles"][q]["atr_pct_med"] * 100 if T["terciles"][q]["z_star"] is not None else None
                  for q in ("lo", "mid", "hi")]
            if all(v is not None for v in pe) and max(pe) - min(pe) <= 1.5:
                unit = "%"
        ys = first_point(YG, T["trail"]["curve"]) if k != "donchian" else None
        st = T["M1"]["stall"]
        ns = None
        for i, n in enumerate(NG):
            if all(ok_sig(st[str(m)]) for m in NG[i:]):
                ns = n
                break
        der[k] = {"z_star": zs, "x_star_pct": xs, "terc_z": tz, "unit": unit, "y_star": ys, "n_star": ns}
    # D-C 4전략 합침
    Hp = {c: np.concatenate([held[k][c] for k in STOCK]) for c in held["kojiro"]}
    cr = {str(t): region(Hp, np.isfinite(Hp["dd"]) & (Hp["dd"] <= t)) for t in TH}
    th = None
    for i, t in enumerate(TH):
        if all(ok_sig(cr[str(u)]) for u in TH[i:]):
            th = t
            break
    Hbar = int(np.median([D[k]["Hbars"] for k in STOCK]))
    gate = overseas_gate(th, Hbar) if th is not None else None
    theta = th if (th is not None and gate and gate["pass"]) else None
    pooled = {"crash": cr, "theta_raw": th, "Hbar": Hbar, "gate": gate, "theta": theta,
              "by_state": [dict(region(Hp, Hp["st"] == s), state=int(s)) for s in (0, 1, 2, 3)],
              "by_dd20": binned(Hp, "dd", [-1, -0.15, -0.11, -0.09, -0.07, -0.05, -0.03, -0.01, 0.0001])}
    json.dump({"meta": meta, "diag": D, "derived": der, "pooled": pooled}, open(os.path.join(HERE, "derived.json"), "w"),
              ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({"derived": der, "theta_raw": th, "gate": None if gate is None else {"n_worse": gate["n_worse"], "pass": gate["pass"]},
                      "theta": theta}, ensure_ascii=False, default=str))

    # ── 변형 명세 ──────────────────────────────────────────────────────────
    V = {}
    for k in STR:
        cur = meta[k]["cur"]
        d = der[k]
        wins = ["T", "V", "H"]
        comp = {}
        mir = {}
        z, u, x, y = d["z_star"], d["unit"], d["x_star_pct"], d["y_star"]
        if k == "kojiro":
            zc, yc = float(cur["stop_atr"]), float(cur["trail_atr"])
            s = {}
            if u == "ATR":
                s = {"stop_atr": z if z is not None else zc, "hard_stop_pct": -99.0}
            elif u == "%" and x is not None:
                s = {"stop_atr": 99.0, "hard_stop_pct": -float(x)}
            elif z is not None and z != zc:
                s = {"stop_atr": z}
            if s:
                comp["S"] = s
            if z is not None and z != zc:
                mir["stop_atr"] = max(0.25, 2 * zc - z)
            if y is not None and y != yc:
                comp["T"] = {"trail_atr": y}
                mir["trail_atr"] = max(0.25, 2 * yc - y)
        elif k == "donchian":
            zc = float(cur["r_atr"])
            s = {}
            if u == "ATR":
                s = {"r_atr": z if z is not None else zc, "r_floor": 0.04}
            elif u == "%" and x is not None:
                s = {"r_atr": 0.5, "r_floor": float(x) / 100.0}
            elif z is not None and z != zc:
                s = {"r_atr": z}
            if s:
                comp["S"] = s
            if z is not None and z != zc:
                mir["r_atr"] = max(0.5, 2 * zc - z)
        elif k in ("bfb", "vcp"):
            zc, yc = float(cur["stop_atr"]), float(cur["atr_trail_mult"])
            s = {}
            if u == "ATR":
                s = {"stop_atr": z if z is not None else zc, "turtle_min_stop_pct": 0.0, "turtle_backstop_pct": 0.0}
            elif u == "%" and x is not None:
                s = {"stop_atr": 0.0, "turtle_min_stop_pct": -float(x), "turtle_backstop_pct": -float(x)}
            elif z is not None and z != zc:
                s = {"stop_atr": z}
            if s:
                comp["S"] = s
            if z is not None and z != zc:
                mir["stop_atr"] = max(0.25, 2 * zc - z)
            if y is not None and y != yc:
                comp["T"] = {"atr_trail_mult": y}
                mir["atr_trail_mult"] = max(0.25, 2 * yc - y)
        else:
            zc, yc = 2.0, 1.8
            s = {}
            if u == "ATR":
                s = {"hard_atr": z if z is not None else zc, "hard_pct": None}
            elif u == "%" and x is not None:
                s = {"hard_atr": None, "hard_pct": float(x)}
            elif z is not None and z != zc:
                s = {"hard_atr": z}
            if s:
                comp["S"] = s
            if z is not None and z != zc:
                mir["hard_atr"] = max(0.25, 2 * zc - z)
            if y is not None and y != yc:
                comp["T"] = {"trail": y}
                mir["trail"] = max(0.25, 2 * yc - y)
        spec = {"V0": {"wins": wins}}
        ovr = {}
        for c in ("S", "T"):
            if c in comp:
                ovr.update(comp[c])
                spec[c] = {"wins": wins, "ovr": comp[c]}
        if theta is not None:
            spec["C"] = {"wins": wins, "crash": theta}
        if d["n_star"] is not None:
            spec["N"] = {"wins": wins, "stall": d["n_star"]}
        if ovr or theta is not None or d["n_star"] is not None:
            spec["DSTAR"] = {"wins": wins, "ovr": ovr or None, "crash": theta, "stall": d["n_star"]}
            if mir:
                spec["MIRROR"] = {"wins": wins, "ovr": mir, "crash": theta, "stall": d["n_star"]}
            if theta is not None:
                for sh in SHIFTS:
                    spec[f"DSTAR|plc{sh}"] = {"wins": ["T", "V"], "ovr": ovr or None, "crash": theta, "shift": sh,
                                              "stall": d["n_star"]}
        V[k] = spec
    json.dump(V, open(os.path.join(HERE, "variants.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: {n: {kk: vv for kk, vv in s.items() if kk != "wins"} for n, s in v.items() if "|" not in n}
                      for k, v in V.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
