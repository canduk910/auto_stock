"""prereg §2.3·§2.4·§3 — 칸별 결과, 주 군집 부트스트랩, 판정 C1~C5."""
import json
from pathlib import Path
import numpy as np, pandas as pd

OUT = Path(__file__).resolve().parent
RNG = np.random.default_rng(20261013); B = 2000
T = pd.read_parquet(OUT / "trades.parquet")
S = pd.read_csv(OUT / "mu_series.csv", parse_dates=["date"]).set_index("date")
T = T.join(S[["m_kp_idx", "m_kq_idx", "m_kp_etf", "m_kq_etf"]], on="entry_dd")
T["wk"] = T.entry_dd.dt.strftime("%G-%V")
T["size"] = np.where(T.market == "KOSPI", np.where(T.kp_rank <= 200, "large", "small"), np.where(T.kq_rank <= 150, "large", "small"))


def cell(kp, kq):
    return np.select([(kp > 0) & (kq > 0), (kp == 0) & (kq > 0), (kp > 0) & (kq == 0), (kp == 0) & (kq == 0)], ["QQ", "K0Q+", "K+Q0", "00"], default="NA")


def boot_diff(df, maskA, maskB, col="ret"):
    """평균(A) − 평균(B), 주 군집 부트스트랩 90%."""
    wk = pd.Categorical(df.wk); W = len(wk.categories); code = wk.codes
    def agg(m):
        s = np.bincount(code[m], weights=df[col].values[m], minlength=W); n = np.bincount(code[m], minlength=W); return s, n
    sa, na = agg(maskA.values); sb, nb = agg(maskB.values)
    pt = sa.sum() / max(na.sum(), 1) - sb.sum() / max(nb.sum(), 1)
    idx = RNG.integers(0, W, size=(B, W))
    A = sa[idx].sum(1) / np.maximum(na[idx].sum(1), 1); Bm = sb[idx].sum(1) / np.maximum(nb[idx].sum(1), 1)
    dd = A - Bm
    return {"diff": round(float(pt) * 100, 3), "lo90": round(float(np.percentile(dd, 5)) * 100, 3), "hi90": round(float(np.percentile(dd, 95)) * 100, 3),
            "nA": int(na.sum()), "nB": int(nb.sum())}


def boot_mean(df, mask, col="ret"):
    wk = pd.Categorical(df.wk); W = len(wk.categories); code = wk.codes; m = mask.values
    s = np.bincount(code[m], weights=df[col].values[m], minlength=W); n = np.bincount(code[m], minlength=W)
    idx = RNG.integers(0, W, size=(B, W)); mm = s[idx].sum(1) / np.maximum(n[idx].sum(1), 1)
    return [round(float(np.percentile(mm, 5)) * 100, 3), round(float(np.percentile(mm, 95)) * 100, 3)]


def table(df):
    out = {}
    for c in ["QQ", "K0Q+", "K+Q0", "00"]:
        x = df[df.cell == c]
        if len(x) == 0:
            out[c] = {"n": 0}; continue
        out[c] = {"n": len(x), "mean": round(x.ret.mean() * 100, 3), "ci90": boot_mean(df, df.cell == c), "median": round(x.ret.median() * 100, 3),
                  "win": round((x.ret > 0).mean(), 3), "R": round(x.R.mean(), 3), "weeks": int(x.wk.nunique())}
    return out


