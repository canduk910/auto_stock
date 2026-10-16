"""씨앗별 자산곡선 → 위험 지표 · 비용 · 위약 · 판정 (prereg §2~§6).

실행: /opt/anaconda3/envs/upbit-trader/bin/python analyze.py <scratch>
출력: summary.json (이 폴더)
"""
from __future__ import annotations

import json
import math
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = sys.argv[1]
S0 = 4_707_820.0
PREV = os.path.join(HERE, "..", "rerun_cost_mu_20261016")
STRATS = {"kojiro": "kojiro", "donchian": "donchian", "bfb": "bfb", "vcp": "vcp", "etf": "etf"}
WEIGHTS = {"kojiro": 0.25, "donchian": 0.25, "bfb": 0.20, "vcp": 0.20}
SHIFTS = (126, 252, 378, 504, 756, 1008, 1260, 1512)
EPIS = {"1997": ("1997-06-01", "1998-06-30"), "2000": ("2000-01-01", "2000-12-31"), "2008": ("2007-11-01", "2008-10-31"),
        "2011": ("2011-07-25", "2011-09-30"), "2018": ("2018-01-29", "2018-10-31"), "2020": ("2020-01-20", "2020-03-31"),
        "2022": ("2021-07-01", "2022-09-30")}
RKEYS = ("R1_mdd", "R2_worst20", "R3_es5", "R4_crash")

ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)
KS = ser["kospi"].dropna()
k20 = KS / KS.shift(20) - 1.0
crash_mark = pd.Series(False, index=KS.index)
idx = np.nonzero((k20 <= -0.10).to_numpy())[0]
for i in idx:
    crash_mark.iloc[max(0, i - 19):i + 1] = True
CRASH_DATES = set(crash_mark.index[crash_mark.to_numpy()])


def path(eq):
    return np.concatenate([[S0], eq])


def metrics(c):
    d = pd.DatetimeIndex(c["dates"])
    eq = c["eq"]
    x = path(eq)
    r = x[1:] / x[:-1] - 1.0
    pk = np.maximum.accumulate(x)
    dd = x / pk - 1.0
    yrs = max((d[-1] - d[0]).days, 1) / 365.25
    out = {"R1_mdd": float(dd.min())}
    out["R2_worst20"] = float((x[20:] / x[:-20] - 1.0).min()) if len(x) > 20 else float("nan")
    n5 = max(1, int(math.ceil(0.05 * len(r))))
    out["R3_es5"] = float(np.sort(r)[:n5].mean())
    cm = np.array([dt in CRASH_DATES for dt in d])
    out["R4_crash"] = float(np.prod(1.0 + r[cm]) - 1.0) if cm.any() else float("nan")
    out["crash_days"] = int(cm.sum())
    me = pd.Series(eq, index=d).groupby(d.to_period("M")).last()
    mr = me / me.shift(1).fillna(S0) - 1.0
    out["worst_month"] = float(mr.min())
    cagr = (eq[-1] / S0) ** (1.0 / yrs) - 1.0
    out["cagr"] = float(cagr)
    out["calmar"] = float(cagr / abs(out["R1_mdd"])) if out["R1_mdd"] < 0 else float("nan")
    # 회복
    spells, i, n = [], 0, len(x)
    while i < n:
        if dd[i] < 0:
            j = i
            while j < n and dd[j] < 0:
                j += 1
            spells.append((j - i + 1, float(dd[i - 1:j].min()), j >= n))   # 고점 날(i−1)부터 신고점 날(j)까지
            i = j
        else:
            i += 1
    if spells:
        L = max(spells, key=lambda s: s[0])
        out["uw_longest"] = int(L[0])
        out["uw_longest_censored"] = bool(L[2])
    else:
        out["uw_longest"], out["uw_longest_censored"] = 0, False
    deep = [s[0] for s in spells if s[1] <= -0.10]
    out["uw_deep_median"] = float(np.median(deep)) if deep else 0.0
    out["share_below20"] = float(np.mean(dd[1:] <= -0.20))
    # 노출
    out["inv_mean"] = float(np.mean(c["inv"]))
    out["days_in_mkt"] = float(np.mean(c["npos"] > 0))
    alr = math.log(max(eq[-1], 1.0) / S0) / yrs
    out["ann_logret"] = float(alr)
    out["ret_per_exposure"] = float(alr / out["inv_mean"]) if out["inv_mean"] > 0 else float("nan")
    return out


def med(vals):
    v = [x for x in vals if x == x]
    return float(np.median(v)) if v else float("nan")


def summarize(curves):
    ms = [metrics(c) for c in curves]
    keys = ms[0].keys()
    return {k: med([m[k] for m in ms]) if not isinstance(ms[0][k], bool) else float(np.mean([m[k] for m in ms]))
            for k in keys}, ms


def paired(ms_on, ms_off, k):
    a = [(x[k], y[k]) for x, y in zip(ms_on, ms_off)]
    if all(not (p == p) or not (q == q) for p, q in a):
        return None
    return int(sum(1 for p, q in a if p == p and q == q and p > q))


