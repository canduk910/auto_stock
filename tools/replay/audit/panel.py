"""데이터 층 — 보관소(주식·ETF) + DB 추출본 → 종목별 일봉 배열(전역 달력 인덱스 ``di``).

배열 키(종목마다, 날짜 오름차순):
- ``di``  전역 달력 인덱스 · ``o h l c`` 수정주가(신호·수익률용, D-1) · ``o_raw c_raw`` 원본(「1주를 살 수 있나」)
- ``raw`` = 원본 시가 ÷ 수정 시가(수정가 → 원화 환산 배율) · ``tv vol`` 거래대금·거래량(원본)
- ``mktcap`` 그날 시총(원, 보관소) · ``mkt`` 0=KOSPI 1=KOSDAQ 2=기타 · ``src`` 0=보관소 1=DB · ``notrade`` 거래 없는 봉

거래 없는 봉 처리(``nontrade``):
- ``"flag"`` — 남기고 표식. 시가·고가·저가를 종가로 채운다(cycle405 ``c405_data``)
- ``"drop"`` — 원본 시가·고가·저가·종가 중 하나라도 0 이하인 봉을 뺀다(cycle391 ``build_ticker_cal``)

이음매(``junction_rescale``): 보관소 마지막 수정 종가와 DB 첫 시가가 25% 넘게 벌어지면 보관소 쪽을
비율로 맞춘다(DB 는 원본=수정 동일 취급이라 그 뒤 권리락을 모른다 — cycle405 와 같다).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C

ARCH_COLS = ["ticker", "name", "bas_dd", "open", "high", "low", "close", "volume", "trade_value",
             "mktcap", "market", "open_adj", "high_adj", "low_adj", "close_adj", "adj_factor"]


@dataclass
class Store:
    cal: pd.DatetimeIndex
    bars: dict
    names: dict
    meta: dict = field(default_factory=dict)


def sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def check_archive(dir_: str, expect: dict) -> dict:
    got = {f: sha256(os.path.join(dir_, f)) for f in sorted(expect)}
    bad = {f: (got[f], expect[f]) for f in expect if got[f] != expect[f]}
    if bad:
        raise SystemExit(f"[audit] 보관소 sha256 불일치 — 멈춘다: {bad}")
    return got


def load_archive(dir_: str, end: "str | None" = None, columns=ARCH_COLS) -> pd.DataFrame:
    fs = sorted(f for f in os.listdir(dir_) if f.endswith(".parquet"))
    df = pd.concat([pd.read_parquet(os.path.join(dir_, f), columns=columns) for f in fs], ignore_index=True)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    if end is not None:
        df = df[df.bas_dd <= pd.Timestamp(end)]
    return df


def db_daily_frame(ext: dict, start: str, end: str) -> pd.DataFrame:
    """``extract_audit_db.py`` 추출본의 ``daily`` 섹션 → 보관소와 같은 열 이름(원본=수정)."""
    cols, rows = ext["daily"]
    df = pd.DataFrame(rows, columns=cols)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"].str[:10])
    df = df[(df.bas_dd >= pd.Timestamp(start)) & (df.bas_dd <= pd.Timestamp(end))]
    return df.rename(columns={"open_price": "open", "high_price": "high", "low_price": "low",
                              "close_price": "close", "trade_value": "trade_value"})


def _mkt_code(m) -> int:
    s = str(m).upper()
    if "KOSDAQ" in s:
        return 1
    if "KOSPI" in s:
        return 0
    return 2


def build_store(arch: pd.DataFrame, *, db: "pd.DataFrame | None" = None, nontrade: str = "flag",
                junction_rescale: bool = True, cal: "pd.DatetimeIndex | None" = None,
                tickers: "set | None" = None, extra_cols: "tuple[str, ...]" = ()) -> Store:
    """``extra_cols`` = 보관소·DB 프레임에 미리 붙여 둔 열(예: 전략의 지수 편입 근사 ``mem``)을 그대로 싣는다."""
    if tickers is not None:
        arch = arch[arch.ticker.isin(tickers)]
        if db is not None:
            db = db[db.ticker.isin(tickers)]
    if cal is None:
        days = set(arch.bas_dd.unique())
        if db is not None:
            days |= set(db.bas_dd.unique())
        cal = pd.DatetimeIndex(sorted(days))
    di_map = pd.Series(np.arange(len(cal)), index=cal)
    arch_g = {t: g for t, g in arch.groupby("ticker", sort=True)}
    db_g = {t: g for t, g in db.groupby("ticker", sort=True)} if db is not None else {}
    bars, rescaled = {}, 0
    for t in sorted(set(arch_g) | set(db_g)):
        parts = []
        ga = arch_g.get(t)
        if ga is not None:
            ga = ga.sort_values("bas_dd")
            if nontrade == "drop":
                ga = ga[(ga.open > 0) & (ga.high > 0) & (ga.low > 0) & (ga.close > 0)]
            if len(ga):
                oa = ga.open_adj.to_numpy(float)
                parts.append(pd.DataFrame({
                    "d": ga.bas_dd.values, "o": oa, "h": ga.high_adj.to_numpy(float),
                    "l": ga.low_adj.to_numpy(float), "c": ga.close_adj.to_numpy(float),
                    "o_raw": ga.open.to_numpy(float), "c_raw": ga.close.to_numpy(float),
                    "raw": ga.open.to_numpy(float) / np.where(oa > 0, oa, np.nan),
                    "tv": ga.trade_value.to_numpy(float), "vol": ga.volume.to_numpy(float),
                    "mktcap": ga.mktcap.to_numpy(float), "mkt": [_mkt_code(m) for m in ga.market],
                    "src": 0, **{x: ga[x].to_numpy() for x in extra_cols}}))
        gd = db_g.get(t)
        if gd is not None:
            gd = gd.sort_values("bas_dd")
            if nontrade == "drop":
                gd = gd[(gd.open > 0) & (gd.high > 0) & (gd.low > 0) & (gd.close > 0)]
            if len(gd):
                parts.append(pd.DataFrame({
                    "d": gd.bas_dd.values, "o": gd.open.to_numpy(float), "h": gd.high.to_numpy(float),
                    "l": gd.low.to_numpy(float), "c": gd.close.to_numpy(float),
                    "o_raw": gd.open.to_numpy(float), "c_raw": gd.close.to_numpy(float),
                    "raw": np.ones(len(gd)), "tv": gd.trade_value.to_numpy(float),
                    "vol": gd.volume.to_numpy(float), "mktcap": np.full(len(gd), np.nan),
                    "mkt": 2, "src": 1, **{x: gd[x].to_numpy() for x in extra_cols}}))
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True)
        if (junction_rescale and ga is not None and gd is not None and len(ga) and len(gd)):
            last_a = float(ga.close_adj.to_numpy()[-1])
            first_d = float(gd.open.to_numpy()[0]) if gd.open.to_numpy()[0] > 0 else float(gd.close.to_numpy()[0])
            if last_a > 0 and first_d > 0 and abs(np.log(first_d / last_a)) > 0.25:
                k = first_d / last_a
                msk = df.src == 0
                for col in ("o", "h", "l", "c"):
                    df.loc[msk, col] = df.loc[msk, col] * k
                df.loc[msk, "raw"] = df.loc[msk, "raw"] / k
                rescaled += 1
        if nontrade == "flag":
            nt = (df.o <= 0) | (df.vol <= 0)
            for col in ("o", "h", "l"):
                df.loc[nt, col] = df.loc[nt, "c"]
            df["notrade"] = nt.values
        else:
            df["notrade"] = False
        df["di"] = di_map.loc[pd.DatetimeIndex(df.d.values)].to_numpy()
        bars[t] = {k: df[k].to_numpy() for k in ("di", "o", "h", "l", "c", "o_raw", "c_raw", "raw", "tv",
                                                 "vol", "mktcap", "mkt", "src", "notrade") + tuple(extra_cols)}
        bars[t]["notrade"] = bars[t]["notrade"].astype(bool)
    names = arch.drop_duplicates("ticker", keep="last").set_index("ticker")["name"].to_dict()
    return Store(cal=cal, bars=bars, names=names,
                 meta={"junction_rescaled": rescaled, "tickers": len(bars), "cal": [str(cal[0].date()),
                                                                                    str(cal[-1].date())]})


def load_db_extract(path: str = C.DB_EXTRACT) -> dict:
    """JSON Lines gzip → {section: (cols, rows)}."""
    import gzip
    import json
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
