"""30년 재검증(평균회귀·장세) — 데이터 층. 연구 전용 · 운영 코드 무접촉(읽기 import 만).

규약 = 스크래치 ``opt/protocol_30y.md``(1996~2026 단일 보관소 · 3분할 · 시기별 비용 · 시대 중립 유니버스).
보관소 = ``data/archive/krx_daily_long/``(git 밖, 읽기만). 정본 = ``unified/`` · 지수 = ``index/market_unit_series.csv``.

- 패널 = (종목 × 날짜) float32 행렬(종목마다 연속 메모리 — 작업자가 한 종목씩 꺼내 float64 로 바꾼다).
- 신호·수익률 = 수정주가(``*_adj``), 「1주를 살 수 있나」 = 원본 시가.
- 가격제한폭 = ``meta/regime_price_limit.csv``(시장·시행일별). 상한가 시가 매수 불가 = 시가 ≥ 전일 종가 × (1 + 폭 − 1%p),
  하한가 잠김 = 시가 ≤ 전일 종가 × (1 − 폭 + 1%p) ∧ 고가 = 저가. (30% 시절의 1.29 · 0.71 과 같은 꼴.)
- 가격제한폭 위반 표시 행(``meta/unified_jump_flags.csv``) = 그 행을 「멈춤(halt)」 으로 본다 — 규약 「위반 표시 행 제외」.
- 왕복 비용 = ``meta/regime_costs.csv`` 의 그날 값(거래당 = 진입일 값/2 + 청산일 값/2).
- 유니버스(시대 중립) = 그날 시총 순위 상위 p(2025 년에 「시총 500억 이상」 이 차지하던 비율의 평균).
- 시장 유닛 = ``src.engine.market_unit.classify`` 그대로, 입력 = 연속 계열 종가, 체결일 d 는 d−1 종가까지.
- 6장세 = ``src.engine.market_regime_label.session_labels`` 그대로(D 라벨 = D−1 종가까지).
"""
from __future__ import annotations

import bisect
import glob
import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import date

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine.etf_like import is_etf_like  # noqa: E402  (라이브 판정 그대로)

LONG_DIR = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long"

T_WIN = ("1997-01-02", "2012-12-28")
V_WIN = ("2013-01-02", "2020-12-30")
H_WIN = ("2021-01-04", "2026-10-02")
SEGS = (("T", T_WIN), ("V", V_WIN), ("H", H_WIN))
ERAS = (("1997-2001", ("1997-01-01", "2001-12-31")), ("2002-2006", ("2002-01-01", "2006-12-31")),
        ("2007-2011", ("2007-01-01", "2011-12-31")), ("2012-2016", ("2012-01-01", "2016-12-31")),
        ("2017-2021", ("2017-01-01", "2021-12-31")), ("2022-2026", ("2022-01-01", "2026-12-31")))
T_SUB = (("1997-01-02", "2001-12-28"), ("2002-01-02", "2007-12-28"), ("2008-01-02", "2012-12-28"))
REF_MKTCAP_WON = 50_000_000_000      # 500억 — 현행 선(2025 년 기준 백분위로 바꿔 전 기간 적용)
REF_TV_WON = 1_000_000_000           # 10억
REF_YEAR = 2025
FLAT_COST = 0.0038


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 비용 · 가격제한폭 (순수 함수) ─────────────────────────────────────────────

def load_cost_table(path: str = os.path.join(LONG_DIR, "meta", "regime_costs.csv")) -> "list[tuple[str, float]]":
    """[(시작일 ISO, 왕복 비용 비율)] 오름차순."""
    import csv
    out = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append((r["from"], float(r["round_trip_pct_assumed"]) / 100.0))
    out.sort()
    return out


def cost_on(day_iso: str, table: "list[tuple[str, float]]") -> float:
    """그날 적용 왕복 비용. 표의 첫 시작일보다 앞이면 첫 값."""
    starts = [s for s, _ in table]
    i = bisect.bisect_right(starts, day_iso) - 1
    return table[max(i, 0)][1]


def load_limit_table(path: str = os.path.join(LONG_DIR, "meta", "regime_price_limit.csv")):
    """{시장: [(시작일, 폭)]}. 「정액제」(KOSDAQ 1996-07~11) = 8%로 근사(그 구간은 워밍업 전용)."""
    import csv
    out: dict = {"KOSPI": [], "KOSDAQ": []}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v = r["limit_pct"].strip()
            pct = 0.08 if not v.replace(".", "").isdigit() else float(v) / 100.0
            mk = r["market"].strip()
            for m in (("KOSPI", "KOSDAQ") if mk == "ALL" else (mk,)):
                out[m].append((r["from"], pct))
    for m in out:
        out[m].sort()
    return out


def limit_on(day_iso: str, market: str, table) -> float:
    key = "KOSDAQ" if "KOSDAQ" in market.upper() else "KOSPI"
    rows = table[key]
    starts = [s for s, _ in rows]
    i = bisect.bisect_right(starts, day_iso) - 1
    return rows[max(i, 0)][1]


