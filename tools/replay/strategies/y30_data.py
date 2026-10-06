"""30년(1996~2026) 재검증 공용 데이터 층 — VCP·BFB 용.

정본 = 메인 세션 30년 규약(``scratchpad/opt/protocol_30y.md``) + 보관소 README
(``data/archive/krx_daily_long/README.md``). 운영 코드 무접촉(연구만).

- 보관소 ``unified/krx_unified_<연도>.parquet`` → 종목별 일봉 배열(공용 ``audit.panel.build_store`` 그대로).
  신호·수익률 = 수정주가(``*_adj``) · 「1주를 살 수 있나」·가격 필터 = 원주가.
- 시대별 가격제한폭(``meta/regime_price_limit.csv``) → 봉마다 ``lim``(비율). 상한가 시가·하한가 잠김 판정에 쓴다.
- 가격제한폭 위반 표시 행(``meta/unified_jump_flags.csv``) → 봉마다 ``jump``. 신호 봉·진입 봉이면 신호 없음,
  보유 구간에 끼면 거래 단위 표본에서 뺀다(개수 보고).
- 시대 중립 유니버스 — 그날 상장 종목(6자리 숫자 · KOSPI/KOSDAQ · 시총 > 0) 중 시총 순위 상위 X% ∧
  거래대금 순위 상위 Y%. X·Y = 운영 문턱(시총 100억 · 거래대금 10억/15억)이 2025 년에 해당하던 비율의
  2025 거래일 평균.
- 시기별 실제 비용(``meta/regime_costs.csv``) — 매수 = 그날 수수료, 매도 = 그날 수수료 + 거래세.
- 시장 유닛 입력 = ``index/market_unit_series.csv``(KOSPI200 지수 × 상수 → 2002-10-14 부터 069500).
"""
from __future__ import annotations

import os
import pickle
import time

import numpy as np
import pandas as pd

from replay.audit import market_unit as MU
from replay.audit import panel as PN

ARCH = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long"
UNIFIED = os.path.join(ARCH, "unified")
CACHE_DIR = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
             "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/opt/bfbvcp")

# 운영 유니버스 문턱(원) — 시대 중립 비율의 기준점
OP_MCAP = 10_000_000_000
OP_TV = {"vcp": 1_000_000_000, "bfb": 1_500_000_000}
REF_YEAR = "2025"

COLS = ["ticker", "name", "bas_dd", "open", "high", "low", "close", "volume", "trade_value", "mktcap", "market",
        "open_adj", "high_adj", "low_adj", "close_adj", "adj_factor"]


# ── 시대 규칙 표 ───────────────────────────────────────────────────────────────

def load_limit_table(path: str = os.path.join(ARCH, "meta/regime_price_limit.csv")) -> "list[tuple]":
    """(시장 0=KOSPI·1=KOSDAQ·None=전체, 시작, 끝, 비율). 정액제(KOSDAQ 1996-07~11) = 8% 로 본다(워밍업 구간)."""
    df = pd.read_csv(path, dtype=str)
    out = []
    for r in df.itertuples():
        mk = {"KOSPI": 0, "KOSDAQ": 1}.get(r.market)
        lim = 0.08 if not str(r.limit_pct).replace(".", "").isdigit() else float(r.limit_pct) / 100.0
        a = pd.Timestamp(r._2)
        b = pd.Timestamp(r.to) if isinstance(r.to, str) and r.to else pd.Timestamp("2100-01-01")
        out.append((mk, a, b, lim))
    return out


def limit_for(mkt: np.ndarray, dates: pd.DatetimeIndex, table) -> np.ndarray:
    """봉마다 가격제한폭 비율. 표에 없으면 0.30."""
    out = np.full(len(dates), np.nan)
    d = pd.DatetimeIndex(dates)
    for mk, a, b, lim in table:
        sel = (d >= a) & (d <= b)
        if mk is not None:
            sel &= (mkt == mk)
        out[sel & np.isnan(out)] = lim
    out[np.isnan(out)] = 0.30
    return out


