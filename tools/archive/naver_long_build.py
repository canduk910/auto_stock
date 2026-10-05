"""30년 일봉 보관소 — 네이버 원본 → 연도별 parquet + 기존 KRX 5년 보관소와 대조 (2026-10-05).

결과 보고 = `_workspace/domain_consult/2026-10-05_archive_30y_build.md`. 로컬 전용(pandas·pyarrow).

  build    <universe.csv> <raw_dir> <out_dir>          — 종목별 json → parquet(연도별)
  validate <out_dir> <krx_parquet_dir> [--from 2020-10-05 --to 2025-10-02]
  stats    <out_dir> <universe.csv>                     — 연도별 종목 수·폐지 수·제한폭 근접 체결
  flags    <out_dir> <out.csv>                          — 가격제한폭 초과 하루 변동 목록(조정 누락 의심)

가격은 네이버 수정주가(조회 시점 기준 액면분할·무상증자 등 반영)다. 거래량은 섞여 있다 — 2020 이후
사건은 가격과 반비례로 수정(실측 94%)되지만 오래된 분할은 그대로다(삼성전자 2018-04-27 거래량 606,216 =
50:1 분할 전 주수). 시가총액·상장주식수는 없다.
"""
from __future__ import annotations

import csv
import json
import os
import sys


def _load_universe(path: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["ticker"], []).append(r)
    return out


