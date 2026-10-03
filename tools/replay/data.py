"""재현 틀 — 데이터 층 (보관소 로더 + DB 추출본 로더 + KOSPI 근사 지수).

- 보관소 = ``data/archive/krx_daily/parquet/krx_daily_YYYY.parquet``(git 밖, 읽기만). 수정본
  (``*_adj``)과 원본이 같은 행에 있다 — 신호·수익률은 수정본, 「1주를 살 수 있나」는 원본 시가.
- DB 추출본 = ``tools/replay/extract_db.py`` 출력(JSON Lines gzip). 네트워크·DB 접속 없음.
- KOSPI 근사 지수 = KOSPI 종목 전일 시총 가중 일간수익률을 쌓은 것(cycle375 §9 와 같은 정의,
  그 스크래치가 남아 있지 않아 여기서 다시 만든다).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass, field

import numpy as np

ARCHIVE_DIR = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily"
KOSPI_BASE_2020_10_05 = 2358.00  # 지수 시작값(실제 KOSPI 2020-10-05 종가) — 수준 맞추기용일 뿐


def sha256_16(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


@dataclass
class Panel:
    """날짜 × 종목 행렬. 결측 = NaN."""

    dates: np.ndarray              # datetime64[D]
    tickers: list
    names: dict
    market: dict                   # ticker → "KOSPI"|"KOSDAQ"
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    o_raw: np.ndarray
    c_raw: np.ndarray
    vol: np.ndarray
    tv: np.ndarray
    mktcap: np.ndarray
    meta: dict = field(default_factory=dict)


def load_archive(archive_dir: str = ARCHIVE_DIR) -> Panel:
    import pandas as pd

    pdir = os.path.join(archive_dir, "parquet")
    files = sorted(f for f in os.listdir(pdir) if f.endswith(".parquet"))
    cols = ["ticker", "name", "bas_dd", "open", "close", "volume", "trade_value", "mktcap",
            "market", "open_adj", "high_adj", "low_adj", "close_adj"]
    df = pd.concat([pd.read_parquet(os.path.join(pdir, f), columns=cols) for f in files],
                   ignore_index=True)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"]).dt.normalize()
    dates = np.array(sorted(df["bas_dd"].unique()), dtype="datetime64[D]")
    tickers = sorted(df["ticker"].unique())
    di = {d: i for i, d in enumerate(dates)}
    ti = {t: j for j, t in enumerate(tickers)}
    r = df["bas_dd"].values.astype("datetime64[D]")
    ri = np.fromiter((di[x] for x in r), dtype=np.int64, count=len(r))
    ci = df["ticker"].map(ti).values
    shape = (len(dates), len(tickers))

    def mat(col):
        m = np.full(shape, np.nan)
        m[ri, ci] = df[col].values.astype(float)
        return m

    last = df.sort_values("bas_dd").groupby("ticker").tail(1)
    names = dict(zip(last["ticker"], last["name"]))
    market = {t: ("KOSPI" if "KOSPI" in str(m).upper() and "KOSDAQ" not in str(m).upper()
                  else "KOSDAQ") for t, m in zip(last["ticker"], last["market"])}
    p = Panel(dates=dates, tickers=tickers, names=names, market=market,
              o=mat("open_adj"), h=mat("high_adj"), l=mat("low_adj"), c=mat("close_adj"),
              o_raw=mat("open"), c_raw=mat("close"), vol=mat("volume"), tv=mat("trade_value"),
              mktcap=mat("mktcap"))
    for f in ("o", "h", "l", "c", "o_raw", "c_raw"):
        m = getattr(p, f)
        m[m <= 0] = np.nan
    p.meta = dict(source="archive", files={f: sha256_16(os.path.join(pdir, f)) for f in files},
                  rows=int(len(df)), dates=len(dates), tickers=len(tickers),
                  first=str(dates[0]), last=str(dates[-1]),
                  market_values=sorted(map(str, df["market"].unique())))
    return p


def kospi_approx_index(p: Panel, base: float = KOSPI_BASE_2020_10_05) -> np.ndarray:
    """KOSPI 종목 전일 시총 가중 일간수익률 누적. 첫날 = ``base``."""
    mask = np.array([p.market.get(t) == "KOSPI" for t in p.tickers])
    c = p.c[:, mask]
    cap = p.mktcap[:, mask]
    out = np.full(len(p.dates), np.nan)
    out[0] = base
    for i in range(1, len(p.dates)):
        r = c[i] / c[i - 1] - 1.0
        w = cap[i - 1]
        ok = np.isfinite(r) & np.isfinite(w) & (w > 0)
        rr = np.sum(w[ok] * r[ok]) / np.sum(w[ok]) if ok.any() else 0.0
        out[i] = out[i - 1] * (1.0 + rr)
    return out


# ── DB 추출본 ────────────────────────────────────────────────────────────────

def load_db_extract(path: str):
    """JSON Lines gzip → {section: (cols, rows)}."""
    out: dict = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            sec = d["section"]
            if "cols" in d:
                out.setdefault(sec, [d["cols"], []])[0] = d["cols"]
            elif "row" in d:
                out.setdefault(sec, [None, []])[1].append(d["row"])
    return out


def db_panel(ext: dict) -> Panel:
    cols, rows = ext["daily"]
    ix = {c: i for i, c in enumerate(cols)}
    dates = np.array(sorted({r[ix["bas_dd"]][:10] for r in rows}), dtype="datetime64[D]")
    tickers = sorted({r[ix["ticker"]] for r in rows})
    di = {str(d): i for i, d in enumerate(dates)}
    ti = {t: j for j, t in enumerate(tickers)}
    shape = (len(dates), len(tickers))
    m = {k: np.full(shape, np.nan) for k in ("o", "h", "l", "c", "vol", "tv", "chg")}
    upd = np.full(shape, np.nan)
    for r in rows:
        i, j = di[r[ix["bas_dd"]][:10]], ti[r[ix["ticker"]]]
        m["o"][i, j] = r[ix["open_price"]]
        m["h"][i, j] = r[ix["high_price"]]
        m["l"][i, j] = r[ix["low_price"]]
        m["c"][i, j] = r[ix["close_price"]]
        m["vol"][i, j] = r[ix["volume"]]
        m["tv"][i, j] = r[ix["trade_value"]]
        m["chg"][i, j] = r[ix["change_rate"]] if r[ix["change_rate"]] is not None else np.nan
    for k in ("o", "h", "l", "c"):
        m[k][m[k] <= 0] = np.nan
    mcols, mrows = ext["master"]
    mx = {c: i for i, c in enumerate(mcols)}
    names, market, grp = {}, {}, {}
    for r in mrows:
        t = r[mx["ticker"]]
        names[t] = r[mx["name"]] or ""
        mk = (r[mx["mket_id_cd"]] or "").upper()
        ex = (r[mx["excg_dvsn_cd"]] or "").upper()
        # CTPF1002R mket_id_cd(STK=KOSPI · KSQ=KOSDAQ)가 정본. 운영 실측 excg_dvsn_cd 는
        # 02=KOSPI · 03=KOSDAQ 이다(2026-10-04 추출본 — 005930=02/STK, 247540=03/KSQ).
        market[t] = ("KOSPI" if mk == "STK" else "KOSDAQ" if mk == "KSQ" else
                     "KOSPI" if ex == "02" else "KOSDAQ" if ex == "03" else "")
        grp[t] = r[mx["scty_grp_id_cd"]]
    p = Panel(dates=dates, tickers=tickers, names=names, market=market,
              o=m["o"], h=m["h"], l=m["l"], c=m["c"], o_raw=m["o"].copy(), c_raw=m["c"].copy(),
              vol=m["vol"], tv=m["tv"], mktcap=np.full(shape, np.nan))
    p.meta = dict(source="db", dates=len(dates), tickers=len(tickers), first=str(dates[0]),
                  last=str(dates[-1]), rows=len(rows), group_code=grp)
    p.meta["chg"] = m["chg"]
    return p


def provisional_close_flags(p: Panel, cutoff: str = "2026-09-28") -> np.ndarray:
    """§3.2 잠정 종가 의심 행 — ``close_t`` vs ``close_{t+1}/(1+chg_{t+1}/100)`` 차이 > 1틱.

    ``chg`` = ``_derive_change_rate``(``prdy_vrss`` ÷ 전일종가 × 100, 소수 4자리 반올림 저장)
    라 역산값에 반올림 오차가 있다 — 허용 오차 = max(1틱, 역산 반올림 오차).
    """
    chg = p.meta["chg"]
    c = p.c
    flags = np.zeros(c.shape, dtype=bool)
    cut = np.datetime64(cutoff)
    for i in range(len(p.dates) - 1):
        if p.dates[i] >= cut:
            break
        implied = c[i + 1] / (1.0 + chg[i + 1] / 100.0)
        tick = np.vectorize(krx_tick)(np.nan_to_num(c[i], nan=1000.0))
        round_err = c[i + 1] * 0.00005 / 100.0 * 100.0 + 1e-9  # 4자리 반올림 → 상대 5e-7
        tol = np.maximum(tick, np.abs(implied) * 5e-7 + round_err)
        bad = np.isfinite(implied) & np.isfinite(c[i]) & (np.abs(c[i] - implied) > tol)
        flags[i] = bad
    return flags


def krx_tick(price: float) -> float:
    """2023-01-25 이후 KRX 호가 단위(KOSPI·KOSDAQ 공통)."""
    if price < 2000:
        return 1
    if price < 5000:
        return 5
    if price < 20000:
        return 10
    if price < 50000:
        return 50
    if price < 200000:
        return 100
    if price < 500000:
        return 500
    return 1000
