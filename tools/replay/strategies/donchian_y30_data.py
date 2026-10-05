"""donchian_swing 30년(1996~2026) 재검증 — 데이터 층.

정본 = 단일 보관소 ``data/archive/krx_daily_long/unified/``(README · meta 먼저). 규약 = 스크래치 ``opt/protocol_30y.md``.
신호는 수정주가(``*_adj``), 체결 원화 환산은 원주가(``open``)로 한다(``audit.panel.build_store`` 와 같은 배열 계약).

이 모듈이 더하는 것(5년 판 ``donchian_kk_audit.build_inputs`` 대비):

- **지수 편입 근사(과거 편입 목록 없음)** — 그날 시총 순위 KOSPI 상위 200 · KOSDAQ(+KOSDAQ GLOBAL) 상위 150,
  보통주(코드 끝 0) · 스팩 제외. 5년 판 ``DK.index_member_archive`` 와 같은 식이되 KOSDAQ GLOBAL 을 KOSDAQ 에 넣는다.
- **거래대금 문턱 시대 중립화** — 현행 「거래대금 ≥ 200억」 이 2025 년에 해당하던 백분위 p*(그날 6자리 숫자 코드
  전 종목 중 200억 이상 비율의 2025 년 평균)를 계산해, 매일 「그날 거래대금 순위 상위 p*」 를 문턱으로 쓴다(``tvok``).
  명목 200억 판(``tv200``)은 민감도로 함께 싣는다.
- 가격제한폭(``lim``) · 위반 표시 행(``jump``, ``meta/unified_jump_flags.csv``) · 시기별 왕복 비용(``meta/regime_costs.csv``).
- 시장 유닛 입력 = ``index/market_unit_series.csv``(KOSPI200 지수 → 069500 연속 계열) · 운영 ``classify`` · D-1.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402

LONG = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long"
UNIFIED = os.path.join(LONG, "unified")
TV_NOMINAL = 200e8
CALIB_YEAR = 2025
KOSPI_TOP, KOSDAQ_TOP = 200, 150

P1_COLS = ["ticker", "name", "bas_dd", "mktcap", "market", "trade_value"]
P2_COLS = ["ticker", "name", "bas_dd", "open", "high", "low", "close", "volume", "trade_value", "mktcap", "market",
           "open_adj", "high_adj", "low_adj", "close_adj", "adj_factor", "no_trade"]

_SIX = re.compile(r"^\d{6}$")
_COMMON = re.compile(r"^\d{5}0$")


def mkt_group(market: pd.Series) -> pd.Series:
    """KOSPI → "KOSPI" · KOSDAQ / KOSDAQ GLOBAL → "KOSDAQ" · 그 밖 → 그대로."""
    s = market.astype(str)
    return s.where(~s.str.startswith("KOSDAQ"), "KOSDAQ")


def member_flags(df: pd.DataFrame) -> np.ndarray:
    """그날 시총 순위 편입 근사(행 순서 = 동률 순위, rank method=first — 5년 판과 같다)."""
    grp = mkt_group(df.market)
    common = df.ticker.str.match(_COMMON) & ~df.name.fillna("").str.contains("스팩") & (df.mktcap > 0)
    rk = pd.Series(np.nan, index=df.index)
    sub = df[common]
    rk.loc[sub.index] = sub.assign(g=grp[common]).groupby(["bas_dd", "g"])["mktcap"].rank(
        ascending=False, method="first")
    return (((grp == "KOSPI") & (rk <= KOSPI_TOP)) | ((grp == "KOSDAQ") & (rk <= KOSDAQ_TOP))).to_numpy()


def tv_share_at(df: pd.DataFrame, thr: float = TV_NOMINAL) -> pd.Series:
    """날짜별 「6자리 숫자 코드 전 종목 중 거래대금 ≥ thr 비율」."""
    six = df[df.ticker.str.match(_SIX)]
    return six.groupby("bas_dd")["trade_value"].apply(lambda x: float((x >= thr).mean()))


def tv_top_flags(df: pd.DataFrame, p_star: float) -> np.ndarray:
    """그날 6자리 숫자 코드 전 종목 중 거래대금 순위(내림차순) ≤ p* × 종목 수 이면 True. 그 밖 코드 = False."""
    six = df.ticker.str.match(_SIX)
    out = pd.Series(False, index=df.index)
    sub = df[six]
    rk = sub.groupby("bas_dd")["trade_value"].rank(ascending=False, method="min")
    nday = sub.groupby("bas_dd")["trade_value"].transform("size")
    out.loc[sub.index] = (rk <= p_star * nday) & (sub.trade_value > 0)
    return out.to_numpy()


def load_pass1(years=range(1996, 2027)) -> pd.DataFrame:
    fs = [os.path.join(UNIFIED, f"krx_unified_{y}.parquet") for y in years]
    return pd.concat([pd.read_parquet(f, columns=P1_COLS) for f in fs if os.path.exists(f)], ignore_index=True)


def calibrate_p_star(p1: pd.DataFrame, year: int = CALIB_YEAR) -> dict:
    d = p1[p1.bas_dd.dt.year == year]
    sh = tv_share_at(d)
    return {"year": year, "p_star": float(sh.mean()), "days": int(len(sh)), "share_min": float(sh.min()),
            "share_max": float(sh.max()), "share_median": float(sh.median())}


def price_limits() -> pd.DataFrame:
    return pd.read_csv(os.path.join(LONG, "meta/regime_price_limit.csv"))


def limit_for(dates: pd.Series, market: pd.Series, pl: "pd.DataFrame | None" = None) -> np.ndarray:
    """행마다 가격제한폭(비율). KOSDAQ 정액제(1996-07~11, 워밍업 구간)는 8% 로 근사."""
    pl = price_limits() if pl is None else pl
    out = np.full(len(dates), np.nan)
    d = pd.to_datetime(dates).to_numpy()
    g = mkt_group(market).to_numpy()
    for _, r in pl.iterrows():
        a = np.datetime64(pd.Timestamp(r["from"]))
        b = np.datetime64(pd.Timestamp(r["to"])) if isinstance(r["to"], str) and r["to"] else np.datetime64("2100-01-01")
        lim = 0.08 if str(r["limit_pct"]) == "정액제" else float(r["limit_pct"]) / 100.0
        msk = (d >= a) & (d <= b)
        if r["market"] != "ALL":
            msk &= (g == r["market"])
        out[msk] = lim
    out[np.isnan(out)] = 0.15
    return out


def costs_table() -> pd.DataFrame:
    t = pd.read_csv(os.path.join(LONG, "meta/regime_costs.csv"))
    t["from"] = pd.to_datetime(t["from"])
    return t.sort_values("from").reset_index(drop=True)


def cost_rt_on(cal: pd.DatetimeIndex, tbl: "pd.DataFrame | None" = None) -> np.ndarray:
    """달력 날마다 시기별 왕복 비용(비율) — ``round_trip_pct_assumed`` / 100."""
    tbl = costs_table() if tbl is None else tbl
    k = tbl["from"].searchsorted(cal, side="right") - 1
    k = np.clip(k, 0, len(tbl) - 1)
    return tbl["round_trip_pct_assumed"].to_numpy(float)[k] / 100.0


def fee_one_way_on(cal: pd.DatetimeIndex, tbl: "pd.DataFrame | None" = None) -> np.ndarray:
    tbl = costs_table() if tbl is None else tbl
    k = np.clip(tbl["from"].searchsorted(cal, side="right") - 1, 0, len(tbl) - 1)
    return tbl["fee_one_way_pct_assumed"].to_numpy(float)[k] / 100.0


def jump_rows() -> pd.DataFrame:
    j = pd.read_csv(os.path.join(LONG, "meta/unified_jump_flags.csv"), dtype={"ticker": str})
    j["bas_dd"] = pd.to_datetime(j["bas_dd"])
    return j[["ticker", "bas_dd"]].drop_duplicates()


def market_unit_series() -> pd.DataFrame:
    s = pd.read_csv(os.path.join(LONG, "index/market_unit_series.csv"))
    s["date"] = pd.to_datetime(s["date"])
    return s.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def build(cache: "str | None" = None, *, p_star: "float | None" = None):
    """→ (store, m, kser, info). ``store.bars[t]`` 추가 열 = ``mem tvok tv200 jump lim``."""
    import pickle
    if cache and os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    p1 = load_pass1()
    cal = pd.DatetimeIndex(sorted(p1.bas_dd.unique()))
    calib = calibrate_p_star(p1)
    ps = calib["p_star"] if p_star is None else p_star
    p1["mem"] = member_flags(p1)
    p1["tvok"] = tv_top_flags(p1, ps)
    keep = set(p1.loc[p1.mem, "ticker"])
    etf_brand = p1[p1.name.fillna("").str.contains("KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO")]
    info = {"calib": calib, "p_star_used": ps, "cal": [str(cal[0].date()), str(cal[-1].date()), len(cal)],
            "rows_all": int(len(p1)), "member_tickers": len(keep),
            "etf_brand_rows_in_archive": int(len(etf_brand))}
    flags = p1.loc[p1.ticker.isin(keep), ["ticker", "bas_dd", "mem", "tvok"]]
    del p1
    fs = [os.path.join(UNIFIED, f) for f in sorted(os.listdir(UNIFIED)) if f.endswith(".parquet")]
    arch = pd.concat([pd.read_parquet(f, columns=P2_COLS, filters=[("ticker", "in", sorted(keep))]) for f in fs],
                     ignore_index=True)
    arch["bas_dd"] = pd.to_datetime(arch["bas_dd"])
    arch = arch.merge(flags, on=["ticker", "bas_dd"], how="left")
    arch["mem"] = arch["mem"].fillna(False).astype(bool)
    arch["tvok"] = arch["tvok"].fillna(False).astype(bool)
    arch["tv200"] = (arch.trade_value >= TV_NOMINAL).to_numpy()
    jr = jump_rows()
    jr["jump"] = True
    arch = arch.merge(jr, on=["ticker", "bas_dd"], how="left")
    arch["jump"] = arch["jump"].fillna(False).astype(bool)
    arch["lim"] = limit_for(arch.bas_dd, arch.market)
    # 원천 no_trade 표식도 거래 없는 봉으로(build_store 는 시가 ≤ 0 ∨ 거래량 ≤ 0 만 본다)
    nt = arch.no_trade.fillna(False).astype(bool)
    arch.loc[nt, "volume"] = 0.0
    arch = arch.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)
    info["jump_rows_in_member_tickers"] = int(arch.jump.sum())
    info["jump_rows_on_member_days"] = int((arch.jump & arch.mem).sum())
    st = PN.build_store(arch, db=None, nontrade="flag", junction_rescale=False, cal=cal,
                        extra_cols=("mem", "tvok", "tv200", "jump", "lim"))
    for b in st.bars.values():
        for k in ("mem", "tvok", "tv200", "jump"):
            b[k] = b[k].astype(bool)
        b["lim"] = b["lim"].astype(float)
    mus = market_unit_series()
    m = MU.m_for_days(cal, pd.DatetimeIndex(mus.date), mus.close.to_numpy(float))
    kser = pd.Series(mus.close.to_numpy(float), index=pd.DatetimeIndex(mus.date))
    info["mu_source_split"] = mus.source.str.contains("069500").sum()
    out = (st, m, kser, info)
    if cache:
        with open(cache, "wb") as fh:
            pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return out
