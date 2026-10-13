"""사후(prereg 밖) — F 방식(코스피 종목=코스피, 코스닥 종목=min) · K0Q+ 세부 · 구간 수. 판정에는 쓰지 않는다."""
import json
from pathlib import Path
import numpy as np, pandas as pd
OUT = Path(__file__).resolve().parent
RNG = np.random.default_rng(20261014); B = 2000
T = pd.read_parquet(OUT / "trades.parquet")
S = pd.read_csv(OUT / "mu_series.csv", parse_dates=["date"]).set_index("date")
T = T.join(S, on="entry_dd"); T["wk"] = T.entry_dd.dt.strftime("%G-%V")
R = {}

def meth(df, kpc, kqc):
    df = df.dropna(subset=[kpc, kqc]); kp, kq = df[kpc].values, df[kqc].values; isq = (df.market == "KOSDAQ").values
    M = {"A": kp, "B": np.where(isq, kq, kp), "F_코스닥만min": np.where(isq, np.minimum(kp, kq), kp), "C_min": np.minimum(kp, kq),
         "G_코스닥만평균": np.where(isq, (kp + kq) / 2, kp)}
    wk = pd.Categorical(df.wk); W = len(wk.categories); code = wk.codes; r = df.ret.values; idx = RNG.integers(0, W, size=(B, W))
    def st(m): return np.bincount(code, weights=m * r, minlength=W), np.bincount(code, weights=m, minlength=W), np.bincount(code, minlength=W)
    b = st(M["A"]); o = {}
    for k, m in M.items():
        a = st(m)
        be = a[0][idx].sum(1) / a[1][idx].sum(1) - b[0][idx].sum(1) / b[1][idx].sum(1)
        bc = (a[0][idx].sum(1) - b[0][idx].sum(1)) / a[2][idx].sum(1)
        o[k] = {"buyable": round(float((m > 0).mean()), 3), "buyable_kq": round(float((m[isq] > 0).mean()), 3), "mean_m": round(float(m.mean()), 3),
                "eff": round(a[0].sum() / a[1].sum() * 100, 3), "eff_minus_A": [round(float(np.percentile(be, q)) * 100, 3) for q in (5, 50, 95)],
                "cap_minus_A": [round(float(np.percentile(bc, q)) * 100, 4) for q in (5, 50, 95)]}
    return o

for nm, a, b, kpc, kqc in [("IDX_1997_2026", "1997", "2027", "m_kp_idx", "m_kq_idx"), ("IDX_1997_2008", "1997", "2009", "m_kp_idx", "m_kq_idx"),
                           ("IDX_2009_2019", "2009", "2020", "m_kp_idx", "m_kq_idx"), ("IDX_2020_2026", "2020", "2027", "m_kp_idx", "m_kq_idx"),
                           ("ETF_2016_2026", "2016-03", "2027", "m_kp_etf", "m_kq_etf"), ("IDX_2016_2026", "2016-03", "2027", "m_kp_idx", "m_kq_idx")]:
    R["methods_" + nm] = meth(T[(T.entry_dd >= a) & (T.entry_dd < b)], kpc, kqc)

# K0Q+ 세부: 코스닥 종목, 코스피 0 일 때 코스닥 상태별
for nm, kpc, kss in [("IDX", "m_kp_idx", "s_kq_idx"), ("ETF", "m_kp_etf", "s_kq_etf")]:
    x = T[(T.market == "KOSDAQ") & (T[kpc] == 0)].dropna(subset=[kss])
    if nm == "ETF": x = x[x.entry_dd >= "2016-03-01"]
    R["kp0_by_kqstate_" + nm] = {s: {"n": int(len(g)), "weeks": int(g.wk.nunique()), "mean": round(g.ret.mean() * 100, 3), "win": round((g.ret > 0).mean(), 3)} for s, g in x.groupby(kss)}
    y = T[(T.market == "KOSDAQ") & (T[kpc] > 0)].dropna(subset=[kss])
    if nm == "ETF": y = y[y.entry_dd >= "2016-03-01"]
    R["kp+_by_kqstate_" + nm] = {s: {"n": int(len(g)), "weeks": int(g.wk.nunique()), "mean": round(g.ret.mean() * 100, 3), "win": round((g.ret > 0).mean(), 3)} for s, g in y.groupby(kss)}
# 연도별 K0Q+ (코스닥 종목, IDX)
x = T[(T.market == "KOSDAQ") & (T.m_kp_idx == 0) & (T.m_kq_idx > 0)]
R["K0Q+_kosdaq_by_year_IDX"] = {int(y): [int(len(g)), round(g.ret.mean() * 100, 2)] for y, g in x.groupby(x.entry_dd.dt.year)}
x = T[(T.market == "KOSDAQ") & (T.m_kp_etf == 0) & (T.m_kq_etf > 0) & (T.entry_dd >= "2016-03-01")]
R["K0Q+_kosdaq_by_year_ETF"] = {int(y): [int(len(g)), round(g.ret.mean() * 100, 2)] for y, g in x.groupby(x.entry_dd.dt.year)}
# 대용 모형 구성: 시장·규모별 진입 수와 기준선
R["baseline"] = {f"{m}_{s}": [int(len(g)), round(g.ret.mean() * 100, 3)] for (m, s), g in T.assign(size=np.where(T.market == "KOSPI", np.where(T.kp_rank <= 200, "large", "small"), np.where(T.kq_rank <= 150, "large", "small"))).groupby(["market", "size"])}
(OUT / "mu_posthoc.json").write_text(json.dumps(R, ensure_ascii=False, indent=1))
for k, v in R.items(): print(k, json.dumps(v, ensure_ascii=False))
