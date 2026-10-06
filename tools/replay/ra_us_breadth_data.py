#!/usr/bin/env python3
"""ra_us_breadth 재료 — 무료 미국 시장 폭 대용 계열(사전 등록 ``ra_us_breadth_20261006/prereg.frozen.md`` §2).

원자료는 git 밖 ``data/archive/global_long/raw/``:
- ``breadth/tv_INDEX_S5FI.json`` · ``tv_INDEX_NDFI.json`` — TradingView 공개 웹소켓(비로그인) 일봉(종가 = 50일선 위 %).
- ``unicorn_advdec/{NYSE,NASDAQ}_{advn,decln}.csv`` — unicorn.us.com(2020-02 중단) · ``breadth/tv_USI_{ADVN,DECL}.{NY,NQ}.json``.
- ``yahoo_RSP.json`` · ``yahoo_SPY.json``(수정 종가) · ``yahoo_NDXE.json`` · ``yahoo_NDX.json``(가격).
- ``breadth/yahoo_constituents/*.json`` · ``breadth/constituents.json`` — 생존 편향 참고판 재료.

모든 계열 = 미국 거래일 달력의 종가 t 값(미래 정보 없음). KRX 정렬은 ``ra_us.align_before``.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

RAW = "/Users/koscom/Projects/auto_stock/data/archive/global_long/raw"
BR = os.path.join(RAW, "breadth")
UNI = os.path.join(RAW, "unicorn_advdec")
SPLICE = pd.Timestamp("2003-09-25")          # 이날부터 TradingView A/D(사전 고정)
AR_N = 60
EW_N = 60
SV_N = 60
EXCH = {"SPX": ("NYSE", "NY"), "NDX": ("NASDAQ", "NQ")}
P0_SYM = {"SPX": "INDEX_S5FI", "NDX": "INDEX_NDFI"}


# ───────────────────────── 원자료 읽기 ─────────────────────────

def tv_close(name: str) -> pd.Series:
    d = json.load(open(os.path.join(BR, f"tv_{name}.json")))
    b = np.asarray(d["bars"], float)
    idx = pd.to_datetime(b[:, 0], unit="s").normalize()
    s = pd.Series(b[:, 4], index=pd.DatetimeIndex(idx))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.dropna()


def unicorn(exch: str, kind: str) -> pd.Series:
    s = pd.read_csv(os.path.join(UNI, f"{exch}_{kind}.csv"), header=None, names=["d", "v"], dtype={"d": str})
    out = pd.Series(pd.to_numeric(s.v, errors="coerce").to_numpy(float),
                    index=pd.DatetimeIndex(pd.to_datetime(s.d.str.strip(), format="%Y%m%d")))
    return out[~out.index.duplicated(keep="last")].sort_index()


def yahoo(path: str, adj: bool = False) -> pd.Series:
    r = json.load(open(path))["chart"]["result"][0]
    off = r["meta"].get("gmtoffset", 0)
    d = [datetime.fromtimestamp(t + off, tz=timezone.utc).date() for t in r["timestamp"]]
    c = r["indicators"]["adjclose"][0]["adjclose"] if adj else r["indicators"]["quote"][0]["close"]
    s = pd.Series(c, index=pd.DatetimeIndex(d), dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s > 0]


# ───────────────────────── P0 · P1 · P2 ─────────────────────────

def p0(asset: str) -> pd.Series:
    """진짜 폭 = 구성 종목 중 50일선 위 비율(0~1)."""
    return tv_close(P0_SYM[asset]) / 100.0


def ad_counts(asset: str) -> tuple[pd.Series, pd.Series]:
    """상승·하락 종목 수 — SPLICE 전 unicorn, 그날부터 TradingView. 상승 + 하락 ≤ 0 행은 버린다."""
    ex, tx = EXCH[asset]
    ua, ud = unicorn(ex, "advn"), unicorn(ex, "decln").reindex(unicorn(ex, "advn").index)
    ta, td = tv_close(f"USI_ADVN.{tx}"), tv_close(f"USI_DECL.{tx}")
    td = td.reindex(ta.index)
    a = pd.concat([ua[ua.index < SPLICE], ta[ta.index >= SPLICE]])
    d = pd.concat([ud[ud.index < SPLICE], td[td.index >= SPLICE]])
    ok = (a + d > 0) & a.notna() & d.notna()
    return a[ok], d[ok]


def ar_n(adv: pd.Series, dec: pd.Series, n: int = AR_N) -> pd.Series:
    """AR60 = 최근 n 거래일 「상승 ÷ (상승 + 하락)」 평균."""
    return (adv / (adv + dec)).rolling(n, min_periods=n).mean().dropna()


def p1(asset: str) -> pd.Series:
    return ar_n(*ad_counts(asset))


def adl_gap(adv: pd.Series, dec: pd.Series, n: int = AR_N) -> pd.Series:
    """S3 민감도 — 누적 A/D 선 − 자기 n 일 평균(음수 = 선이 평균 아래)."""
    adl = (adv - dec).cumsum()
    return (adl - adl.rolling(n, min_periods=n).mean()).dropna()


def p1_adl(asset: str) -> pd.Series:
    return adl_gap(*ad_counts(asset))


def ew_gap(ew: pd.Series, cw: pd.Series, n: int = EW_N) -> pd.Series:
    """P2 = (동일가중 ÷ 시가총액가중) ÷ 자기 n 일 평균 − 1."""
    j = ew.index.intersection(cw.index)
    r = ew[j] / cw[j]
    return (r / r.rolling(n, min_periods=n).mean() - 1).dropna()


def p2(asset: str) -> pd.Series:
    if asset == "SPX":
        return ew_gap(yahoo(os.path.join(RAW, "yahoo_RSP.json"), adj=True),
                      yahoo(os.path.join(RAW, "yahoo_SPY.json"), adj=True))
    return ew_gap(yahoo(os.path.join(RAW, "yahoo_NDXE.json")), yahoo(os.path.join(RAW, "yahoo_NDX.json")))


# ───────────────────────── 생존 편향 참고판 ─────────────────────────

def above_ma_share(px: pd.DataFrame, n: int = SV_N) -> pd.Series:
    """한국 원판과 같은 정의 — 그날 n 일 평균이 있는 종목 중 종가 > n 일 평균 비율."""
    sma = px.rolling(n, min_periods=n).mean()
    ok = sma.notna() & px.notna()
    ab = (px > sma) & ok
    cnt = ok.sum(axis=1)
    return (ab.sum(axis=1) / cnt.replace(0, np.nan)).dropna()


def sv(asset: str, min_names: int = 50) -> pd.Series:
    """현 구성 종목(2026-10-06 위키백과)의 Yahoo 수정 종가로 만든 60일선 위 비율 — 생존 편향 있음."""
    cons = json.load(open(os.path.join(BR, "constituents.json")))
    names = cons["sp500" if asset == "SPX" else "ndx"]
    cols = {}
    for t in names:
        p = os.path.join(BR, "yahoo_constituents", t.replace(".", "-") + ".json")
        if os.path.exists(p):
            try:
                cols[t] = yahoo(p, adj=True)
            except Exception:
                continue
    px = pd.DataFrame(cols).sort_index()
    px = px[px.index.dayofweek < 5]
    s = above_ma_share(px)
    n = (px.rolling(SV_N, min_periods=SV_N).mean().notna()).sum(axis=1).reindex(s.index)
    return s[n >= min_names]


def sv_coverage(asset: str) -> dict:
    cons = json.load(open(os.path.join(BR, "constituents.json")))
    names = cons["sp500" if asset == "SPX" else "ndx"]
    have = [t for t in names if os.path.exists(os.path.join(BR, "yahoo_constituents", t.replace(".", "-") + ".json"))]
    return {"n_list": len(names), "n_have": len(have), "asof": cons.get("asof")}


def source_table() -> dict:
    """결과 문서 「자료」 절용 — 계열별 첫·끝 날짜·행 수."""
    out = {}

    def rng(s):
        return {"first": str(s.index.min().date()), "last": str(s.index.max().date()), "n": int(len(s))}

    for nm in ("INDEX_S5FI", "INDEX_NDFI"):
        out["tv_" + nm] = rng(tv_close(nm))
    for ex, tx in EXCH.values():
        a = unicorn(ex, "advn")
        d = unicorn(ex, "decln").reindex(a.index)
        z = (a + d) <= 0
        out[f"unicorn_{ex}"] = rng(a[~z]) | {"zero_rows": int(z.sum())}
        out[f"tv_ADVN.{tx}"] = rng(tv_close(f"USI_ADVN.{tx}"))
    for f in ("RSP", "SPY", "NDXE", "NDX", "SPXEW", "QQEW", "QQQE"):
        p = os.path.join(RAW, f"yahoo_{f}.json")
        if os.path.exists(p):
            out[f"yahoo_{f}"] = rng(yahoo(p))
    inv = os.path.join(BR, "investing_S5FI_1225324.json")
    if os.path.exists(inv):
        d = json.load(open(inv))["data"]
        s = pd.Series([float(x["last_closeRaw"]) for x in d],
                      index=pd.DatetimeIndex([x["rowDateTimestamp"][:10] for x in d])).sort_index()
        tv = tv_close("INDEX_S5FI")
        j = s.index.intersection(tv.index)
        out["investing_S5FI"] = rng(s) | {"overlap_tv": int(len(j)),
                                          "max_abs_diff_pct": float((s[j] - tv[j]).abs().max()),
                                          "mean_abs_diff_pct": float((s[j] - tv[j]).abs().mean())}
    return out


if __name__ == "__main__":
    print(json.dumps(source_table(), indent=1, ensure_ascii=False))
    print(glob.glob(os.path.join(BR, "*.json"))[:3])
