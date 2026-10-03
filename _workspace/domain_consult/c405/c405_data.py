"""cycle405 — 재현 데이터 준비 (읽기 전용 입력 → 스크래치 pkl).

입력
- KRX 일봉 보관소 parquet 2020-10-05 ~ 2025-10-02 (수정주가, 상장폐지 포함, 읽기 전용)
- KRX ETF 보관소 parquet 의 069500(KODEX 200) — 시장 유닛 원천(운영과 같은 종목)
- 운영 DB stock_master_daily · stock_master 덤프(2026-10-03 07:05 KST, BEGIN READ ONLY) — H 구간

출력 (스크래치 c405/)
- c405_panel.pkl : 종목별 배열 + 전역 달력 + 069500 시장 유닛 상태
"""
from __future__ import annotations

import glob
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ARCH = Path("/Users/koscom/Projects/auto_stock/data/archive/krx_daily/parquet")
ETF = Path("/Users/koscom/Projects/auto_stock/data/archive/krx_etf_daily/parquet")
SCR = Path("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
           "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/c405")
DB_DUMP = SCR / "db_dump.tsv"
ARCH_END = pd.Timestamp("2025-10-02")
DB_START = pd.Timestamp("2025-10-10")
DB_END = pd.Timestamp("2026-09-30")  # 10-01·10-02 봉은 잠정값 위험(20:30 적재) → 제외


def load_archive() -> pd.DataFrame:
    fs = sorted(glob.glob(str(ARCH / "krx_daily_*.parquet")))
    cols = ["ticker", "name", "bas_dd", "open", "high", "low", "close", "volume",
            "trade_value", "mktcap", "market", "open_adj", "high_adj", "low_adj",
            "close_adj", "adj_factor"]
    df = pd.concat([pd.read_parquet(f, columns=cols) for f in fs], ignore_index=True)
    df = df[df.bas_dd <= ARCH_END]
    return df


