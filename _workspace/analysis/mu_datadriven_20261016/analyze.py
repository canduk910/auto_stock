"""검증 판정 (prereg §5) · 보유분 몫 (§6) · 전략 쪽 조건부 손익 (§3 Y_trade · E3 점검).

실행: /opt/anaconda3/envs/upbit-trader/bin/python analyze.py <scratch>
판정 함수는 앞 변형 비교 analyze.py(→ 앞 재측정 analyze.py)를 그대로 불러 쓴다.
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
spec = importlib.util.spec_from_file_location("VA", os.path.join(HERE, "..", "mu_variants_20261016", "analyze.py"))
VA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VA)
sys.argv = _argv
A0 = VA.A0
STR = ("kojiro", "donchian", "bfb", "vcp")
NAMES = ("V0", "DS", "DKR", "ORC")
COST_RT = 2 * 0.00014 + 0.002
sys.path.insert(0, HERE)
import dmvar  # noqa: E402


def load():
    Rs = {}
    for k in STR:
        with open(os.path.join(SCR, "md", f"{k}.pkl"), "rb") as fh:
            Rs[k] = pickle.load(fh)
    return Rs


def holdings_share(ev):
    out = {}
    for wn in ("T", "V", "H"):
        W = ev[wn]
        off, orc = W["off"]["R4_crash"], W["ORC"]["R4_crash"]
        span = orc - off
        row = {"R4_off": off, "R4_ORC": orc, "max_avoidable_share": span / abs(off) if off else None,
               "unavoidable_share": (-orc) / abs(off) if off else None}
        for nm in ("V0", "DS", "DKR"):
            row[f"captured_{nm}"] = (W[nm]["R4_crash"] - off) / span if span else None
        out[wn] = row
    return out


def states(cal, ser, L, lb):
    """날 D 의 상태 = D 보다 앞선 마지막 봉 기준 (위/아래, 상승/하락) — 띠 없음(E3 정의)."""
    out = {}
    for mk in ("kospi", "kosdaq"):
        s = ser[mk].dropna()
        c = s.to_numpy(float)
        sm = dmvar.sma(c, L)
        lab = np.full(len(c), "", dtype=object)
        for k in range(L + lb - 1, len(c)):
            lab[k] = ("A" if c[k] > sm[k] else "B") + ("R" if sm[k] > sm[k - lb] else "F")
        bd = s.index
        pos = bd.searchsorted(cal, side="left") - 1
        out[mk] = np.array([lab[p] if p >= 0 and (cal[i] - bd[p]).days <= 10 else "" for i, p in enumerate(pos)], dtype=object)
    return out


def feat_days(cal, ser, fn):
    out = {}
    for mk in ("kospi", "kosdaq"):
        s = ser[mk].dropna()
        v = fn(s.to_numpy(float))
        bd = s.index
        pos = bd.searchsorted(cal, side="left") - 1
        out[mk] = np.array([v[p] if p >= 0 and (cal[i] - bd[p]).days <= 10 else np.nan for i, p in enumerate(pos)])
    return out


def trade_table(Rs, wn, cal, ser):
    rows = []
    for k in STR:
        t = Rs[k]["trades"][wn].copy()
        t = t[t.gross.notna()]
        t["net"] = t.gross - COST_RT
        t["strat"] = k
        rows.append(t)
    T = pd.concat(rows, ignore_index=True)
    T["dm"] = T.net - T.groupby("strat").net.transform("mean")
    mk = np.where(T.kq, "kosdaq", "kospi")
    for tag, (L, lb) in {"s200": (200, 40), "s60": (60, 20)}.items():
        st = states(cal, ser, L, lb)
        T[tag] = [st[m][g] for m, g in zip(mk, T.gd)]
    pos60 = feat_days(cal, ser, lambda c: np.log(c) - np.log(dmvar.sma(c, 60)))
    dd20 = feat_days(cal, ser, lambda c: np.log(c) - np.log(pd.Series(c).rolling(20, min_periods=20).max().to_numpy()))
    T["pos60"] = [pos60[m][g] for m, g in zip(mk, T.gd)]
    T["dd20"] = [dd20[m][g] for m, g in zip(mk, T.gd)]
    return T


def grp(T, col):
    out = {}
    for key, g in T.groupby(col):
        if key == "" or len(g) < 30:
            continue
        sd = g.dm.std(ddof=1)
        out[str(key)] = {"n": int(len(g)), "dm_mean": float(g.dm.mean()), "t": float(g.dm.mean() / (sd / np.sqrt(len(g)))),
                         "net_mean": float(g.net.mean()), "loss10": float(np.mean(g.net <= -0.10)),
                         "by_strat": {s: float(x.dm.mean()) for s, x in g.groupby("strat")}}
    return out


def binned(T, col, edges):
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        g = T[(T[col] > a) & (T[col] <= b)]
        if len(g) < 30:
            continue
        sd = g.dm.std(ddof=1)
        out.append({"lo": a, "hi": b, "n": int(len(g)), "dm_mean": float(g.dm.mean()),
                    "t": float(g.dm.mean() / (sd / np.sqrt(len(g)))), "loss10": float(np.mean(g.net <= -0.10))})
    return out


def acct_forward(RC, wn, cal, ser):
    """off 계좌 묶음 이후 20영업일 수익(씨앗 평균) × 상태(KOSPI 기준)."""
    cs = RC["curves"][("off", wn)]
    d = pd.DatetimeIndex(cs[0]["dates"])
    eq = np.mean([np.log(c["eq"]) for c in cs], axis=0)
    f20 = np.full(len(eq), np.nan)
    f20[:-20] = eq[20:] - eq[:-20]
    calx = pd.DatetimeIndex(cal)
    out = {}
    for tag, (L, lb) in {"s200": (200, 40), "s60": (60, 20)}.items():
        st = states(calx, ser, L, lb)["kospi"]
        sd = pd.Series(st, index=calx).reindex(d).to_numpy()
        out[tag] = {s: {"n": int(np.sum((sd == s) & np.isfinite(f20))), "f20_mean": float(np.nanmean(f20[sd == s]))}
                    for s in ("AR", "AF", "BR", "BF") if np.sum(sd == s) > 20}
    return out


def main():
    Rs = load()
    ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)
    cal = pd.DatetimeIndex(Rs["kojiro"]["cal"])
    RC = VA.book4(Rs)
    out = {}
    ev = VA.evaluate_target(RC, "book4", list(NAMES))
    out["book4"] = {"eval": ev, "judge": {n: VA.judge(ev, n) for n in ("DS", "DKR")}, "holdings": holdings_share(ev)}
    for k in STR:
        e = VA.evaluate_target(Rs[k], k, list(NAMES))
        out[k] = {"eval": e, "judge": {n: VA.judge(e, n) for n in ("DS", "DKR")}, "holdings": holdings_share(e)}
    tr = {}
    for wn in ("T", "V", "H"):
        T = trade_table(Rs, wn, cal, ser)
        tr[wn] = {"n": int(len(T)), "s200": grp(T, "s200"), "s60": grp(T, "s60"),
                  "pos60": binned(T, "pos60", [-1, -0.10, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 1]),
                  "dd20": binned(T, "dd20", [-1, -0.15, -0.10, -0.07, -0.05, -0.03, -0.01, 1e-9])}
    out["trades"] = tr
    out["acct_forward"] = {wn: acct_forward(RC, wn, cal, ser) for wn in ("T", "V", "H")}
    # m 계열 요약(시장 쪽): 빠짐 비율·변경 횟수
    for nm in NAMES:
        out.setdefault("m_profile", {})[nm] = {wn: VA.flicker_market(cal, RC["m"][nm], RC["curves"][("V0", wn)][0]["dates"])
                                               for wn in ("T", "V", "H")}
    with open(os.path.join(HERE, "summary.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    for n in ("DS", "DKR"):
        print(n, out["book4"]["judge"][n])
    print(json.dumps(out["book4"]["holdings"], ensure_ascii=False))


if __name__ == "__main__":
    main()