def build(universe_csv: str, raw_dir: str, out_dir: str) -> None:
    import pandas as pd

    uni = _load_universe(universe_csv)
    frames = []
    n_empty = 0
    n_clipped = 0
    for fn in sorted(os.listdir(raw_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(raw_dir, fn), encoding="utf-8") as fh:
            o = json.load(fh)
        rows = o["rows"]
        if not rows:
            n_empty += 1
            continue
        t = o["ticker"]
        df = pd.DataFrame(rows, columns=["bas_dd", "open", "high", "low", "close", "volume", "foreign_ratio"])
        df["bas_dd"] = pd.to_datetime(df["bas_dd"], format="%Y%m%d")
        metas = uni.get(t, [])
        listed = [m for m in metas if m["src"] == "listed"]
        delisted = sorted((m for m in metas if m["src"] == "delisted"), key=lambda m: m["delisting"])
        # 코드 재사용 방어 — 폐지 이력이 있으면 그 창 밖 행은 다른 회사일 수 있다.
        # 현재 상장 중이면 마지막 폐지일 다음 날부터만 현재 회사로, 폐지만 있으면 마지막 폐지일까지만.
        if delisted:
            last_del = pd.Timestamp(delisted[-1]["delisting"])
            before = len(df)
            if listed:
                df = df[df["bas_dd"] > last_del]
                meta = listed[0]
                status = "listed"
            else:
                df = df[df["bas_dd"] <= last_del]
                meta = delisted[-1]
                status = "delisted"
            n_clipped += before - len(df)
        else:
            meta = listed[0] if listed else {"name": "", "market": "", "delisting": "", "reason": ""}
            status = "listed"
        if df.empty:
            continue
        df.insert(0, "ticker", t)
        df["name"] = meta.get("name", "")
        df["market"] = meta.get("market", "")
        df["status"] = status
        df["delisting_date"] = meta.get("delisting", "") if status == "delisted" else ""
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    # 거래 없는 날(거래정지·휴장 아닌 무체결) — 네이버는 시고저 0 · 종가=전일 종가 · 거래량 0 으로 준다
    # (실측: 삼성전자 2018-04-30~05-03 분할 정지). 행은 지우지 않고 표시하고, 시고저 0 은 종가로 채운다.
    all_df["no_trade"] = all_df["volume"].fillna(0) <= 0
    for c in ("open", "high", "low"):
        z = all_df[c].fillna(0) <= 0
        all_df.loc[z, c] = all_df.loc[z, "close"]
    os.makedirs(out_dir, exist_ok=True)
    all_df["year"] = all_df["bas_dd"].dt.year
    for yr, g in all_df.groupby("year"):
        g.drop(columns=["year"]).to_parquet(os.path.join(out_dir, f"naver_daily_{yr}.parquet"), index=False)
    print(f"[build] rows={len(all_df)} tickers={all_df['ticker'].nunique()} empty_files={n_empty} "
          f"clipped_rows(code reuse)={n_clipped} years={all_df['year'].min()}~{all_df['year'].max()}")


def _read_dir(d: str, prefix: str, years: range | None = None):
    import pandas as pd

    fs = sorted(f for f in os.listdir(d) if f.startswith(prefix) and f.endswith(".parquet"))
    if years is not None:
        fs = [f for f in fs if int(f[-12:-8]) in years]
    return pd.concat([pd.read_parquet(os.path.join(d, f)) for f in fs], ignore_index=True)


def validate(out_dir: str, krx_dir: str, d0: str, d1: str) -> None:
    import numpy as np
    import pandas as pd

    yrs = range(int(d0[:4]), int(d1[:4]) + 1)
    nv = _read_dir(out_dir, "naver_daily_", yrs)
    kx = _read_dir(krx_dir, "krx_daily_", yrs)
    nv = nv[(nv["bas_dd"] >= d0) & (nv["bas_dd"] <= d1)]
    kx = kx[(kx["bas_dd"] >= d0) & (kx["bas_dd"] <= d1)]
    m = kx.merge(nv[["ticker", "bas_dd", "open", "high", "low", "close", "volume"]],
                 on=["ticker", "bas_dd"], how="outer", suffixes=("_k", "_n"), indicator=True)
    both = m[m["_merge"] == "both"].copy()
    only_k = m[m["_merge"] == "left_only"]
    only_n = m[m["_merge"] == "right_only"]
    print(f"[validate] 기간 {d0}~{d1}")
    print(f"[validate] KRX 행={len(kx)} 종목={kx['ticker'].nunique()} | 네이버 행={len(nv)} 종목={nv['ticker'].nunique()}")
    print(f"[validate] 양쪽 행={len(both)} | KRX만={len(only_k)} (종목 {only_k['ticker'].nunique()}) | "
          f"네이버만={len(only_n)} (종목 {only_n['ticker'].nunique()})")
    k_t = set(kx["ticker"]); n_t = set(nv["ticker"])
    print(f"[validate] 종목 커버리지: KRX 종목 중 네이버에 있는 비율 = {len(k_t & n_t) / len(k_t) * 100:.2f}%")

    # 1) 원가격 일치(네이버 수정주가 = KRX 원주가 인 행 — 조회 이후 조정 사건이 없는 구간)
    both["raw_eq"] = (both["close_n"] - both["close_k"]).abs() < 0.5
    both["adj_eq"] = (both["close_n"] - both["close_adj"]).abs() <= np.maximum(0.5, both["close_adj"].abs() * 0.001)
    print(f"[validate] 종가: 네이버=KRX원주가 {both['raw_eq'].mean() * 100:.2f}% | "
          f"네이버≈KRX수정주가(0.1%) {both['adj_eq'].mean() * 100:.2f}%")
    # 2) 일간 수익률 일치 — 수정 기준 시점 차이(KRX 보관소=2025-10-02, 네이버=오늘)에 무관한 지표
    both = both.sort_values(["ticker", "bas_dd"])
    both["r_n"] = both.groupby("ticker")["close_n"].pct_change()
    both["r_k"] = both.groupby("ticker")["close_adj"].pct_change()
    rr = both.dropna(subset=["r_n", "r_k"])
    diff = (rr["r_n"] - rr["r_k"]).abs()
    print(f"[validate] 일간 수익률 |차이|≤0.01%p {(diff <= 1e-4).mean() * 100:.3f}% · ≤0.1%p {(diff <= 1e-3).mean() * 100:.3f}% "
          f"· ≤1%p {(diff <= 1e-2).mean() * 100:.3f}% (n={len(rr)})")
    bad = rr[diff > 1e-2]
    print(f"[validate] 1%p 초과 어긋남 {len(bad)}행 · 종목 {bad['ticker'].nunique()}")
    print(bad.assign(d=diff[diff > 1e-2])[["ticker", "bas_dd", "close_k", "close_adj", "close_n", "r_k", "r_n", "d"]]
          .sort_values("d", ascending=False).head(15).to_string())
    # 3) 시고저 일관성(같은 날 비율이 종가 비율과 같아야 한다)
    for c in ("open", "high", "low"):
        ratio_c = both["close_n"] / both["close_k"]
        ok = ((both[f"{c}_n"] - both[f"{c}_k"] * ratio_c).abs() <= np.maximum(1.0, both[f"{c}_n"].abs() * 0.002))
        print(f"[validate] {c}: 네이버 ≈ KRX원주가×(그날 종가 비율) {ok.mean() * 100:.2f}%")
    vr = (both["volume_n"] == both["volume_k"]).mean()
    print(f"[validate] 거래량 완전 일치 {vr * 100:.2f}%")
    # 생존편향 점검 — KRX만 있는 종목 중 기간 내 사라진(폐지) 종목
    last_k = kx.groupby("ticker")["bas_dd"].max()
    gone = last_k[last_k < pd.Timestamp(d1) - pd.Timedelta(days=10)]
    print(f"[validate] KRX 기간 중 사라진 종목 {len(gone)} 중 네이버에 있는 것 {len(set(gone.index) & n_t)}")
    miss = sorted(set(gone.index) - n_t)
    print(f"[validate] 사라진 종목 중 네이버 없음 예시 {miss[:15]}")


def stats(out_dir: str, universe_csv: str) -> None:
    import pandas as pd

    df = _read_dir(out_dir, "naver_daily_")
    df["year"] = df["bas_dd"].dt.year
    per = df.groupby("year").agg(tickers=("ticker", "nunique"), rows=("ticker", "size"),
                                 days=("bas_dd", "nunique"))
    uni = pd.read_csv(universe_csv, dtype=str)
    dl = uni[uni["src"] == "delisted"].copy()
    dl["year"] = dl["delisting"].str[:4].astype(int)
    have = set(df.loc[df["status"] == "delisted", "ticker"])
    dl["have"] = dl["ticker"].isin(have)
    d = dl.groupby("year").agg(delisted_list=("ticker", "size"), delisted_with_data=("have", "sum"))
    per = per.join(d, how="left").fillna(0).astype(int)
    # 제한폭 근접 — 전일 종가 대비 상승률 분포 상단(제도 변화 확인용)
    df = df.sort_values(["ticker", "bas_dd"])
    df["r"] = df.groupby("ticker")["close"].pct_change()
    q = df[df["volume"] > 0].groupby("year")["r"].agg(lambda s: round(s.quantile(0.9999) * 100, 1))
    per["r_p9999_pct"] = q
    mx = df[df["volume"] > 0].groupby("year")["r"].agg(lambda s: round((s.between(0.145, 0.155)).sum()))
    per["n_r_14.5~15.5pct"] = mx
    mx30 = df[df["volume"] > 0].groupby("year")["r"].agg(lambda s: round((s.between(0.29, 0.30)).sum()))
    per["n_r_29~30pct"] = mx30
    print(per.to_string())


# 가격제한폭(상하 동일). 시행일은 이 보관소의 일별 상한가 최빈값으로 실측했다(결과 보고 「제도 변화」 절).
_LIMITS = {
    "KOSPI": [("1900-01-01", 0.06), ("1996-11-25", 0.08), ("1998-03-02", 0.12), ("1998-12-07", 0.15), ("2015-06-15", 0.30)],
    "KOSDAQ": [("1900-01-01", 0.06), ("1996-11-25", 0.08), ("1998-05-25", 0.12), ("2005-03-28", 0.15), ("2015-06-15", 0.30)],
}


def flags(out_dir: str, out_csv: str) -> None:
    """가격제한폭을 넘는 하루 변동(종가 기준)을 표시한다 — 지우지 않는다.

    합법적인 경우(상장 첫날 이후 며칠의 기준가 재산정·정리매매·거래재개·감자 후 재상장)와
    네이버 수정주가의 조정 누락(감자·병합 등)이 섞여 있다. 백테스트는 이 행을 진입·청산 신호에서
    빼거나 그 종목의 그 구간을 건너뛰어야 한다.
    """
    import numpy as np
    import pandas as pd

    df = _read_dir(out_dir, "naver_daily_")[["ticker", "bas_dd", "close", "volume", "market"]]
    df = df.sort_values(["ticker", "bas_dd"])
    df["r"] = df.groupby("ticker")["close"].pct_change()
    df["mk"] = np.where(df["market"].str.startswith("KOSDAQ"), "KOSDAQ", "KOSPI")
    df["limit"] = np.nan
    for mk, sched in _LIMITS.items():
        for i, (d, lim) in enumerate(sched):
            end = sched[i + 1][0] if i + 1 < len(sched) else "2100-01-01"
            sel = (df["mk"] == mk) & (df["bas_dd"] >= d) & (df["bas_dd"] < end)
            df.loc[sel, "limit"] = lim
    bad = df[df["r"].abs() > df["limit"] + 0.01].copy()
    bad[["ticker", "bas_dd", "market", "close", "r", "limit"]].to_csv(out_csv, index=False)
    bad["year"] = bad["bas_dd"].dt.year
    tot = df.groupby(df["bas_dd"].dt.year).size()
    s = pd.DataFrame({"jump_rows": bad.groupby("year").size(), "jump_tickers": bad.groupby("year")["ticker"].nunique(),
                      "rows": tot}).fillna(0).astype(int)
    s["per_10k"] = (s["jump_rows"] / s["rows"] * 1e4).round(2)
    print(s.to_string())
    print(f"[flags] 제한폭 초과 {len(bad)}행 · 종목 {bad['ticker'].nunique()} -> {out_csv}")


def main() -> None:
    a = sys.argv[1:]

    def opt(n: str, dflt: str) -> str:
        return a[a.index(n) + 1] if n in a else dflt

    if a[0] == "build":
        build(a[1], a[2], a[3])
    elif a[0] == "validate":
        validate(a[1], a[2], opt("--from", "2020-10-05"), opt("--to", "2025-10-02"))
    elif a[0] == "flags":
        flags(a[1], a[2])
    elif a[0] == "stats":
        stats(a[1], a[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
