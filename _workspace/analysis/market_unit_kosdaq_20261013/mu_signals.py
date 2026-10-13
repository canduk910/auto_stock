"""시장 유닛 판정 계열(코스피 쪽·코스닥 쪽) 만들기 + 불일치 통계. 로컬 보관소만 읽는다."""
import importlib.util, json, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ARCH = ROOT / "data/archive/krx_daily_long"
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mu", ROOT / "src/engine/market_unit.py")
mu = importlib.util.module_from_spec(spec); sys.modules["mu"] = mu; spec.loader.exec_module(mu)
STATES = ["up_rising", "up_falling", "down_rising", "down_falling"]


def series_m(dates, closes):
    """거래일 D 의 판정 = D 앞 마지막 80봉. 반환 DataFrame(index=판정이 쓰인 봉의 '다음 봉' 날짜가 아니라 as-of 봉 날짜)."""
    dates = list(dates); closes = [float(c) for c in closes]
    rows = []
    for i in range(len(dates)):
        cl, reason = mu.classify(closes[max(0, i - 79): i + 1])
        rows.append((dates[i], cl.state if cl else None, cl.m if cl else np.nan))
    return pd.DataFrame(rows, columns=["asof", "state", "m"]).set_index("asof")


def load_series():
    import glob
    etf = pd.concat([pd.read_parquet(x, columns=["ticker", "bas_dd", "close"]) for x in sorted(glob.glob(str(ARCH / "parquet_etf/*.parquet")))])
    e200 = etf[etf.ticker == "069500"].sort_values("bas_dd").set_index("bas_dd").close
    e150 = etf[etf.ticker == "229200"].sort_values("bas_dd").set_index("bas_dd").close
    kp = pd.read_csv(ARCH / "index/market_unit_series.csv", parse_dates=["date"]).set_index("date").close.dropna()
    kq = pd.read_csv(ARCH / "index/krx_kosdaq.csv", parse_dates=["date"]).set_index("date").close.dropna()
    return e200, e150, kp, kq


def build():
    e200, e150, kp, kq = load_series()
    out = {}
    for name, s in [("kp_etf", e200), ("kq_etf", e150), ("kp_idx", kp), ("kq_idx", kq)]:
        d = series_m(s.index, s.values)
        out[name] = d
    # 거래일 D 에 쓰는 값 = 직전 봉 as-of → 달력(코스피 계열)에 맞춰 shift
    cal = kp.index[kp.index >= "1996-01-01"]
    df = pd.DataFrame(index=cal)
    for name, d in out.items():
        a = d.reindex(cal).ffill() if False else d.reindex(cal)
        df[f"m_{name}"] = a.m.shift(1); df[f"s_{name}"] = a.state.shift(1)
    df.index.name = "date"
    df.to_csv(OUT / "mu_series.csv")
    return df


def runs(mask):
    """True 구간 길이 목록."""
    v = mask.values.astype(int); out = []; c = 0
    for x in v:
        if x: c += 1
        elif c: out.append(c); c = 0
    if c: out.append(c)
    return out


def divergence(df, a, b, start, end):
    d = df.loc[start:end, [f"m_{a}", f"m_{b}", f"s_{a}", f"s_{b}"]].dropna()
    ma, mb = d[f"m_{a}"], d[f"m_{b}"]
    res = {"days": len(d), "from": str(d.index[0].date()), "to": str(d.index[-1].date())}
    res["state_agree"] = round(float((d[f"s_{a}"] == d[f"s_{b}"]).mean()), 4)
    res["m_agree"] = round(float((ma == mb).mean()), 4)
    res["kq_stronger"] = int((mb > ma).sum()); res["kq_weaker"] = int((mb < ma).sum())
    res["corr_m"] = round(float(np.corrcoef(ma, mb)[0, 1]), 3)
    ct = pd.crosstab(d[f"s_{a}"], d[f"s_{b}"]).reindex(index=STATES, columns=STATES, fill_value=0)
    res["crosstab_rows_kp_cols_kq"] = ct.values.tolist()
    for key, mask in [("K0Q+", (ma == 0) & (mb > 0)), ("K+Q0", (ma > 0) & (mb == 0)), ("both0", (ma == 0) & (mb == 0)),
                      ("both+", (ma > 0) & (mb > 0)), ("any_diff", ma != mb)]:
        r = runs(mask)
        res[key] = {"days": int(mask.sum()), "share": round(float(mask.mean()), 4), "episodes": len(r),
                    "median_len": float(np.median(r)) if r else 0, "max_len": max(r) if r else 0}
    res["mean_m"] = {"A_kp": round(float(ma.mean()), 3), "kq": round(float(mb.mean()), 3),
                     "C_min": round(float(np.minimum(ma, mb).mean()), 3), "D_max": round(float(np.maximum(ma, mb).mean()), 3),
                     "E_avg": round(float(((ma + mb) / 2).mean()), 3)}
    res["buyable_share"] = {"A_kp": round(float((ma > 0).mean()), 3), "kq": round(float((mb > 0).mean()), 3),
                            "C_min": round(float((np.minimum(ma, mb) > 0).mean()), 3),
                            "D_max": round(float((np.maximum(ma, mb) > 0).mean()), 3)}
    yr = d.assign(k0q=((ma == 0) & (mb > 0)), kq0=((ma > 0) & (mb == 0))).groupby(d.index.year)[["k0q", "kq0"]].sum()
    res["by_year_K0Q+_K+Q0"] = {int(y): [int(r.k0q), int(r.kq0)] for y, r in yr.iterrows()}
    return res


if __name__ == "__main__":
    df = build()
    R = {}
    R["IDX_1997_2026"] = divergence(df, "kp_idx", "kq_idx", "1997-01-02", "2026-10-02")
    R["IDX_2016_2026"] = divergence(df, "kp_idx", "kq_idx", "2016-03-01", "2026-10-02")
    R["IDX_2021_2026"] = divergence(df, "kp_idx", "kq_idx", "2021-10-01", "2026-10-02")
    R["ETF_2016_2026"] = divergence(df, "kp_etf", "kq_etf", "2016-03-01", "2026-10-02")
    R["ETF_2021_2026"] = divergence(df, "kp_etf", "kq_etf", "2021-10-01", "2026-10-02")
    # 대용 품질: 229200 판정 vs 코스닥 종합지수 판정, 069500 vs 연속 계열
    R["proxy_kq_etf_vs_idx"] = divergence(df, "kq_etf", "kq_idx", "2016-03-01", "2026-10-02")
    R["proxy_kp_etf_vs_idx"] = divergence(df, "kp_etf", "kp_idx", "2016-03-01", "2026-10-02")
    (OUT / "mu_divergence.json").write_text(json.dumps(R, ensure_ascii=False, indent=1))
    for k, v in R.items():
        print(k, {x: v[x] for x in ["days", "state_agree", "m_agree", "kq_stronger", "kq_weaker", "corr_m", "K0Q+", "K+Q0", "both0", "mean_m", "buyable_share"]})
    print(df.tail(3).to_string())