def block(df, kpcol, kqcol, label):
    df = df.dropna(subset=[kpcol, kqcol]).copy()
    df["cell"] = cell(df[kpcol], df[kqcol])
    res = {"label": label, "n": len(df), "from": str(df.entry_dd.min().date()), "to": str(df.entry_dd.max().date())}
    for mk in ["KOSDAQ", "KOSPI"]:
        x = df[df.market == mk]
        r = {"cells": table(x)}
        r["K0Q+_minus_00"] = boot_diff(x, x.cell == "K0Q+", x.cell == "00")
        r["K+Q0_minus_QQ"] = boot_diff(x, x.cell == "K+Q0", x.cell == "QQ")
        r["K0Q+_minus_QQ"] = boot_diff(x, x.cell == "K0Q+", x.cell == "QQ")
        r["K+Q0_minus_00"] = boot_diff(x, x.cell == "K+Q0", x.cell == "00")
        r["split_by_kq"] = boot_diff(x, x[kqcol] > 0, x[kqcol] == 0)
        r["split_by_kp"] = boot_diff(x, x[kpcol] > 0, x[kpcol] == 0)
        for sz in ["large", "small"]:
            y = x[x["size"] == sz]
            r[f"{sz}"] = {"cells": {c: {"n": int((y.cell == c).sum()), "mean": round(y[y.cell == c].ret.mean() * 100, 3) if (y.cell == c).any() else None} for c in ["QQ", "K0Q+", "K+Q0", "00"]},
                          "K0Q+_minus_00": boot_diff(y, y.cell == "K0Q+", y.cell == "00"), "K+Q0_minus_QQ": boot_diff(y, y.cell == "K+Q0", y.cell == "QQ"),
                          "split_by_kq": boot_diff(y, y[kqcol] > 0, y[kqcol] == 0), "split_by_kp": boot_diff(y, y[kpcol] > 0, y[kpcol] == 0)}
        res[mk] = r
    # 방식별 사후 가중(전 종목)
    kp, kq = df[kpcol].values, df[kqcol].values; own = np.where(df.market.values == "KOSPI", kp, kq)
    methods = {"U_균등": np.ones(len(df)), "A_코스피": kp, "B_소속시장": own, "C_min": np.minimum(kp, kq), "D_max": np.maximum(kp, kq), "E_평균": (kp + kq) / 2}
    wk = pd.Categorical(df.wk); W = len(wk.categories); code = wk.codes; r_ = df.ret.values
    idx = RNG.integers(0, W, size=(B, W))
    def stats(m, sel=None):
        if sel is None: sel = np.ones(len(df), bool)
        mr = np.bincount(code[sel], weights=(m * r_)[sel], minlength=W); ms = np.bincount(code[sel], weights=m[sel], minlength=W); n = np.bincount(code[sel], minlength=W)
        return mr, ms, n
    mm = {}
    for mk, sel in [("ALL", np.ones(len(df), bool)), ("KOSDAQ", (df.market == "KOSDAQ").values), ("KOSPI", (df.market == "KOSPI").values)]:
        base = stats(methods["A_코스피"], sel); o = {}
        for name, m in methods.items():
            mr, ms, n = stats(m, sel)
            eff = mr.sum() / ms.sum(); cap = mr.sum() / n.sum()
            be = mr[idx].sum(1) / ms[idx].sum(1) - base[0][idx].sum(1) / base[1][idx].sum(1)
            bc = mr[idx].sum(1) / n[idx].sum(1) - base[0][idx].sum(1) / base[2][idx].sum(1)
            o[name] = {"buyable": round(float((m[sel] > 0).mean()), 3), "mean_m": round(float(m[sel].mean()), 3),
                       "eff_pct": round(eff * 100, 3), "cap_pct": round(cap * 100, 4),
                       "eff_minus_A": [round(float(np.percentile(be, q)) * 100, 3) for q in (5, 50, 95)],
                       "cap_minus_A": [round(float(np.percentile(bc, q)) * 100, 4) for q in (5, 50, 95)]}
        mm[mk] = o
    res["methods"] = mm
    return res


R = {}
R["IDX_1997_2026"] = block(T, "m_kp_idx", "m_kq_idx", "S-IDX 전 기간")
for a, b, nm in [("1997-01-01", "2008-12-31", "IDX_1997_2008"), ("2009-01-01", "2019-12-31", "IDX_2009_2019"), ("2020-01-01", "2026-12-31", "IDX_2020_2026")]:
    R[nm] = block(T[(T.entry_dd >= a) & (T.entry_dd <= b)], "m_kp_idx", "m_kq_idx", nm)
R["ETF_2016_2026"] = block(T[T.entry_dd >= "2016-03-01"], "m_kp_etf", "m_kq_etf", "S-ETF")
R["IDX_2016_2026"] = block(T[T.entry_dd >= "2016-03-01"], "m_kp_idx", "m_kq_idx", "S-IDX 같은 기간")
(OUT / "mu_cells.json").write_text(json.dumps(R, ensure_ascii=False, indent=1))

for k, v in R.items():
    print("\n=====", k, v["n"], v["from"], v["to"])
    for mk in ["KOSDAQ", "KOSPI"]:
        r = v[mk]; print(" --", mk)
        for c, x in r["cells"].items(): print("   ", c, x)
        for key in ["K0Q+_minus_00", "K+Q0_minus_QQ", "K0Q+_minus_QQ", "K+Q0_minus_00", "split_by_kq", "split_by_kp"]: print("   ", key, r[key])
        for sz in ["large", "small"]:
            print("   ", sz, r[sz]["cells"]); print("      K0Q+-00", r[sz]["K0Q+_minus_00"], "K+Q0-QQ", r[sz]["K+Q0_minus_QQ"]); print("      by_kq", r[sz]["split_by_kq"], "by_kp", r[sz]["split_by_kp"])
    for mk, o in v["methods"].items():
        print(" methods", mk)
        for name, s in o.items(): print("   ", name, s)
