"""지수 구성 근사(M) 표 + KOSDAQ150·KOSPI200 시총가중 근사 지수 + 원천별 m 판정·일치율 (prereg §1·§2 보고).

산출: 스크래치 mem.parquet(ticker, bas_dd, mem, kq) · series.csv(날짜별 지수 종가) · 이 폴더 series.json(검증·일치율).
실행: /opt/anaconda3/envs/upbit-trader/bin/python -I series.py <scratch>
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
sys.path.insert(0, "/Users/koscom/Projects/auto_stock")
from replay.audit import market_unit as MU  # noqa
from replay.strategies import donchian_y30_data as YD  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = sys.argv[1]
LONG = YD.LONG


def capw_index(df: pd.DataFrame, grp: str, top: int) -> pd.Series:
    """그날 grp 보통주 중 전날 시총 상위 top 의 전날 시총 가중 수익률 연결(1000 시작)."""
    d = df[(df.g == grp) & df.common].sort_values(["ticker", "bas_dd"]).copy()
    d["prev_cap"] = d.groupby("ticker")["mktcap"].shift(1)
    d["prev_c"] = d.groupby("ticker")["close_adj"].shift(1)
    d["prev_dd"] = d.groupby("ticker")["bas_dd"].shift(1)
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    prev_of = pd.Series(cal[:-1], index=cal[1:])
    d = d[d.prev_dd.notna()]
    d = d[d.prev_dd.to_numpy() == prev_of.reindex(d.bas_dd).to_numpy()]      # 연속 거래일만
    d = d[(d.prev_cap > 0) & (d.prev_c > 0) & (d.close_adj > 0)]
    d["rk"] = d.groupby("bas_dd")["prev_cap"].rank(ascending=False, method="first")
    d = d[d.rk <= top]
    d["r"] = d.close_adj / d.prev_c - 1
    d["w"] = d.prev_cap
    r = d.groupby("bas_dd").apply(lambda x: float(np.average(x.r, weights=x.w)), include_groups=False)
    days = cal[cal >= r.index.min()]
    r = r.reindex(days).fillna(0.0)
    lvl = 1000 * np.cumprod(1 + r.to_numpy())
    return pd.Series(lvl, index=days)


def state_agree(cal, a: np.ndarray, b: np.ndarray, sel) -> dict:
    ok = np.isfinite(a) & np.isfinite(b) & sel
    if ok.sum() == 0:
        return {"n": 0}
    aa, bb = a[ok], b[ok]
    return {"n": int(ok.sum()), "agree_m": float((aa == bb).mean()),
            "agree_buyable": float(((aa > 0) == (bb > 0)).mean()),
            "a_mean": float(aa.mean()), "b_mean": float(bb.mean()),
            "a0_b_pos": float(((aa == 0) & (bb > 0)).mean()), "a_pos_b0": float(((aa > 0) & (bb == 0)).mean())}


def main():
    cols = ["ticker", "name", "bas_dd", "mktcap", "market", "close_adj"]
    fs = [os.path.join(YD.UNIFIED, f) for f in sorted(os.listdir(YD.UNIFIED)) if f.endswith(".parquet")]
    df = pd.concat([pd.read_parquet(f, columns=cols) for f in fs], ignore_index=True)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    df["g"] = YD.mkt_group(df.market).to_numpy()
    df["common"] = (df.ticker.str.match(YD._COMMON) & ~df.name.fillna("").str.contains("스팩") & (df.mktcap > 0)).to_numpy()
    df["mem"] = YD.member_flags(df)
    df["kq"] = (df.g == "KOSDAQ").to_numpy()
    df.loc[df.mem, ["ticker", "bas_dd", "mem", "kq"]].reset_index(drop=True).to_parquet(os.path.join(SCR, "mem.parquet"))
    q150 = capw_index(df, "KOSDAQ", 150)
    k200a = capw_index(df, "KOSPI", 200)
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    del df

    def rd(fn):
        x = pd.read_csv(os.path.join(LONG, "index", fn))
        x["date"] = pd.to_datetime(x["date"])
        x = x.dropna(subset=["close"]).sort_values("date")
        return pd.Series(x.close.to_numpy(float), index=pd.DatetimeIndex(x.date))
    S = {"kospi": rd("krx_kospi.csv"), "kosdaq": rd("krx_kosdaq.csv"), "k200": rd("krx_kospi200.csv"),
         "q150a": q150, "k200a": k200a}
    mus = YD.market_unit_series()
    S["etf"] = pd.Series(mus.close.to_numpy(float), index=pd.DatetimeIndex(mus.date))
    # 229200 (2015-10~)
    ef = [os.path.join(LONG, "parquet_etf", f) for f in sorted(os.listdir(os.path.join(LONG, "parquet_etf")))]
    e = pd.concat([pd.read_parquet(f) for f in ef], ignore_index=True)
    tcol = "ticker" if "ticker" in e.columns else e.columns[0]
    e = e[e[tcol].astype(str) == "229200"]
    dcol = [c for c in e.columns if "date" in c.lower() or c == "bas_dd"][0]
    ccol = "close" if "close" in e.columns else [c for c in e.columns if "close" in c.lower()][0]
    e = e.sort_values(dcol)
    S["q150etf"] = pd.Series(e[ccol].to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(e[dcol])))
    pd.DataFrame(S).to_csv(os.path.join(SCR, "series.csv"))
    M = {k: MU.m_for_days(cal, v.index, v.to_numpy(float)) for k, v in S.items()}
    np.save(os.path.join(SCR, "m_cal.npy"), cal.to_numpy())
    for k, v in M.items():
        np.save(os.path.join(SCR, f"m_{k}.npy"), v)
    R = {"q150a_start": str(q150.index[0].date())}
    wins = {"ALL": ("1997-01-02", "2026-10-02"), "T": ("1997-01-02", "2012-12-28"), "V": ("2013-01-02", "2020-12-30"),
            "H": ("2021-01-04", "2026-10-02"), "ETF2016": ("2016-01-04", "2026-10-02")}
    for wn, (a, b) in wins.items():
        sel = (cal >= pd.Timestamp(a)) & (cal <= pd.Timestamp(b))
        R[wn] = {"kospi_comp_vs_k200": state_agree(cal, M["kospi"], M["k200"], sel),
                 "kosdaq_comp_vs_q150a": state_agree(cal, M["kosdaq"], M["q150a"], sel),
                 "check_k200a_vs_k200": state_agree(cal, M["k200a"], M["k200"], sel),
                 "check_q150a_vs_q150etf": state_agree(cal, M["q150a"], M["q150etf"], sel),
                 "kosdaq_comp_vs_q150etf": state_agree(cal, M["kosdaq"], M["q150etf"], sel),
                 "k200_vs_etf": state_agree(cal, M["k200"], M["etf"], sel)}
    # 일간 수익률 상관(2015-10~)
    j = pd.DataFrame({"a": S["q150a"], "e": S["q150etf"], "k": S["kosdaq"]}).dropna()
    rr = j.pct_change().dropna()
    R["ret_corr_q150a_vs_229200"] = float(rr.a.corr(rr.e))
    R["ret_corr_kosdaq_vs_229200"] = float(rr.k.corr(rr.e))
    j2 = pd.DataFrame({"a": S["k200a"], "k": S["k200"]}).dropna().pct_change().dropna()
    R["ret_corr_k200a_vs_k200"] = float(j2.a.corr(j2.k))
    # 연도별 코스닥 일치율
    yr = {}
    for y in range(1997, 2027):
        sel = cal.year == y
        yr[y] = {"kospi": state_agree(cal, M["kospi"], M["k200"], sel).get("agree_m"),
                 "kosdaq": state_agree(cal, M["kosdaq"], M["q150a"], sel).get("agree_m")}
    R["by_year_agree_m"] = yr
    json.dump(R, open(os.path.join(HERE, "series.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: R[k] for k in ("ALL", "ETF2016")}, ensure_ascii=False, indent=1))
    print(R["ret_corr_q150a_vs_229200"], R["ret_corr_kosdaq_vs_229200"], R["ret_corr_k200a_vs_k200"])


if __name__ == "__main__":
    main()