def load_cost_table(path: str = os.path.join(ARCH, "meta/regime_costs.csv")) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["from"] = pd.to_datetime(df["from"])
    df["to"] = pd.to_datetime(df["to"]).fillna(pd.Timestamp("2100-01-01"))
    return df


class EraCost:
    """날짜 → (한쪽 수수료, 매도 거래세). 비율(소수). ``const`` 가 있으면 왕복 const 를 반반(민감도판)."""

    def __init__(self, cal: pd.DatetimeIndex, table: "pd.DataFrame | None" = None, const: "float | None" = None):
        self.const = const
        n = len(cal)
        self.fee = np.zeros(n)
        self.tax = np.zeros(n)
        if const is None:
            t = load_cost_table() if table is None else table
            for r in t.itertuples():
                sel = (cal >= r._1) & (cal <= r.to)
                self.fee[sel] = r.fee_one_way_pct_assumed / 100.0
                self.tax[sel] = r.sell_tax_kospi_pct / 100.0
        else:
            self.fee[:] = const / 2
            self.tax[:] = 0.0

    def buy(self, gd: int) -> float:
        return float(self.fee[gd])

    def sell(self, gd: int) -> float:
        return float(self.fee[gd] + self.tax[gd])

    def rt(self, gd_in: int, gd_out: int) -> float:
        return self.buy(gd_in) + self.sell(gd_out)


# ── 보관소 적재 ───────────────────────────────────────────────────────────────

def load_unified(years=None) -> pd.DataFrame:
    fs = sorted(f for f in os.listdir(UNIFIED) if f.endswith(".parquet"))
    if years is not None:
        fs = [f for f in fs if int(f[-12:-8]) in years]
    df = pd.concat([pd.read_parquet(os.path.join(UNIFIED, f), columns=COLS) for f in fs], ignore_index=True)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    df["market"] = df["market"].replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    df = df[df.ticker.str.match(r"^\d{6}$") & df.market.isin(["KOSPI", "KOSDAQ"])].copy()
    return df


def universe_ratios(df: pd.DataFrame, ref_year: str = REF_YEAR) -> dict:
    """운영 문턱이 기준 연도에 해당하던 비율(그날 상장 종목 중) 의 거래일 평균."""
    r = df[(df.bas_dd.dt.year == int(ref_year)) & (df.mktcap > 0)]
    g = r.groupby("bas_dd")
    out = {"mcap": float(g.apply(lambda x: (x.mktcap >= OP_MCAP).mean(), include_groups=False).mean())}
    for k, thr in OP_TV.items():
        out[f"tv_{k}"] = float(g.apply(lambda x: (x.trade_value >= thr).mean(), include_groups=False).mean())
    out["ref_days"] = int(g.ngroups)
    return out


def add_rank_cols(df: pd.DataFrame) -> pd.DataFrame:
    """그날 순위 백분위(0=최상위, 1=최하위). 분모 = 그날 시총 > 0 인 종목 수. 시총 0·결측은 1.0(유니버스 밖)."""
    ok = df.mktcap > 0
    n = df[ok].groupby("bas_dd")["ticker"].transform("size")
    df["mc_pct"] = 1.0
    df["tv_pct"] = 1.0
    df.loc[ok, "mc_pct"] = df[ok].groupby("bas_dd")["mktcap"].rank(ascending=False, method="max") / n
    df.loc[ok, "tv_pct"] = df[ok].groupby("bas_dd")["trade_value"].rank(ascending=False, method="max") / n
    return df


def add_jump_and_limit(df: pd.DataFrame) -> pd.DataFrame:
    jf = pd.read_csv(os.path.join(ARCH, "meta/unified_jump_flags.csv"), dtype={"ticker": str})
    key = set(jf.ticker + "|" + pd.to_datetime(jf.bas_dd).dt.strftime("%Y-%m-%d"))
    df["jump"] = (df.ticker + "|" + df.bas_dd.dt.strftime("%Y-%m-%d")).isin(key).to_numpy()
    mk = np.where(df.market.to_numpy() == "KOSPI", 0, 1)
    df["lim"] = limit_for(mk, pd.DatetimeIndex(df.bas_dd), load_limit_table())
    return df


