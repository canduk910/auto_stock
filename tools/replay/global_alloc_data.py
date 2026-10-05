#!/usr/bin/env python3
"""여러 나라 자산배분 연구 — 원화 기준 일별 총수익 계열 만들기.

입력 = ``data/archive/global_long/raw/`` (``tools/archive/global_long_fetch.py``) + KRX 지수
``data/archive/krx_daily_long/index/krx_kospi200.csv``.
출력 = ``data/archive/global_long/global_daily_krw.parquet`` (KRX 거래일 색인, 열 = 자산별 원화 총수익 지수 ·
환헤지판 · 현지통화판 · 금리) + ``global_daily_meta.json``.

시각 정렬(미래 정보 차단): KRX 거래일 D 의 값 =
- 미국 자산(S&P500 · 나스닥100 · 미국채 10년 · 달러) 과 모든 환율(FRED 뉴욕 정오) = **D 보다 앞선** 마지막 관측
- 일본 · 홍콩 지수 = D 와 같은 날 또는 그 전 마지막 관측(그 시장 마감이 KRX 마감과 같거나 뒤 1시간 안)
배당 근사 = 가격지수에 연 배당수익률 상수를 매일 1/365 씩 더한다(S&P500 은 Yahoo 총수익지수 원값).

    python tools/replay/global_alloc_data.py <global_long_dir> <krx_index_csv>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

ASSETS = ("K200", "SPX", "NDX", "NKY", "HSCEI", "UST10", "USD")
# 연 배당수익률 근사(가격지수에 더한다) — SPX 는 총수익지수라 0.
DIV_YIELD = {"K200": 0.016, "SPX": 0.0, "NDX": 0.008, "NKY": 0.013, "HSCEI": 0.030}
CURRENCY = {"K200": "KRW", "SPX": "USD", "NDX": "USD", "NKY": "JPY", "HSCEI": "HKD", "UST10": "USD",
            "USD": "USD"}
SAME_DAY = {"NKY", "HSCEI"}            # D 당일 종가까지 쓴다
JP_RATE_BEFORE_2002 = 0.003           # FRED 일본 3개월 금리 시작(2002-04) 전 상수


def _yahoo(path: str) -> pd.Series:
    with open(path) as f:
        r = json.load(f)["chart"]["result"][0]
    off = r["meta"].get("gmtoffset", 0)
    ts = r["timestamp"]
    c = r["indicators"]["quote"][0]["close"]
    d = [datetime.fromtimestamp(t + off, tz=timezone.utc).date() for t in ts]
    s = pd.Series(c, index=pd.DatetimeIndex(d), dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")]
    return s.sort_index()


def _fred(path: str) -> pd.Series:
    d = pd.read_csv(path)
    s = pd.to_numeric(d.iloc[:, 1], errors="coerce")
    s.index = pd.DatetimeIndex(d.iloc[:, 0])
    return s.dropna().sort_index()


def par_bond_return(y_prev: np.ndarray, y_now: np.ndarray, dt_years: np.ndarray, n: int = 10) -> np.ndarray:
    """만기 n 년 액면 채권(쿠폰 = 전일 금리, 반기 지급)을 오늘 금리로 다시 매긴 가격 변화 + 경과 이자.

    ``r = P(y_now; c=y_prev) − 1 + y_prev·dt``. 매일 새 10년물로 굴린다(상수 만기 근사).
    """
    c = y_prev / 2.0
    k = y_now / 2.0
    m = 2 * n
    with np.errstate(divide="ignore", invalid="ignore"):
        ann = np.where(np.abs(k) > 1e-9, (1 - (1 + k) ** (-m)) / k, m)
    price = c * ann + (1 + k) ** (-m)
    return price - 1.0 + y_prev * dt_years


def _align(s: pd.Series, idx: pd.DatetimeIndex, strict_before: bool) -> pd.Series:
    """KRX 거래일 idx 각각에 대해 s 의 마지막 관측(strict_before 면 D 미만, 아니면 D 이하)."""
    src = s.copy()
    if strict_before:
        src = src.shift(1, freq="D")   # D−1 이하 == (원래날짜+1) ≤ D
    return src.reindex(src.index.union(idx)).ffill().reindex(idx)


def _rate_daily(monthly: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """월 평균 금리(%) → 그 달에 공표 전 값 사용을 피하려 한 달 미룬 뒤 일별 앞채움(소수)."""
    m = monthly.copy() / 100.0
    m.index = m.index + pd.offsets.MonthBegin(1)
    return m.reindex(m.index.union(idx)).ffill().reindex(idx)


def build(gdir: str, krx_index_csv: str) -> tuple[pd.DataFrame, dict]:
    raw = os.path.join(gdir, "raw")
    k = pd.read_csv(krx_index_csv, parse_dates=["date"]).set_index("date")["close"].dropna()
    idx = pd.DatetimeIndex(k.index)
    idx = idx[idx >= "1995-01-03"]

    fx_kous = _align(_fred(os.path.join(raw, "fred_DEXKOUS.csv")), idx, True)
    fx_jpus = _align(_fred(os.path.join(raw, "fred_DEXJPUS.csv")), idx, True)
    fx_hkus = _align(_fred(os.path.join(raw, "fred_DEXHKUS.csv")), idx, True)
    krw_per = {"KRW": pd.Series(1.0, index=idx), "USD": fx_kous, "JPY": fx_kous / fx_jpus,
               "HKD": fx_kous / fx_hkus}

    r_kr = _rate_daily(_fred(os.path.join(raw, "fred_IR3TIB01KRM156N.csv")), idx)
    r_us = _align(_fred(os.path.join(raw, "fred_DTB3.csv")) / 100.0, idx, True)
    r_jp = _rate_daily(_fred(os.path.join(raw, "fred_IR3TIB01JPM156N.csv")), idx).fillna(JP_RATE_BEFORE_2002)
    rate_of = {"USD": r_us, "JPY": r_jp, "HKD": r_us, "KRW": r_kr}   # HKD 는 달러 페그 → 미국 금리

    days = pd.Series(idx, index=idx).diff().dt.days.fillna(1).astype(float)
    dt_y = days / 365.0

    local = {}
    local["K200"] = k.reindex(idx)
    local["SPX"] = _align(_yahoo(os.path.join(raw, "yahoo_SP500TR.json")), idx, True)
    local["NDX"] = _align(_yahoo(os.path.join(raw, "yahoo_NDX.json")), idx, True)
    local["NKY"] = _align(_yahoo(os.path.join(raw, "yahoo_N225.json")), idx, False)
    local["HSCEI"] = _align(_yahoo(os.path.join(raw, "yahoo_HSCE.json")), idx, False)
    y10 = _align(_fred(os.path.join(raw, "fred_DGS10.csv")) / 100.0, idx, True)

    out = {}
    meta = {"div_yield": DIV_YIELD, "assets": ASSETS, "first": str(idx[0].date()), "last": str(idx[-1].date())}
    loc_ret = {}
    for a in ("K200", "SPX", "NDX", "NKY", "HSCEI"):
        pr = local[a].pct_change().fillna(0.0)
        loc_ret[a] = pr + DIV_YIELD[a] * dt_y
    yp = y10.shift(1).bfill().to_numpy()
    loc_ret["UST10"] = pd.Series(par_bond_return(yp, y10.to_numpy(), dt_y.to_numpy()), index=idx)
    loc_ret["UST10"].iloc[0] = 0.0
    loc_ret["USD"] = r_us.shift(1).bfill() * dt_y            # 달러 현금 = 미국 단기금리
    cash = r_kr.shift(1).bfill() * dt_y
    cash.iloc[0] = 0.0

    for a in ASSETS:
        cur = CURRENCY[a]
        fxr = (krw_per[cur] / krw_per[cur].shift(1)).fillna(1.0) - 1.0
        unh = (1 + loc_ret[a]) * (1 + fxr) - 1                       # 환노출
        carry = (r_kr.shift(1).bfill() - rate_of[cur].shift(1).bfill()) * dt_y
        hed = loc_ret[a] + (carry if cur != "KRW" else 0.0)          # 환헤지(금리차 근사)
        if a == "USD":
            hed = cash.copy()                                          # 달러를 헤지하면 원화 현금
        out[f"{a}_ret"] = unh
        out[f"{a}_hret"] = hed
        out[f"{a}_lret"] = loc_ret[a]
    out["CASH_ret"] = cash
    out["r_kr"] = r_kr
    out["r_us"] = r_us
    out["fx_usdkrw"] = fx_kous
    out["y10"] = y10
    for a in ("K200", "SPX", "NDX", "NKY", "HSCEI"):
        out[f"{a}_px_local"] = local[a]
    df = pd.DataFrame(out, index=idx)
    df.index.name = "date"
    nan = df.isna().sum()
    meta["nan_counts"] = {c: int(v) for c, v in nan.items() if v}
    return df, meta


def main(gdir: str, krx_index_csv: str) -> None:
    df, meta = build(gdir, krx_index_csv)
    df.to_parquet(os.path.join(gdir, "global_daily_krw.parquet"))
    with open(os.path.join(gdir, "global_daily_meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    yr = (1 + df[[f"{a}_ret" for a in ASSETS] + ["CASH_ret"]]).groupby(df.index.year).prod() - 1
    print(yr.round(3).to_string())
    print(meta)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