def load_db() -> tuple[pd.DataFrame, dict]:
    sm = None
    recs = []
    with open(DB_DUMP, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("SM\t"):
                sm = json.loads(line[3:])
                continue
            p = line.rstrip("\n").split("\t")
            # D ticker bas_dd o h l c vol tv updated_at
            recs.append((p[1], p[2], int(p[3]), int(p[4]), int(p[5]), int(p[6]),
                         int(p[7]), int(p[8]) if p[8] not in ("", "None") else 0))
    db = pd.DataFrame(recs, columns=["ticker", "bas_dd", "open", "high", "low", "close",
                                     "volume", "trade_value"])
    db["bas_dd"] = pd.to_datetime(db.bas_dd)
    db = db[(db.bas_dd >= DB_START) & (db.bas_dd <= DB_END)]
    meta = {r["ticker"]: r for r in sm}
    return db, meta


def market_unit_series() -> pd.DataFrame:
    fs = sorted(glob.glob(str(ETF / "krx_daily_*.parquet")))
    df = pd.concat([pd.read_parquet(f, columns=["ticker", "bas_dd", "close_adj"]) for f in fs])
    s = df[df.ticker == "069500"].sort_values("bas_dd").set_index("bas_dd")["close_adj"]
    # 운영 market_unit.classify: 마지막 80 종가. sum60 = 마지막 60(D-1 포함),
    # sum60_prev = 처음 60(20봉 전). above = last*60 > sum60, rising = sum60 > sum60_prev.
    sma = s.rolling(60).mean()
    sma_prev = sma.shift(20)
    above = s > sma
    rising = sma > sma_prev
    m = np.where(above & rising, 1.0, np.where(above & ~rising, 0.75,
                 np.where(~above & rising, 0.5, 0.0)))
    out = pd.DataFrame({"close": s, "m_at_close": m, "valid": sma_prev.notna()})
    return out


def main() -> None:
    arch = load_archive()
    db, meta = load_db()
    print("archive rows", len(arch), "db rows", len(db), file=sys.stderr)

    # 전역 달력
    cal = sorted(set(arch.bas_dd.unique()) | set(db.bas_dd.unique()))
    cal = pd.DatetimeIndex(cal)
    di = {d: i for i, d in enumerate(cal)}

    # 069500 시장 유닛: 그날 D 의 m = D-1 종가 판정(직전 영업일 봉)
    mu = market_unit_series()
    mu = mu.reindex(cal).ffill()
    m_close = mu["m_at_close"].values
    valid = mu["valid"].fillna(False).values.astype(bool)
    m_for_day = np.full(len(cal), np.nan)
    for i in range(1, len(cal)):
        if valid[i - 1]:
            m_for_day[i] = m_close[i - 1]

    # 지수 편입 근사(보관소): 그날 시총 KOSPI 상위 200 · KOSDAQ 상위 150,
    # 보통주(6자리 숫자 · 끝자리 0) · 이름에 '스팩' 없는 종목 중
    a = arch.copy()
    a["common"] = a.ticker.str.match(r"^\d{5}0$") & ~a.name.fillna("").str.contains("스팩")
    a["rk"] = np.nan
    sub = a[a.common & (a.mktcap > 0)]
    rk = sub.groupby(["bas_dd", "market"])["mktcap"].rank(ascending=False, method="first")
    a.loc[sub.index, "rk"] = rk
    a["idx_member"] = ((a.market == "KOSPI") & (a.rk <= 200)) | ((a.market == "KOSDAQ") & (a.rk <= 150))

    # DB 메타: 현재 편입 플래그 · ETF 그룹
    def db_member(t: str) -> bool:
        r = meta.get(t)
        if not r:
            return False
        g = (r.get("g1") or r.get("g2") or "")
        if g in ("EF", "EN", "FE"):
            return False
        return bool(r.get("is_kospi200")) or bool(r.get("is_kosdaq150"))

    panel = {}
    arch_g = {t: g for t, g in a.groupby("ticker")}
    db_g = {t: g for t, g in db.groupby("ticker")}
    tickers = sorted(set(arch_g) | set(db_g))
    junction_rescaled = 0
    for t in tickers:
        parts = []
        ga = arch_g.get(t)
        if ga is not None:
            ga = ga.sort_values("bas_dd")
            parts.append(pd.DataFrame({
                "d": ga.bas_dd.values,
                "o": ga.open_adj.values, "h": ga.high_adj.values,
                "l": ga.low_adj.values, "c": ga.close_adj.values,
                "raw": (ga.open.values / np.where(ga.open_adj.values > 0, ga.open_adj.values, np.nan)),
                "tv": ga.trade_value.values.astype(float),
                "vol": ga.volume.values.astype(float),
                "mem": ga.idx_member.values.astype(bool),
                "src": 0,
            }))
        gd = db_g.get(t)
        if gd is not None:
            gd = gd.sort_values("bas_dd")
            mem = db_member(t)
            parts.append(pd.DataFrame({
                "d": gd.bas_dd.values,
                "o": gd.open.values.astype(float), "h": gd.high.values.astype(float),
                "l": gd.low.values.astype(float), "c": gd.close.values.astype(float),
                "raw": np.ones(len(gd)),
                "tv": gd.trade_value.values.astype(float),
                "vol": gd.volume.values.astype(float),
                "mem": np.full(len(gd), mem),
                "src": 1,
            }))
        df = pd.concat(parts, ignore_index=True)
        # 이음매: 보관소 마지막 종가 대비 DB 첫 시가가 25% 넘게 벌어지면 보관소 쪽을 비율로 맞춘다
        if ga is not None and gd is not None and len(ga) and len(gd):
            last_a = float(ga.close_adj.values[-1])
            first_d = float(gd.open.values[0]) if gd.open.values[0] > 0 else float(gd.close.values[0])
            if last_a > 0 and first_d > 0 and abs(np.log(first_d / last_a)) > 0.25:
                k = first_d / last_a
                msk = df.src == 0
                for col in ("o", "h", "l", "c"):
                    df.loc[msk, col] = df.loc[msk, col] * k
                df.loc[msk, "raw"] = df.loc[msk, "raw"] / k
                junction_rescaled += 1
        # 거래 없는 날(시가 0) — 거래 불가 표식
        notrade = (df.o <= 0) | (df.vol <= 0)
        for col in ("o", "h", "l"):
            df.loc[notrade, col] = df.loc[notrade, "c"]
        df["notrade"] = notrade.values
        df["di"] = [di[pd.Timestamp(x)] for x in df.d.values]
        panel[t] = {k: df[k].values for k in ("di", "o", "h", "l", "c", "raw", "tv", "mem", "src", "notrade")}

    out = {"cal": cal, "m_for_day": m_for_day, "panel": panel,
           "names": a.drop_duplicates("ticker", keep="last").set_index("ticker")["name"].to_dict(),
           "db_meta": {t: {"name": r.get("name")} for t, r in meta.items()},
           "junction_rescaled": junction_rescaled}
    with open(SCR / "c405_panel.pkl", "wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print("tickers", len(panel), "cal", len(cal), cal[0], cal[-1],
          "junction_rescaled", junction_rescaled, file=sys.stderr)


if __name__ == "__main__":
    main()