def mval(v):
    return 1.0 if (v is None or not np.isfinite(v)) else float(v)


def out_mask(R, kind):
    mk = np.array([mval(v) for v in R["m"]["kospi"]])
    if kind == "etf":
        return mk <= 0
    mq = np.array([mval(v) for v in R["m"]["kosdaq"]])
    return (mk <= 0) | (mq <= 0)


def spells_cost(R, kind, curves_on, curves_off, win_dates):
    """빠짐 구간별 on−off 누적 차 · 시장 반등(KOSPI)."""
    cal = pd.DatetimeIndex(R["cal"])
    om = out_mask(R, kind)
    d0, d1 = pd.Timestamp(win_dates[0]), pd.Timestamp(win_dates[-1])
    sp, i = [], 0
    while i < len(cal):
        if om[i]:
            j = i
            while j < len(cal) and om[j]:
                j += 1
            if d0 <= cal[i] <= d1:
                sp.append((i, j))          # j = 재개일 인덱스(없으면 len)
            i = j
        else:
            i += 1
    dpos = {d: k for k, d in enumerate(pd.DatetimeIndex(win_dates))}
    rows, B, K = [], [], []
    for sd in range(len(curves_on)):
        xo, xf = path(curves_on[sd]["eq"]), path(curves_off[sd]["eq"])
        b = k = 0.0
        for (i, j) in sp:
            a = dpos.get(cal[i])
            e_idx = min(j + 20, len(cal) - 1)
            e_d = min(cal[e_idx], d1)
            e = dpos.get(e_d)
            if a is None or e is None:
                continue
            ro = xo[e + 1] / xo[a] - 1.0
            rf = xf[e + 1] / xf[a] - 1.0
            dlt = ro - rf
            b += max(dlt, 0.0)
            k += max(-dlt, 0.0)
            if sd == 0:
                rows.append({"start": str(cal[i].date()), "resume": str(cal[j].date()) if j < len(cal) else None,
                             "days_out": int(j - i), "delta_seed0": float(dlt)})
        B.append(b)
        K.append(k)
    # 시장 쪽(시드 무관)
    for row in rows:
        s, rsm = pd.Timestamp(row["start"]), row["resume"]
        if rsm is None:
            continue
        seg = KS[(KS.index >= s) & (KS.index < pd.Timestamp(rsm))]
        if len(seg) == 0:
            continue
        p_res = KS[KS.index >= pd.Timestamp(rsm)]
        if len(p_res) == 0:
            continue
        row["kospi_trough_to_resume"] = float(p_res.iloc[0] / seg.min() - 1.0)
        row["kospi_during_out"] = float(p_res.iloc[0] / KS[KS.index < s].iloc[-1] - 1.0) if (KS.index < s).any() else None
        row["kospi_resume_20d"] = float(p_res.iloc[min(20, len(p_res) - 1)] / p_res.iloc[0] - 1.0)
    return {"n_spells": len(sp), "B_med": med(B), "K_med": med(K), "B_minus_K_med": med([b - k for b, k in zip(B, K)]),
            "spells": rows}


def episodes(R, kind, curves, win_dates):
    cal = pd.DatetimeIndex(R["cal"])
    mk = np.array([mval(v) for v in R["m"]["kospi"]])
    mq = np.array([mval(v) for v in R["m"]["kosdaq"]]) if "kosdaq" in R["m"] else None
    wd = pd.DatetimeIndex(win_dates)
    out = {}
    for nm, (a, b) in EPIS.items():
        seg = KS[(KS.index >= pd.Timestamp(a)) & (KS.index <= pd.Timestamp(b))]
        if len(seg) == 0:
            continue
        pkd = seg.idxmax()
        trd = seg[seg.index >= pkd].idxmin()
        if not (wd[0] <= pkd and trd <= wd[-1]):
            continue
        ia, ib = wd.searchsorted(pkd), wd.searchsorted(trd)
        rets = [float(path(c["eq"])[ib + 1] / path(c["eq"])[ia + 1] - 1.0) for c in curves]
        ci = (cal >= pkd) & (cal <= trd)
        out[nm] = {"peak": str(pkd.date()), "trough": str(trd.date()), "kospi": float(seg[trd] / seg[pkd] - 1.0),
                   "acct_med": med(rets), "m0_kospi": float(np.mean(mk[ci] <= 0)),
                   "m0_kosdaq": float(np.mean(mq[ci] <= 0)) if mq is not None else None}
    return out


