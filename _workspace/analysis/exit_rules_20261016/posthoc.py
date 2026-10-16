"""사후 보고(동결 밖 — 도출·판정에 쓰지 않는다).

(1) 첫 닿음 곡선의 H 민감도: H=20 으로 다시(T) — 「손절선 닿은 뒤 반등」 이 5봉짜리 현상인지
(2) 급락 국면 지수 낙폭 중 밤사이 갭 몫(국내 2 + 해외 6, 시가 있는 자료) — 어떤 손절선도 못 막는 몫의 크기
실행: /opt/anaconda3/envs/upbit-trader/bin/python posthoc.py <scratch>
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = sys.argv[1]
sys.argv = [sys.argv[0], SCR]
spec = importlib.util.spec_from_file_location("ms", os.path.join(HERE, "measure.py"))
MS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MS)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
GL = os.path.join(ROOT, "data", "archive", "global_long", "raw")
KR = os.path.join(ROOT, "data", "archive", "krx_daily_long", "index")
EPIS = {"2000": ("2000-03-01", "2000-12-31"), "2008": ("2008-05-01", "2008-11-30"), "2011": ("2011-07-15", "2011-10-15"),
        "2020": ("2020-02-01", "2020-04-15"), "2022": ("2022-01-01", "2022-10-31")}


def ohlc_yahoo(code):
    r = json.load(open(os.path.join(GL, f"yahoo_{code}.json")))["chart"]["result"][0]
    off = r["meta"].get("gmtoffset", 0)
    d = [datetime.fromtimestamp(t + off, tz=timezone.utc).date() for t in r["timestamp"]]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({"o": q["open"], "c": q["close"]}, index=pd.DatetimeIndex(d)).dropna()
    return df[~df.index.duplicated(keep="last")].sort_index()


def ohlc_krx(fn):
    d = pd.read_csv(os.path.join(KR, fn)).dropna(subset=["close"])
    d["date"] = pd.to_datetime(d["date"])
    return pd.DataFrame({"o": d.open.to_numpy(float), "c": d.close.to_numpy(float)}, index=pd.DatetimeIndex(d.date)).sort_index()


def gap_share(df, a, b):
    x = df[(df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b))]
    if len(x) < 10:
        return None
    full = df.loc[:pd.Timestamp(b)]
    i0 = full.index.get_loc(x.index[0])
    if i0 == 0:
        return None
    c = full.c.to_numpy()[i0 - 1:]
    o = full.o.to_numpy()[i0:]
    c = c[:len(o) + 1]
    pk = np.argmax(c[:-1]) if False else 0
    k_hi = int(np.argmax(c))
    k_lo = k_hi + int(np.argmin(c[k_hi:]))
    if k_lo <= k_hi:
        return None
    gaps = np.log(o[k_hi:k_lo] / c[k_hi:k_lo])
    intr = np.log(c[k_hi + 1:k_lo + 1] / o[k_hi:k_lo])
    tot = float(np.log(c[k_lo] / c[k_hi]))
    flat = float(np.mean(np.abs(o[k_hi:k_lo] / c[k_hi:k_lo] - 1) < 1e-6))
    return {"peak": str(x.index[0] if k_hi == 0 else full.index[i0 - 1 + k_hi].date()), "trough": str(full.index[i0 - 1 + k_lo].date()),
            "drawdown": float(np.exp(tot) - 1), "gap_part": float(gaps.sum()), "intraday_part": float(intr.sum()),
            "gap_share": float(gaps.sum() / tot) if tot < 0 else None, "open_eq_prevclose_share": flat}


def main():
    out = {"touch_H20": {}, "gap_share": {}}
    for k in MS.STOCK:
        P = MS.load(k)
        cal = pd.DatetimeIndex(P["cal"])
        RT = [r for r in P["recs"] if r["win"] == "T"]
        ev, f0, _ = MS.touch_events(RT, 20, cal, "atr")
        f0v = float(f0.mean())
        out["touch_H20"][k] = {"f0": f0v, "atr": MS.curve(ev, f0v)}
        evp, _, _ = MS.touch_events(RT, 20, cal, "pct")
        out["touch_H20"][k]["pct"] = MS.curve(evp, f0v)
        print(k, round(f0v * 100, 2), {z: (round(v["delta"] * 100, 2), None if v["t"] is None else round(v["t"], 1))
                                       for z, v in out["touch_H20"][k]["atr"].items()}, flush=True)
    src = {"KOSPI": ohlc_krx("krx_kospi.csv"), "KOSDAQ": ohlc_krx("krx_kosdaq.csv")}
    for nm, code in (("SPX", "GSPC"), ("IXIC", "IXIC"), ("N225", "N225"), ("HSI", "HSI"), ("HSCE", "HSCE"), ("SSE", "000001.SS")):
        src[nm] = ohlc_yahoo(code)
    for ep, (a, b) in EPIS.items():
        out["gap_share"][ep] = {nm: gap_share(df, a, b) for nm, df in src.items()}
    json.dump(out, open(os.path.join(HERE, "posthoc.json"), "w"), ensure_ascii=False, indent=1, default=str)
    for ep, v in out["gap_share"].items():
        print(ep, {nm: (None if x is None or x["gap_share"] is None else (round(x["drawdown"] * 100, 1), round(x["gap_share"], 2), round(x["open_eq_prevclose_share"], 2)))
                   for nm, x in v.items()})


if __name__ == "__main__":
    main()
