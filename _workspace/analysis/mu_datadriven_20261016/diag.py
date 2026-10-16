"""지수 진단 + 파라미터 도출 (prereg §1~§4 E1~E6).

실행: /opt/anaconda3/envs/upbit-trader/bin/python diag.py <out.json> [end_year=2012] [set=all|kr]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KR = os.path.join(ROOT, "data", "archive", "krx_daily_long", "index")
GL = os.path.join(ROOT, "data", "archive", "global_long", "raw")
KR_SET = {"KOSPI": "krx_kospi.csv", "KOSDAQ": "krx_kosdaq.csv"}
FX_SET = {"SPX": "GSPC", "IXIC": "IXIC", "N225": "N225", "HSI": "HSI", "HSCE": "HSCE", "SSE": "000001.SS"}
EXTRA = {"K200": ("kr", "krx_kospi200.csv")}
LS = (20, 40, 60, 90, 120, 200)
LBS = (5, 10, 20, 40)
WS = (10, 20, 60)
H = 20
KR_START = pd.Timestamp("1997-01-01")


def yahoo(code):
    with open(os.path.join(GL, f"yahoo_{code}.json")) as f:
        r = json.load(f)["chart"]["result"][0]
    off = r["meta"].get("gmtoffset", 0)
    d = [datetime.fromtimestamp(t + off, tz=timezone.utc).date() for t in r["timestamp"]]
    s = pd.Series(r["indicators"]["quote"][0]["close"], index=pd.DatetimeIndex(d), dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s > 0]


def krx(fn):
    d = pd.read_csv(os.path.join(KR, fn)).dropna(subset=["close"])
    d["date"] = pd.to_datetime(d["date"])
    s = pd.Series(d.close.to_numpy(float), index=pd.DatetimeIndex(d.date)).sort_index()
    return s[~s.index.duplicated(keep="last")]


def load_all():
    out = {k: krx(v) for k, v in KR_SET.items()}
    out.update({k: yahoo(v) for k, v in FX_SET.items()})
    out["K200"] = krx("krx_kospi200.csv")
    return out


def sma(c, L):
    return pd.Series(c).rolling(L, min_periods=L).mean().to_numpy()


def volp(sig, hist=1000, mn=250):
    out = np.full(len(sig), np.nan)
    for k in range(len(sig)):
        if not np.isfinite(sig[k]):
            continue
        h = sig[max(0, k - hist):k]
        h = h[np.isfinite(h)]
        if len(h) < mn:
            continue
        out[k] = np.mean(h < sig[k])
    return out


def features(s):
    c = s.to_numpy(float)
    lc = np.log(c)
    r = np.diff(lc, prepend=np.nan)
    f = {"date": s.index, "c": c}
    sm = {L: sma(c, L) for L in LS}
    for L in LS:
        f[f"POS{L}"] = lc - np.log(sm[L])
        for lb in LBS:
            a = np.full(len(c), np.nan)
            a[lb:] = np.log(sm[L][lb:] / sm[L][:-lb])
            f[f"SLP{L}_{lb}"] = a
    s250 = pd.Series(r).rolling(250, min_periods=250).std(ddof=1).to_numpy()
    f["s250"] = s250
    for w in WS:
        mx = pd.Series(c).rolling(w, min_periods=w).max().to_numpy()
        f[f"DD{w}"] = lc - np.log(mx)
        f[f"zDD{w}"] = f[f"DD{w}"] / s250
    s20 = pd.Series(r).rolling(20, min_periods=20).std(ddof=1).to_numpy()
    f["VOLP"] = volp(s20)
    pm = np.full(len(c), np.nan)
    fr = np.full(len(c), np.nan)
    for k in range(len(c) - H):
        pm[k] = np.min(lc[k + 1:k + H + 1]) - lc[k]
        fr[k] = lc[k + H] - lc[k]
    f["PM20"], f["FR20"] = pm, fr
    return pd.DataFrame(f)


def sample(df, name, end_year, start=None):
    end = pd.Timestamp(f"{end_year}-12-31")
    st = start if start is not None else (KR_START if name in ("KOSPI", "KOSDAQ", "K200") else df.date.iloc[0])
    pos = np.arange(len(df))
    fut_ok = np.zeros(len(df), bool)
    dd = df.date.to_numpy()
    for k in range(len(df) - H):
        fut_ok[k] = dd[k + H] <= np.datetime64(end)
    need = [c for c in df.columns if c.startswith(("POS", "SLP", "zDD", "VOLP"))] + ["PM20"]
    ok = (df.date >= st).to_numpy() & fut_ok & np.all(np.isfinite(df[need].to_numpy(float)), axis=1)
    x = df[ok].copy()
    x["k"] = pos[ok]
    q10 = np.quantile(x.PM20, 0.10)
    x["tail"] = (x.PM20 <= q10).astype(float)
    return x, float(q10)


def J(flag, tail):
    t = tail > 0.5
    return float(flag[t].mean() - flag[~t].mean())


def changes_per_yr(flag, dates):
    yrs = max((dates.iloc[-1] - dates.iloc[0]).days, 1) / 365.25
    return float(np.sum(flag[1:] != flag[:-1]) / yrs)


def bins(x, y, nb=20):
    qs = np.quantile(x, np.linspace(0, 1, nb + 1))
    idx = np.clip(np.searchsorted(qs, x, side="right") - 1, 0, nb - 1)
    med, rate, cnt, lo, hi = [], [], [], [], []
    for b in range(nb):
        m = idx == b
        if m.sum() == 0:
            continue
        med.append(float(np.median(x[m]))); rate.append(float(y[m].mean())); cnt.append(int(m.sum()))
        lo.append(float(x[m].min())); hi.append(float(x[m].max()))
    return np.array(med), np.array(rate), np.array(cnt), np.array(lo), np.array(hi)


def spearman(a, b):
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def hinge(med, rate, cnt, up=False):
    best = None
    for th in med[2:-2]:
        h = np.maximum(med - th, 0) if up else np.maximum(th - med, 0)
        X = np.column_stack([np.ones_like(h), h])
        W = np.sqrt(cnt)
        coef, *_ = np.linalg.lstsq(X * W[:, None], rate * W, rcond=None)
        sse = float(np.sum(cnt * (rate - X @ coef) ** 2))
        if best is None or sse < best[0]:
            best = (sse, float(th), float(coef[1]))
    return {"theta": best[1], "beta": best[2], "valid": best[2] > 0}


def q25(v):
    return float(np.round(np.clip(v, 0, 1) * 4) / 4)


def derive(S, names):
    out = {"indices": names}
    # E1
    e1 = {}
    vars_ = [f"POS{L}" for L in LS] + [f"SLP{L}_{lb}" for L in LS for lb in LBS] + [f"zDD{w}" for w in WS] + ["VOLP"]
    for v in vars_:
        rhos = []
        for n in names:
            med, rate, cnt, _, _ = bins(S[n][v].to_numpy(), S[n]["tail"].to_numpy())
            rhos.append(spearman(med, rate))
        e1[v] = {"rho_med": float(np.median(rhos)), "neg_n": int(sum(r < 0 for r in rhos)), "rho": dict(zip(names, rhos))}
    out["E1"] = e1
    # E2
    grid = {}
    for L in LS:
        for lb in LBS:
            js, chs, per = [], [], {}
            for n in names:
                x = S[n]
                F = ((x[f"POS{L}"] < 0) & (x[f"SLP{L}_{lb}"] < 0)).to_numpy()
                j = J(F, x["tail"].to_numpy())
                js.append(j); chs.append(changes_per_yr(F, x.date)); per[n] = j
            grid[f"{L}_{lb}"] = {"L": L, "lb": lb, "medJ": float(np.median(js)), "chg": float(np.median(chs)), "J": per,
                                 "flag_share": float(np.median([((S[n][f"POS{L}"] < 0) & (S[n][f"SLP{L}_{lb}"] < 0)).mean() for n in names]))}
    mx = max(g["medJ"] for g in grid.values())
    plateau = [k for k, g in grid.items() if g["medJ"] >= 0.9 * mx]
    pick = min(plateau, key=lambda k: (grid[k]["chg"], -grid[k]["L"]))
    Ls, lbs = grid[pick]["L"], grid[pick]["lb"]
    own = {n: max(grid, key=lambda k: grid[k]["J"][n]) for n in names}
    out["E2"] = {"grid": grid, "max_medJ": mx, "plateau": plateau, "pick": pick, "L": Ls, "lb": lbs,
                 "own_argmax": own, "own_in_plateau": int(sum(own[n] in plateau for n in names))}
    # E3
    st = {}
    for nm, (a, r) in {"AR": (True, True), "AF": (True, False), "BR": (False, True), "BF": (False, False)}.items():
        lam, fr, sh = [], [], []
        for n in names:
            x = S[n]
            m = (((x[f"POS{Ls}"] > 0) == a) & ((x[f"SLP{Ls}_{lbs}"] > 0) == r)).to_numpy()
            if m.sum() < 30:
                continue
            lam.append(float(x["tail"].to_numpy()[m].mean() / 0.10)); fr.append(float(x.FR20.to_numpy()[m].mean())); sh.append(float(m.mean()))
        st[nm] = {"lambda": float(np.median(lam)), "m": q25(2 - float(np.median(lam))), "fr20_mean_med": float(np.median(fr)),
                  "share_med": float(np.median(sh)), "lambda_each": lam}
    out["E3"] = st
    # E4
    rr = {}
    for b in (0.005, 0.01, 0.015, 0.02, 0.03):
        lo_t = lo_n = hi_t = hi_n = 0.0
        for n in names:
            p, t = S[n][f"POS{Ls}"].to_numpy(), S[n]["tail"].to_numpy()
            ml, mh = (p > -b) & (p < 0), (p >= 0) & (p < b)
            lo_t += t[ml].sum(); lo_n += ml.sum(); hi_t += t[mh].sum(); hi_n += mh.sum()
        rr[str(b)] = {"RR": float((lo_t / lo_n) / (hi_t / hi_n)), "n_lo": int(lo_n), "n_hi": int(hi_n),
                      "tail_lo": float(lo_t / lo_n), "tail_hi": float(hi_t / hi_n)}
    bstar = 0.0
    for b in (0.005, 0.01, 0.015, 0.02, 0.03):
        if rr[str(b)]["RR"] < 1.2:
            bstar = b
        else:
            break
    out["E4"] = {"RR": rr, "b": bstar}
    # E5
    cand = {}
    for v in ("zDD10", "zDD20", "zDD60", "VOLP"):
        up = v == "VOLP"
        th = {}
        for n in names:
            med, rate, cnt, _, _ = bins(S[n][v].to_numpy(), S[n]["tail"].to_numpy())
            hz = hinge(med, rate, cnt, up=up)
            if hz["valid"]:
                th[n] = hz["theta"]
        if len(th) < 5:
            cand[v] = {"dropped": True, "theta_each": th}
            continue
        theta = float(np.median(list(th.values())))
        dj, lamo = {}, []
        for n in names:
            x = S[n]
            F = ((x[f"POS{Ls}"] < 0) & (x[f"SLP{Ls}_{lbs}"] < 0)).to_numpy()
            O = (x[v].to_numpy() >= theta) if up else (x[v].to_numpy() <= theta)
            t = x["tail"].to_numpy()
            dj[n] = J(F | O, t) - J(F, t)
            mm = O & ~F
            if mm.sum() >= 20:
                lamo.append(float(t[mm].mean() / 0.10))
        q1, q3 = np.percentile(list(th.values()), [25, 75])
        # 해제 경계 — 합산 곡선
        xs = np.concatenate([S[n][v].to_numpy() for n in names]); ts = np.concatenate([S[n]["tail"].to_numpy() for n in names])
        med, rate, cnt, lo, hi = bins(xs, ts)
        lift = rate / ts.mean()
        if up:
            order = [i for i in range(len(med) - 1, -1, -1) if hi[i] < theta]
            th_off = next((float(hi[i]) for i in order if lift[i] <= 1.25), float(np.min(lo)))
        else:
            order = [i for i in range(len(med)) if lo[i] > theta]
            th_off = next((float(lo[i]) for i in order if lift[i] <= 1.25), 0.0)
        cand[v] = {"theta": theta, "theta_each": th, "iqr_rel": float((q3 - q1) / abs(theta)) if theta else None,
                   "medDJ": float(np.median(list(dj.values()))), "pos_n": int(sum(d > 0 for d in dj.values())), "DJ": dj,
                   "lambda_O": float(np.median(lamo)) if lamo else None, "cap": q25(2 - float(np.median(lamo))) if lamo else None,
                   "theta_off": th_off, "pooled_curve": {"med": med.tolist(), "lift": lift.tolist(), "lo": lo.tolist(), "hi": hi.tolist()}}
    ok = [v for v, c in cand.items() if not c.get("dropped") and c["medDJ"] >= 0.02 and c["pos_n"] >= 6]
    pick5 = max(ok, key=lambda v: cand[v]["medDJ"]) if ok else None
    out["E5"] = {"cand": cand, "pick": pick5}
    out["rule"] = {"L": Ls, "lb": lbs, "table": {k: st[k]["m"] for k in st}, "band": bstar,
                   "overlay": None if pick5 is None else {"var": pick5, "theta": cand[pick5]["theta"], "theta_off": cand[pick5]["theta_off"],
                                                          "cap": cand[pick5]["cap"]}}
    return out


def pooled_curves(S, names, vs=("POS60", "POS120", "zDD20", "zDD10", "VOLP", "SLP60_20")):
    out = {}
    for v in vs:
        xs = np.concatenate([S[n][v].to_numpy() for n in names]); ts = np.concatenate([S[n]["tail"].to_numpy() for n in names])
        fr = np.concatenate([S[n].FR20.to_numpy() for n in names])
        med, rate, cnt, lo, hi = bins(xs, ts)
        _, frm, _, _, _ = bins(xs, fr)
        out[v] = {"med": med.tolist(), "lift": (rate / ts.mean()).tolist(), "fr20": frm.tolist(), "lo": lo.tolist(), "hi": hi.tolist()}
    return out


def main():
    outp = sys.argv[1]
    end_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2012
    which = sys.argv[3] if len(sys.argv) > 3 else "all"
    raw = load_all()
    F = {n: features(s) for n, s in raw.items()}
    names = ["KOSPI", "KOSDAQ"] + ([] if which == "kr" else list(FX_SET))
    S, q = {}, {}
    for n in names + ["K200"]:
        S[n], q[n] = sample(F[n], n, end_year)
    res = derive(S, names)
    res["q10"] = q
    res["n_days"] = {n: int(len(S[n])) for n in S}
    res["span"] = {n: [str(S[n].date.iloc[0].date()), str(S[n].date.iloc[-1].date())] for n in S}
    if which == "all" and end_year == 2012:
        res["pooled"] = pooled_curves(S, names)
        # 해외 2013~ 표본 밖: 도출 규칙의 4상태 위험 배수(부호 확인)
        oos = {}
        L, lb = res["rule"]["L"], res["rule"]["lb"]
        for n in list(FX_SET) + ["KOSPI", "KOSDAQ"]:
            df = F[n]
            x = df[(df.date >= "2013-01-01")].copy()
            x = x[np.isfinite(x.PM20) & np.isfinite(x[f"SLP{L}_{lb}"])]
            x["tail"] = (x.PM20 <= q[n]).astype(float)
            row = {"base": float(x["tail"].mean())}
            for nm, (a, r) in {"AR": (True, True), "AF": (True, False), "BR": (False, True), "BF": (False, False)}.items():
                m = ((x[f"POS{L}"] > 0) == a) & ((x[f"SLP{L}_{lb}"] > 0) == r)
                row[nm] = float(x["tail"][m].mean() / max(x["tail"].mean(), 1e-9)) if m.sum() >= 20 else None
            ov = res["rule"]["overlay"]
            if ov:
                v = ov["var"]
                m = (x[v] >= ov["theta"]) if v == "VOLP" else (x[v] <= ov["theta"])
                row["overlay"] = float(x["tail"][m].mean() / max(x["tail"].mean(), 1e-9)) if m.sum() >= 20 else None
                row["overlay_n"] = int(m.sum())
            oos[n] = row
        res["oos_2013"] = oos
    with open(outp, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
    print(json.dumps(res["rule"], ensure_ascii=False))
    print("E2 pick", res["E2"]["pick"], "max", round(res["E2"]["max_medJ"], 4), "plateau", res["E2"]["plateau"], "own_in", res["E2"]["own_in_plateau"])
    print("E4", {k: round(v["RR"], 3) for k, v in res["E4"]["RR"].items()})
    for v, c in res["E5"]["cand"].items():
        if not c.get("dropped"):
            print("E5", v, "theta", round(c["theta"], 3), "iqr", round(c["iqr_rel"], 2), "medDJ", round(c["medDJ"], 4), "pos", c["pos_n"],
                  "lamO", c["lambda_O"], "off", round(c["theta_off"], 3))
        else:
            print("E5", v, "dropped", c["theta_each"])
    for k, s in res["E3"].items():
        print("E3", k, round(s["lambda"], 3), s["m"], round(s["share_med"], 3))


if __name__ == "__main__":
    main()