def evaluate(name, R, kind, prev=None):
    C = R["curves"]
    res = {"repro": {}, "win": {}}
    if prev is not None:
        for (vn, wn), bk in R["book"].items():
            if vn in ("on", "off"):
                pv = prev[vn][wn]["book_NEW"]
                res["repro"][f"{vn}{wn}"] = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
    for wn in ("T", "V", "H"):
        if ("on", wn) not in C:
            continue
        so, mo = summarize(C[("on", wn)])
        sf, mf = summarize(C[("off", wn)])
        W = {"on": so, "off": sf, "improved": {}, "seeds_on_better": {}}
        for k in RKEYS:
            pc = paired(mo, mf, k)
            W["seeds_on_better"][k] = pc
            ok = (so[k] == so[k] and sf[k] == sf[k] and so[k] > sf[k] and pc is not None and pc >= 10)
            W["improved"][k] = bool(ok)
        W["k"] = int(sum(W["improved"].values()))
        wd = C[("on", wn)][0]["dates"]
        W["cost"] = spells_cost(R, kind, C[("on", wn)], C[("off", wn)], wd)
        W["c"] = bool(W["cost"]["K_med"] < W["cost"]["B_med"])
        W["episodes"] = {"on": episodes(R, kind, C[("on", wn)], wd), "off": episodes(R, kind, C[("off", wn)], wd)}
        if ("plc126", wn) in C:
            pl = {}
            for sh in SHIFTS:
                sp, _ = summarize(C[(f"plc{sh}", wn)])
                pl[sh] = {k: sp[k] for k in RKEYS + ("cagr", "inv_mean", "days_in_mkt")}
            W["placebo"] = pl
            W["timing"] = {k: int(sum(1 for sh in SHIFTS if so[k] > pl[sh][k])) for k in ("R1_mdd", "R4_crash")}
            W["timing_ok"] = bool(all(v >= 6 for v in W["timing"].values()))
        res["win"][wn] = W
    T, V = res["win"]["T"], res["win"]["V"]
    if T["k"] >= 3 and V["k"] >= 3 and T["c"] and V["c"]:
        lab = "위험 회피 가치 있음"
    elif T["k"] <= 1 and V["k"] <= 1:
        lab = "위험 회피 가치 없음"
    else:
        lab = "혼재"
    tt = (T.get("timing_ok"), V.get("timing_ok"))
    tag = "타이밍 효과 확인" if all(tt) else ("타이밍 효과 없음(덜 거래한 효과)" if not any(tt) else "타이밍 효과 부분")
    H = res["win"].get("H")
    hrev = bool(H and H["on"]["R1_mdd"] < H["off"]["R1_mdd"] and
                (H["on"]["R4_crash"] < H["off"]["R4_crash"] if H["on"]["R4_crash"] == H["on"]["R4_crash"] else False))
    if lab == "위험 회피 가치 있음":
        conf = "높음" if all(tt) else "중간"
    elif lab == "혼재" and ((T["k"] >= 3 and T["c"]) or (V["k"] >= 3 and V["c"])):
        conf = "중간"
    else:
        conf = "낮음"
    res["label"] = lab + (" (H 반전)" if hrev else "")
    res["timing_tag"] = tag
    res["confidence"] = conf
    return res


def combine(Rs, vn, wn):
    w = {k: WEIGHTS[k] / sum(WEIGHTS.values()) for k in WEIGHTS}
    cs = {k: Rs[k]["curves"][(vn, wn)] for k in w}
    common = None
    for k in w:
        d = pd.DatetimeIndex(cs[k][0]["dates"])
        common = d if common is None else common.intersection(d)
    out = []
    for sd in range(len(cs["kojiro"])):
        r = np.zeros(len(common))
        inv = np.zeros(len(common))
        npos = np.zeros(len(common))
        for k, wk in w.items():
            c = cs[k][sd]
            d = pd.DatetimeIndex(c["dates"])
            x = pd.Series(path(c["eq"])[1:], index=d)
            xp = x.shift(1)
            xp.iloc[0] = S0
            rr = (x / xp - 1.0).reindex(common).fillna(0.0).to_numpy()
            r += wk * rr
            inv += wk * pd.Series(c["inv"], index=d).reindex(common).fillna(0.0).to_numpy()
            npos += pd.Series(c["npos"], index=d).reindex(common).fillna(0).to_numpy()
        out.append({"dates": np.asarray(common), "eq": S0 * np.cumprod(1.0 + r), "inv": inv, "npos": npos})
    return out


def main():
    Rs, res = {}, {}
    for k, f in STRATS.items():
        p = os.path.join(SCR, "mr", f + ".pkl")
        if not os.path.exists(p):
            print("missing", k)
            continue
        with open(p, "rb") as fh:
            Rs[k] = pickle.load(fh)
        prev = json.load(open(os.path.join(PREV, f"result_{f}.json")))
        res[k] = evaluate(k, Rs[k], k, prev)
        print(k, res[k]["label"], res[k]["timing_tag"], res[k]["confidence"], "repro max", max(res[k]["repro"].values()))
    if all(k in Rs for k in WEIGHTS):
        RC = {"cal": Rs["kojiro"]["cal"], "m": Rs["kojiro"]["m"], "book": {}, "curves": {}}
        for (vn, wn) in Rs["kojiro"]["curves"]:
            if all((vn, wn) in Rs[k]["curves"] for k in WEIGHTS):
                RC["curves"][(vn, wn)] = combine(Rs, vn, wn)
        res["book4"] = evaluate("book4", RC, "book4", None)
        print("book4", res["book4"]["label"], res["book4"]["timing_tag"], res["book4"]["confidence"])
    with open(os.path.join(HERE, "summary.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))


if __name__ == "__main__":
    main()