def limit_up_mult(lim: float) -> float:
    """상한가 시가 매수 불가 배수(30% 시절 1.29 와 같은 꼴)."""
    return 1.0 + lim - 0.01


def limit_down_mult(lim: float) -> float:
    return 1.0 - lim + 0.01


# ── 유니버스 백분위 ───────────────────────────────────────────────────────────

def share_at_or_above(values: np.ndarray, threshold: float) -> float:
    v = values[np.isfinite(values) & (values > 0)]
    return float(np.mean(v >= threshold)) if len(v) else float("nan")


def top_share_mask(values: np.ndarray, share: float) -> np.ndarray:
    """한 날의 값 배열 → 상위 ``share`` 비율 bool(결측·0 = False). 순위 = 내림차순 1..n, 자격 = 순위 ≤ ceil(share·n)."""
    out = np.zeros(len(values), dtype=bool)
    ok = np.isfinite(values) & (values > 0)
    n = int(ok.sum())
    if n == 0:
        return out
    k = int(np.ceil(share * n))
    idx = np.where(ok)[0]
    order = idx[np.argsort(-values[idx], kind="mergesort")]
    out[order[:k]] = True
    return out


# ── 패널 ──────────────────────────────────────────────────────────────────────

@dataclass
class Panel30:
    dates: np.ndarray                 # datetime64[D]
    tickers: list
    names: dict
    o: np.ndarray                     # (종목, 날짜) float32 수정
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    o_raw: np.ndarray
    c_raw: np.ndarray
    tv: np.ndarray
    mktcap: np.ndarray
    notrade: np.ndarray               # bool — 거래 없음·결측
    flag: np.ndarray                  # bool — 가격제한폭 위반 표시 행
    kosdaq: np.ndarray                # bool — 그날 소속이 KOSDAQ
    meta: dict = field(default_factory=dict)


def load_panel(long_dir: str = LONG_DIR) -> Panel30:
    import pandas as pd

    files = sorted(glob.glob(os.path.join(long_dir, "unified", "krx_unified_*.parquet")))
    cols = ["ticker", "name", "bas_dd", "open", "close", "volume", "trade_value", "mktcap", "market",
            "open_adj", "high_adj", "low_adj", "close_adj", "no_trade"]
    parts = []
    for f in files:
        d = pd.read_parquet(f, columns=cols)
        d = d[d["ticker"].str.len().eq(6) & d["ticker"].str.isdigit()]
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    del parts
    df["bas_dd"] = df["bas_dd"].dt.normalize()
    last = df.sort_values("bas_dd").groupby("ticker").tail(1)
    names = dict(zip(last["ticker"], last["name"]))
    etf = {t for t, nm in names.items() if is_etf_like(None, nm or "")}
    df = df[~df["ticker"].isin(etf)]
    dates = np.array(sorted(df["bas_dd"].unique()), dtype="datetime64[D]")
    tickers = sorted(df["ticker"].unique())
    di = {d: i for i, d in enumerate(dates)}
    ti = {t: j for j, t in enumerate(tickers)}
    ri = np.fromiter((di[x] for x in df["bas_dd"].values.astype("datetime64[D]")), dtype=np.int64, count=len(df))
    ci = df["ticker"].map(ti).to_numpy()
    shape = (len(tickers), len(dates))

    def mat(col, dtype=np.float32, fill=np.nan):
        m = np.full(shape, fill, dtype=dtype)
        m[ci, ri] = df[col].to_numpy().astype(dtype)
        return m

    p = Panel30(dates=dates, tickers=tickers, names={t: names.get(t, "") for t in tickers},
                o=mat("open_adj"), h=mat("high_adj"), l=mat("low_adj"), c=mat("close_adj"),
                o_raw=mat("open"), c_raw=mat("close"), tv=mat("trade_value"), mktcap=mat("mktcap"),
                notrade=np.ones(shape, dtype=bool), flag=np.zeros(shape, dtype=bool),
                kosdaq=np.zeros(shape, dtype=bool))
    vol = df["volume"].to_numpy()
    nt = df["no_trade"].to_numpy().astype(bool) | ~(np.nan_to_num(vol) > 0)
    p.notrade[ci, ri] = nt
    p.kosdaq[ci, ri] = df["market"].str.upper().str.contains("KOSDAQ").to_numpy()
    for f in ("o", "h", "l", "c", "o_raw", "c_raw"):
        m = getattr(p, f)
        m[~(m > 0)] = np.nan
    p.notrade |= ~np.isfinite(p.c) | ~np.isfinite(p.o)
    jf = pd.read_csv(os.path.join(long_dir, "meta", "unified_jump_flags.csv"), dtype={"ticker": str},
                     parse_dates=["bas_dd"])
    n_flag = 0
    for t, d in zip(jf["ticker"], jf["bas_dd"].values.astype("datetime64[D]")):
        if t in ti and d in di:
            p.flag[ti[t], di[d]] = True
            n_flag += 1
    p.meta = dict(files={os.path.basename(f): sha256(f)[:16] for f in files}, rows=int(len(df)),
                  dates=len(dates), tickers=len(tickers), first=str(dates[0]), last=str(dates[-1]),
                  etf_like_excluded=len(etf), flag_rows=n_flag)
    return p


