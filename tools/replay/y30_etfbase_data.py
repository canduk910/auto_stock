#!/usr/bin/env python3
"""30년 재검증(etf_trend · 바탕 층) — 데이터 층. 사전 등록 = ``_workspace/analysis/strategy_30y_20261006/etf_base/prereg.md``.

연구 전용 — ``src/`` 는 읽어서 부르기만 한다.

- 지수 연속 계열(069500 ← KOSPI200 × 이음 비율) · 시장 유닛 m · 60일 낙폭
- 바탕 층 5자산 경로(상장 전은 지수·금리·환율 근사, prereg §1.1)
- 시기별 비용(``meta/regime_costs.csv``) · 가격제한폭(``meta/regime_price_limit.csv``)
- ETF 일봉(네이버 생존분) → 공용 층 ``Store`` 와 같은 모양의 종목 배열
"""
from __future__ import annotations

import glob
import hashlib
import os

import numpy as np
import pandas as pd

ARCH = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long"
SCRATCH = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
           "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/y30eb")
FRED_DIR = os.path.join(SCRATCH, "fred")
TOTALS = os.path.join(SCRATCH, "market_totals.parquet")

K200, KQ150, SHORT, USD, KTB10 = "069500", "229200", "153130", "261240", "148070"
ASSETS = (K200, KQ150, SHORT, USD, KTB10)
KTB_DMOD = 7.5
DIV_YIELD_REPORT = 0.015
SPLICE_069500 = pd.Timestamp("2002-10-14")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 비용 · 가격제한폭 ─────────────────────────────────────────────────────

def load_costs(path: str = os.path.join(ARCH, "meta/regime_costs.csv")) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["from"] = pd.to_datetime(df["from"])
    df["to"] = pd.to_datetime(df["to"]).fillna(pd.Timestamp("2100-01-01"))
    return df


def cost_rt_on(dates, costs: pd.DataFrame, kind: str = "table") -> np.ndarray:
    """날짜별 왕복 비용(비율). kind = table(표 그대로) · fee(수수료 × 2) · const(0.38%)."""
    d = pd.DatetimeIndex(dates)
    out = np.full(len(d), np.nan)
    if kind == "const":
        out[:] = 0.0038
        return out
    for _, r in costs.iterrows():
        mk = (d >= r["from"]) & (d <= r["to"])
        out[mk] = (r["round_trip_pct_assumed"] if kind == "table" else 2 * r["fee_one_way_pct_assumed"]) / 100.0
    pre = d < costs["from"].min()                  # 1995 = 준비 구간 전용 — 첫 행 값
    r0 = costs.iloc[0]
    out[pre] = (r0["round_trip_pct_assumed"] if kind == "table" else 2 * r0["fee_one_way_pct_assumed"]) / 100.0
    if np.isnan(out).any():
        raise ValueError("비용 표 밖의 날짜")
    return out


def price_limit_on(dates, path: str = os.path.join(ARCH, "meta/regime_price_limit.csv")) -> np.ndarray:
    """KOSPI 기준 가격제한폭(비율). ETF 는 유가증권시장 상장이라 KOSPI 행을 쓴다."""
    df = pd.read_csv(path)
    df = df[df.market.isin(["KOSPI", "ALL"])].copy()
    df["from"] = pd.to_datetime(df["from"])
    df["to"] = pd.to_datetime(df["to"]).fillna(pd.Timestamp("2100-01-01"))
    d = pd.DatetimeIndex(dates)
    out = np.full(len(d), np.nan)
    for _, r in df.iterrows():
        mk = (d >= r["from"]) & (d <= r["to"])
        out[mk] = float(r["limit_pct"]) / 100.0
    out[np.isnan(out)] = 0.06          # 1995-04 이전(준비 구간 전용)
    return out


# ── FRED ────────────────────────────────────────────────────────────────

