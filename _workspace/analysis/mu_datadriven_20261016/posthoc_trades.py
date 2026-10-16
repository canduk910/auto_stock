"""사후 진단(동결 밖) — T(1997~2012) off 거래만으로 전략 쪽 조건부 손익 격자. 판정·도출에 쓰지 않는다(보고 전용)."""
import json, os, pickle, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); SCR = sys.argv[1]
sys.path.insert(0, HERE)
import dmvar
STR = ("kojiro", "donchian", "bfb", "vcp"); COST = 2 * 0.00014 + 0.002
Rs = {k: pickle.load(open(os.path.join(SCR, "md", f"{k}.pkl"), "rb")) for k in STR}
cal = pd.DatetimeIndex(Rs["kojiro"]["cal"]); ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)
T = pd.concat([Rs[k]["trades"]["T"].assign(strat=k) for k in STR], ignore_index=True)
T = T[T.gross.notna()].copy(); T["net"] = T.gross - COST; T["dm"] = T.net - T.groupby("strat").net.transform("mean")
mk = np.where(T.kq, "kosdaq", "kospi"); gd = T.gd.to_numpy()
def daymap(fn):
    out = {}
    for m in ("kospi", "kosdaq"):
        s = ser[m].dropna(); v = fn(s.to_numpy(float)); pos = s.index.searchsorted(cal, side="left") - 1
        out[m] = np.array([v[p] if p >= 0 and (cal[i] - s.index[p]).days <= 10 else np.nan for i, p in enumerate(pos)])
    return np.array([out[a][g] for a, g in zip(mk, gd)])
res = {"grid": {}}
dm = T.dm.to_numpy()
for L in (20, 40, 60, 90, 120, 200):
    pos = daymap(lambda c: np.log(c) - np.log(dmvar.sma(c, L)))
    for lb in (5, 10, 20, 40):
        def slp(c, L=L, lb=lb):
            s = dmvar.sma(c, L); a = np.full(len(c), np.nan); a[lb:] = np.log(s[lb:] / s[:-lb]); return a
        sl = daymap(slp); ok = np.isfinite(pos) & np.isfinite(sl)
        F = ok & (pos < 0) & (sl < 0); A = ok & (pos > 0) & (sl > 0)
        sd = dm[ok].std(ddof=1)
        res["grid"][f"{L}_{lb}"] = {"BF_dm": float(dm[F].mean()), "BF_share": float(F[ok].mean()), "AR_dm": float(dm[A].mean()),
                                    "gap_F_vs_rest": float(dm[F].mean() - dm[ok & ~F].mean()),
                                    "t_F": float(dm[F].mean() / (dm[F].std(ddof=1) / np.sqrt(F.sum())))}
dd20 = daymap(lambda c: np.log(c) - np.log(pd.Series(c).rolling(20, min_periods=20).max().to_numpy()))
ok = np.isfinite(dd20); x, y = dd20[ok], dm[ok]
qs = np.quantile(x, np.linspace(0, 1, 21)); idx = np.clip(np.searchsorted(qs, x, side="right") - 1, 0, 19)
res["dd20_bins"] = [{"med": float(np.median(x[idx == b])), "dm": float(y[idx == b].mean()), "n": int((idx == b).sum())} for b in range(20) if (idx == b).any()]
json.dump(res, open(os.path.join(HERE, "posthoc_trades_T.json"), "w"), indent=1)
for k, v in sorted(res["grid"].items(), key=lambda kv: kv[1]["gap_F_vs_rest"]):
    print(k, {a: round(b * 100, 2) if "dm" in a or "gap" in a or "share" in a else round(b, 1) for a, b in v.items()})
print([(round(b["med"] * 100, 1), round(b["dm"] * 100, 2)) for b in res["dd20_bins"]])