def build(cache: bool = True):
    """→ (Store, meta). Store.bars[t] 에 공용 키 + ``mc_pct``·``tv_pct``·``jump``·``lim``."""
    path = os.path.join(CACHE_DIR, "y30_store.pkl")
    if cache and os.path.exists(path):
        with open(path, "rb") as fh:
            return pickle.load(fh)
    t0 = time.time()
    df = load_unified()
    ratios = universe_ratios(df)
    df = add_rank_cols(df)
    df = add_jump_and_limit(df)
    st = PN.build_store(df, db=None, nontrade="flag", junction_rescale=False,
                        extra_cols=("mc_pct", "tv_pct", "jump", "lim"))
    for b in st.bars.values():
        b["jump"] = b["jump"].astype(bool)
        b["mc_pct"] = b["mc_pct"].astype(float)
        b["tv_pct"] = b["tv_pct"].astype(float)
        b["lim"] = b["lim"].astype(float)
    meta = {"ratios": ratios, "rows": int(len(df)), "tickers": len(st.bars), "cal": [str(st.cal[0].date()),
                                                                                     str(st.cal[-1].date())],
            "n_days": len(st.cal), "jump_rows": int(df.jump.sum()), "build_s": time.time() - t0}
    out = (st, meta)
    if cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return out


def market_unit(cal: pd.DatetimeIndex) -> "tuple[np.ndarray, pd.Series]":
    """체결일별 m(D−1 봉 규약, 운영 classify) + 기준선 종가 계열."""
    s = pd.read_csv(os.path.join(ARCH, "index/market_unit_series.csv"), parse_dates=["date"])
    s = s.dropna(subset=["close"]).sort_values("date")
    m = MU.m_for_days(cal, pd.DatetimeIndex(s.date), s.close.to_numpy(float))
    return m, pd.Series(s.close.to_numpy(float), index=pd.DatetimeIndex(s.date))


def universe(st, ratios: dict, kind: str, *, mode: str = "pct", price_filter=(3_000, 500_000)) -> dict:
    """신호 봉 기준 유니버스. ``pct`` = 시대 중립(판정) · ``nominal`` = 운영 원화 문턱 그대로(재현 확인·보고)."""
    lo, hi = price_filter
    out = {}
    X = ratios["mcap"]
    Y = ratios[f"tv_{kind}"]
    for t, b in st.bars.items():
        base = (b["c_raw"] >= lo) & (b["c_raw"] <= hi) & ~b["notrade"] & ~b["jump"]
        if mode == "pct":
            out[t] = base & (b["mc_pct"] <= X) & (b["tv_pct"] <= Y)
        else:
            with np.errstate(invalid="ignore"):
                out[t] = base & np.nan_to_num(b["mktcap"] >= OP_MCAP).astype(bool) & (b["tv"] >= OP_TV[kind])
    return out


def bench_stats(bench: pd.Series, m: np.ndarray, cal: pd.DatetimeIndex, win) -> dict:
    """기준선 — 지수(KOSPI200 → 069500) 단순 보유 · 시장 유닛 m 비례 보유(m 결측 = 1.0, 비용 없음)."""
    a, b = pd.Timestamp(win[0]), pd.Timestamp(win[1])
    s = bench[(bench.index >= a) & (bench.index <= b)]
    px = s.to_numpy(float)
    r = px[1:] / px[:-1] - 1
    mi = pd.Series(m, index=cal).reindex(s.index).to_numpy(float)[1:]
    mi = np.where(np.isfinite(mi), mi, 1.0)
    out = {}
    for nm, rr in (("hold", r), ("m_hold", r * mi)):
        eq = np.concatenate([[1.0], np.cumprod(1 + rr)])
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        out[nm] = {"cagr": float(eq[-1] ** (1 / yrs) - 1) if yrs > 0 else float("nan"),
                   "mdd": float((eq / np.maximum.accumulate(eq) - 1).min())}
    return out