def fred(series: str) -> pd.Series:
    df = pd.read_csv(os.path.join(FRED_DIR, f"{series}.csv"))
    df.columns = ["date", "v"]
    df["date"] = pd.to_datetime(df["date"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna().set_index("date")["v"]


def monthly_on(cal: pd.DatetimeIndex, s: pd.Series) -> np.ndarray:
    """월 값(그 달 1일 표기) → 날짜마다 그 달 값(없으면 직전 달 값)."""
    key = pd.DatetimeIndex([pd.Timestamp(d.year, d.month, 1) for d in cal])
    uk = key.unique()
    full = s.reindex(s.index.union(uk)).ffill()
    return full.reindex(uk).reindex(key).to_numpy(float)


def interp_mid_month(cal: pd.DatetimeIndex, s: pd.Series) -> np.ndarray:
    """월 값을 그 달 15일에 두고 날짜로 선형 보간(범위 밖 = NaN)."""
    x = (s.index + pd.Timedelta(days=14)).values.astype("datetime64[ns]").astype(np.int64).astype(float)
    xi = pd.DatetimeIndex(cal).values.astype("datetime64[ns]").astype(np.int64).astype(float)
    y = np.interp(xi, x, s.to_numpy(float), left=np.nan, right=s.to_numpy(float)[-1])
    return y


def caldays(cal: pd.DatetimeIndex) -> np.ndarray:
    ns = pd.DatetimeIndex(cal).values.astype("datetime64[ns]").astype(np.int64)
    return np.r_[0.0, np.diff(ns) / 86_400e9]


# ── 지수 연속 계열 ──────────────────────────────────────────────────────

def load_index_series() -> pd.DataFrame:
    s = pd.read_csv(os.path.join(ARCH, "index/market_unit_series.csv"), parse_dates=["date"])
    s = s.sort_values("date").reset_index(drop=True)
    o = s["open"].to_numpy(float).copy()
    c = s["close"].to_numpy(float)
    bad = ~np.isfinite(o) | (o <= 0)
    o[bad] = np.r_[c[0], c[:-1]][bad]          # 시가 결측 = 전일 종가
    s["open"] = o
    return s


def _naver_etf(tickers) -> pd.DataFrame:
    fs = sorted(glob.glob(os.path.join(ARCH, "parquet_etf/naver_daily_*.parquet")))
    df = pd.concat([pd.read_parquet(f, columns=["ticker", "bas_dd", "open", "high", "low", "close", "volume",
                                                "name", "no_trade"]) for f in fs], ignore_index=True)
    df = df[df.ticker.isin(tickers)].copy()
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    return df


def chain_backward(cal: pd.DatetimeIndex, etf: pd.DataFrame, proxy_close: np.ndarray, proxy_open: "np.ndarray | None"):
    """상장 뒤 = ETF 수정가(거래 없는 날은 종가 이월·시가 = 전일 종가), 상장 전 = 근사 경로를 상장 첫 종가에 맞춰 잇는다.

    반환 (open, close, src) — src 0 = 근사 · 1 = ETF · −1 = 값 없음.
    """
    n = len(cal)
    g = etf.sort_values("bas_dd")
    g = g[(g.close > 0) & ~g.no_trade.astype(bool) & (g.volume > 0)]
    first = g.bas_dd.iloc[0]
    e = g.set_index("bas_dd").reindex(cal)
    after = cal >= first
    C = np.full(n, np.nan)
    O = np.full(n, np.nan)
    src = np.full(n, -1, dtype=int)
    ec = e.close.to_numpy(float)
    eo = e.open.to_numpy(float)
    i0 = int(np.argmax(after))
    for i in range(i0, n):
        if np.isfinite(ec[i]):
            C[i] = ec[i]
            O[i] = eo[i] if np.isfinite(eo[i]) and eo[i] > 0 else C[i - 1]
        else:
            C[i] = C[i - 1]
            O[i] = C[i - 1]
        src[i] = 1
    pc = pd.Series(np.asarray(proxy_close, float)).ffill().to_numpy()     # 근사 원천의 빈 날 = 이월
    if np.isfinite(pc[i0]):
        k = C[i0] / pc[i0]
        lo = i0
        while lo - 1 >= 0 and np.isfinite(pc[lo - 1]):
            lo -= 1
        C[lo:i0] = pc[lo:i0] * k
        src[lo:i0] = 0
        po = None if proxy_open is None else np.asarray(proxy_open, float)
        for i in range(lo, i0):
            if po is not None and np.isfinite(po[i]) and po[i] > 0:
                O[i] = po[i] * k
            else:
                O[i] = C[i - 1] if i > lo else C[i]
    return O, C, src


def proxy_cash(cal: pd.DatetimeIndex, rate_pct: np.ndarray) -> np.ndarray:
    """금리(연 %) 복리 경로. 첫 날 = 1."""
    cd = caldays(cal)
    r = np.nan_to_num(rate_pct / 100.0)
    g = (1 + np.r_[0.0, r[:-1]]) ** (cd / 365.0)
    return np.cumprod(g)


def proxy_ktb(cal: pd.DatetimeIndex, y10_pct: np.ndarray, short_pct: np.ndarray) -> np.ndarray:
    cd = caldays(cal)
    y = y10_pct / 100.0
    s = short_pct / 100.0
    ret = np.zeros(len(cal))
    for i in range(1, len(cal)):
        if np.isfinite(y[i]) and np.isfinite(y[i - 1]):
            ret[i] = y[i - 1] * cd[i] / 365.0 - KTB_DMOD * (y[i] - y[i - 1])
        else:
            ret[i] = (1 + np.nan_to_num(s[i - 1])) ** (cd[i] / 365.0) - 1
    return np.cumprod(1 + ret)


def proxy_usd(cal: pd.DatetimeIndex, spot: pd.Series, us3m_pct: np.ndarray) -> np.ndarray:
    """원/달러 현물(그날보다 앞선 마지막 관측) × 미국 단기 금리 이자."""
    sp = spot.sort_index()
    pos = sp.index.searchsorted(cal, side="left") - 1
    v = np.where(pos >= 0, sp.to_numpy(float)[np.clip(pos, 0, None)], np.nan)
    cd = caldays(cal)
    r = np.nan_to_num(us3m_pct / 100.0)
    carry = np.cumprod((1 + np.r_[0.0, r[:-1]]) ** (cd / 365.0))
    return v * carry


def load_base_assets(div_report: bool = False) -> dict:
    """바탕 층 5자산 (cal, O, Cl, src) + 지수 판단 재료. ``div_report`` = 2002-10 이전 069500 에 연 1.5% 배당 누적."""
    s = load_index_series()
    cal = pd.DatetimeIndex(s.date)
    n = len(cal)
    O = np.full((n, len(ASSETS)), np.nan)
    Cl = O.copy()
    SRC = np.full((n, len(ASSETS)), -1, dtype=int)
    c_idx = s.close.to_numpy(float)
    o_idx = s.open.to_numpy(float)
    k_o, k_c = o_idx.copy(), c_idx.copy()
    if div_report:
        pre = cal < SPLICE_069500
        cd = caldays(cal)
        acc = np.cumprod((1 + DIV_YIELD_REPORT) ** (cd / 365.0))
        # 이음일에 1 이 되도록 앞쪽만 할증(뒤쪽 = 네이버 분배 수정가 그대로)
        j = int(np.argmax(~pre))
        f = np.where(pre, acc / acc[j], 1.0)
        k_o, k_c = o_idx * f, c_idx * f
    O[:, 0], Cl[:, 0] = k_o, k_c
    SRC[:, 0] = np.where(cal < SPLICE_069500, 0, 1)
    etf = _naver_etf(set(ASSETS))
    # 229200 ← 코스닥 종합지수
    kq = pd.read_csv(os.path.join(ARCH, "index/krx_kosdaq.csv"), parse_dates=["date"]).set_index("date").reindex(cal)
    o, c, sr = chain_backward(cal, etf[etf.ticker == KQ150], kq.close.to_numpy(float), kq.open.to_numpy(float))
    O[:, 1], Cl[:, 1], SRC[:, 1] = o, c, sr
    # 153130 ← 단기 금리 이자
    ir3 = monthly_on(cal, fred("IR3TIB01KRM156N"))
    cash_path = proxy_cash(cal, ir3)
    o, c, sr = chain_backward(cal, etf[etf.ticker == SHORT], cash_path, None)
    O[:, 2], Cl[:, 2], SRC[:, 2] = o, c, sr
    # 261240 ← 원/달러 현물 + 미국 단기 금리
    us3 = monthly_on(cal, fred("TB3MS"))
    usd_path = proxy_usd(cal, fred("DEXKOUS"), us3)
    o, c, sr = chain_backward(cal, etf[etf.ticker == USD], usd_path, None)
    O[:, 3], Cl[:, 3], SRC[:, 3] = o, c, sr
    # 148070 ← 국고 10년 금리(2000-10 ~) · 그 전 단기 금리 이자
    y10 = interp_mid_month(cal, fred("IRLTLT01KRM156N"))
    first10 = fred("IRLTLT01KRM156N").index[0] + pd.Timedelta(days=14)
    y10[cal < first10] = np.nan
    ktb_path = proxy_ktb(cal, y10, ir3)
    o, c, sr = chain_backward(cal, etf[etf.ticker == KTB10], ktb_path, None)
    O[:, 4], Cl[:, 4], SRC[:, 4] = o, c, sr
    return {"cal": cal, "O": O, "Cl": Cl, "SRC": SRC, "c_idx": c_idx}


def market_unit(closes: np.ndarray) -> np.ndarray:
    from replay.audit import market_unit as MU
    return MU.m_at_bars(np.asarray(closes, float))


# ── ETF(etf_trend) ──────────────────────────────────────────────────────

def load_etf_panel(cls: dict) -> pd.DataFrame:
    fs = sorted(glob.glob(os.path.join(ARCH, "parquet_etf/naver_daily_*.parquet")))
    df = pd.concat([pd.read_parquet(f, columns=["ticker", "bas_dd", "open", "high", "low", "close", "volume",
                                                "name", "no_trade"]) for f in fs], ignore_index=True)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    keep = {t for t, v in cls.items() if v} | {K200}
    return df[df.ticker.isin(keep)].copy()


def etf_bars(df: pd.DataFrame, cal: pd.DatetimeIndex) -> dict:
    """공용 층 ``build_store(nontrade="drop")`` 와 같은 키. 원본가 = 수정가(네이버), 거래대금 = 종가 × 거래량, 시총 없음."""
    di_map = pd.Series(np.arange(len(cal)), index=cal)
    bars = {}
    for t, g in df.groupby("ticker", sort=True):
        g = g.sort_values("bas_dd")
        g = g[(g.open > 0) & (g.high > 0) & (g.low > 0) & (g.close > 0) & (g.volume > 0)
              & ~g.no_trade.astype(bool)]
        if not len(g):
            continue
        o = g.open.to_numpy(float)
        c = g.close.to_numpy(float)
        bars[t] = {"di": di_map.loc[pd.DatetimeIndex(g.bas_dd.values)].to_numpy(), "o": o,
                   "h": g.high.to_numpy(float), "l": g.low.to_numpy(float), "c": c, "o_raw": o, "c_raw": c,
                   "raw": np.ones(len(g)), "tv": c * g.volume.to_numpy(float), "vol": g.volume.to_numpy(float),
                   "mktcap": np.full(len(g), np.nan), "mkt": np.zeros(len(g), dtype=int),
                   "src": np.zeros(len(g), dtype=int), "notrade": np.zeros(len(g), dtype=bool)}
    return bars


def deflator(cal: pd.DatetimeIndex, path: str = TOTALS) -> np.ndarray:
    """그날 전체 시장 시총 ÷ 2025 년 평균(없는 날 = 직전 값)."""
    tot = pd.read_parquet(path)
    ref = float(tot.mc[tot.index.year == 2025].mean())
    v = tot.mc.reindex(tot.index.union(cal)).ffill().reindex(cal).to_numpy(float)
    return v / ref