def limit_matrix(p: Panel30, table=None) -> np.ndarray:
    """(종목, 날짜) float32 가격제한폭."""
    table = table or load_limit_table()
    iso = [str(d) for d in p.dates]
    kp = np.array([limit_on(s, "KOSPI", table) for s in iso], dtype=np.float32)
    kq = np.array([limit_on(s, "KOSDAQ", table) for s in iso], dtype=np.float32)
    return np.where(p.kosdaq, kq[None, :], kp[None, :]).astype(np.float32)


def cost_vector(dates: np.ndarray, table=None) -> np.ndarray:
    table = table or load_cost_table()
    return np.array([cost_on(str(d), table) for d in dates])


def universe_shares(p: Panel30, year: int = REF_YEAR) -> dict:
    yr = p.dates.astype("datetime64[Y]").astype(int) + 1970
    cols = np.where(yr == year)[0]
    cap = [share_at_or_above(p.mktcap[:, i].astype(float), REF_MKTCAP_WON) for i in cols]
    tv = [share_at_or_above(p.tv[:, i].astype(float), REF_TV_WON) for i in cols]
    return {"year": year, "days": int(len(cols)), "mktcap_share": float(np.nanmean(cap)),
            "tv_share": float(np.nanmean(tv)), "mktcap_share_min": float(np.nanmin(cap)),
            "mktcap_share_max": float(np.nanmax(cap)), "tv_share_min": float(np.nanmin(tv)),
            "tv_share_max": float(np.nanmax(tv))}


def eligible_matrix(values: np.ndarray, share: float) -> np.ndarray:
    out = np.zeros(values.shape, dtype=bool)
    for i in range(values.shape[1]):
        out[:, i] = top_share_mask(values[:, i].astype(float), share)
    return out


# ── 시장 연속 계열 · 시장 유닛 · 6장세 ─────────────────────────────────────────

def load_market_series(long_dir: str = LONG_DIR):
    import pandas as pd
    m = pd.read_csv(os.path.join(long_dir, "index", "market_unit_series.csv"), parse_dates=["date"])
    return m["date"].values.astype("datetime64[D]"), m["close"].to_numpy(dtype=float), m["source"].tolist()


def market_unit_by_session(s_dates: np.ndarray, s_close: np.ndarray, sessions: np.ndarray) -> np.ndarray:
    """세션 d 의 시장 유닛 m = classify(d 보다 앞선 연속 계열 종가) — D−1 규약. 결측 = NaN."""
    from src.engine.market_unit import classify
    out = np.full(len(sessions), np.nan)
    pos = np.searchsorted(s_dates, sessions, side="left")      # d 보다 앞선 종가 개수
    closes = list(s_close)
    cache = {}
    for i, k in enumerate(pos):
        if k not in cache:
            cl, _why = classify(closes[:k])
            cache[k] = cl.m if cl is not None else np.nan
        out[i] = cache[k]
    return out


def regime_by_session(s_dates: np.ndarray, s_close: np.ndarray, sessions: np.ndarray) -> np.ndarray:
    """세션 d 의 6장세 코드 1..6(0 = 없음). 코드 = 1 안정상승 2 변동상승 3 안정횡보 4 변동횡보 5 안정하락 6 변동하락."""
    from src.engine.market_regime_label import session_labels
    code = {"stable_up": 1, "volatile_up": 2, "stable_flat": 3, "volatile_flat": 4,
            "stable_down": 5, "volatile_down": 6}
    ds = [date.fromisoformat(str(d)) for d in s_dates]
    # 세션 날짜 목록 = 연속 계열 날짜 + (마지막 다음 세션 없음). D 라벨 = D−1 종가까지.
    labs = session_labels(ds, list(s_close))
    lab_of = {}
    for d, pt in labs:
        lab_of[np.datetime64(d, "D")] = code[pt.label]
    return np.array([lab_of.get(d, 0) for d in sessions], dtype=np.int64)


def seg_bounds(dates: np.ndarray, win) -> "tuple[int, int]":
    a = int(np.searchsorted(dates, np.datetime64(win[0]), side="left"))
    b = int(np.searchsorted(dates, np.datetime64(win[1]), side="right")) - 1
    return a, b


def seg_index(dates: np.ndarray) -> np.ndarray:
    """날짜 → 0=T 1=V 2=H, −1 = 워밍업/밖."""
    out = np.full(len(dates), -1, dtype=np.int8)
    for k, (_n, w) in enumerate(SEGS):
        a, b = seg_bounds(dates, w)
        out[a:b + 1] = k
    return out
