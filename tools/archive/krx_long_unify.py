"""1996~2026 단일 KRX 일봉 보관소 — 출처 셋을 이어 붙이고 수정주가를 한 번에 다시 낸다 (2026-10-06).

결과 보고 = `_workspace/domain_consult/2026-10-05_archive_30y_build.md` §10.

출처(겹치는 날은 아래 우선순위, 나머지는 대조용):
  1. KRX 정보데이터시스템(로그인, MDCSTAT01501) — 1996-01-03 ~ 2009-12-31 · 2025-10-03 ~ 2026-10-02
  2. KRX Open API stk/ksq_bydd_trd (`krx_daily_archive.py stream`) — 2010-01-04 ~ 2020-10-02
  3. 기존 5년 보관소 parquet(cycle362, Open API) — 2020-10-05 ~ 2025-10-02
  (bridge_2010 · bridge_2020 = 정보데이터시스템으로 겹쳐 받은 경계 구간 — 대조에만 쓴다)

수정주가는 기존 `_adjust_one` 과 같은 규칙(기준가 = 종가 − 전일대비, 기준가 ≠ 전일 종가면 그 비율이 조정계수,
최신일부터 과거로 누적곱)을 30년 전체에 벡터로 적용한다 — 기준일 = 2026-10-02.

  python tools/archive/krx_long_unify.py build <base_dir>        — unified/ 연도별 parquet + meta/boundary_check.txt
  python tools/archive/krx_long_unify.py naver_check <base_dir>  — 네이버 보관소와 일간 수익률 교차 확인
  python tools/archive/krx_long_unify.py index <base_dir>        — 지수 csv + 시장 유닛 입력 연속 계열
  python tools/archive/krx_long_unify.py regime <base_dir>       — 제도·비용 메타 csv
"""
from __future__ import annotations

import json
import os
import sys

_COLS = ["ticker", "name", "bas_dd", "open", "high", "low", "close", "prev_diff", "volume",
         "trade_value", "mktcap", "list_shrs", "market"]


def _n(v) -> float:
    if v in (None, "", "-"):
        return 0.0
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def _load_mdc(path: str, source: str):
    import pandas as pd

    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = o["trd_dd"]
            for r in o["rows"]:
                # 휴장일 요청에도 전 종목 행이 '-' 값으로 온다(1996~2009 실측 332,967행) — 버린다
                if r.get("TDD_CLSPRC", "-") in ("-", ""):
                    continue
                out.append((r["ISU_SRT_CD"], r.get("ISU_ABBRV", ""), d, _n(r["TDD_OPNPRC"]), _n(r["TDD_HGPRC"]),
                            _n(r["TDD_LWPRC"]), _n(r["TDD_CLSPRC"]), _n(r["CMPPREVDD_PRC"]), _n(r["ACC_TRDVOL"]),
                            _n(r["ACC_TRDVAL"]), _n(r["MKTCAP"]), _n(r["LIST_SHRS"]), r.get("MKT_NM", "")))
    df = pd.DataFrame(out, columns=_COLS)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"], format="%Y%m%d")
    df["source"] = source
    return df


def _load_openapi_jsonl(path: str, source: str):
    import pandas as pd

    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = o["bas_dd"]
            for r in o["rows"]:
                t, name, op, hi, lo, cl, pdiff, vol, tval, mcap, shrs, mkt = r
                if t:
                    out.append((t, name, d, op, hi, lo, cl, pdiff, vol, tval, mcap, shrs, mkt))
    df = pd.DataFrame(out, columns=_COLS)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"], format="%Y%m%d")
    for c in _COLS[3:12]:
        df[c] = df[c].astype(float)
    df["source"] = source
    return df


def _load_5y(krx5_dir: str):
    import pandas as pd

    fs = sorted(f for f in os.listdir(krx5_dir) if f.startswith("krx_daily_") and f.endswith(".parquet"))
    df = pd.concat([pd.read_parquet(os.path.join(krx5_dir, f), columns=_COLS) for f in fs], ignore_index=True)
    for c in _COLS[3:12]:
        df[c] = df[c].astype(float)
    df["source"] = "openapi_5y"
    return df


def _compare(a, b, label: str, lines: list) -> None:
    import numpy as np

    m = a.merge(b, on=["ticker", "bas_dd"], suffixes=("_a", "_b"))
    if m.empty:
        lines.append(f"{label}: 겹치는 행 0")
        return
    def rate(c, tol=0.5):
        return (np.abs(m[f"{c}_a"] - m[f"{c}_b"]) <= tol).mean() * 100
    ta, tb = set(a["ticker"]), set(b["ticker"])
    lines.append(
        f"{label}: 겹치는 행 {len(m)} · 날짜 {m['bas_dd'].nunique()} · 종목(a {len(ta)}, b {len(tb)}, 공통 {len(ta & tb)}) | "
        f"일치율 종가 {rate('close'):.3f}% 시가 {rate('open'):.3f}% 전일대비 {rate('prev_diff'):.3f}% "
        f"거래량 {rate('volume'):.3f}% 거래대금 {rate('trade_value', 1.0):.3f}% 시총 {rate('mktcap', 1.0):.3f}% "
        f"상장주식수 {rate('list_shrs'):.3f}%")
    bad = m[np.abs(m["close_a"] - m["close_b"]) > 0.5]
    if len(bad):
        lines.append("  종가 불일치 예: " + "; ".join(
            f"{r.ticker} {r.bas_dd.date()} {r.close_a:.0f}/{r.close_b:.0f}" for r in bad.head(5).itertuples()))


def _adjust(df):
    import numpy as np

    df = df.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)
    g = df.groupby("ticker", sort=False)
    prev_close = g["close"].shift(1)
    base = df["close"] - df["prev_diff"]
    ratio = base / prev_close
    ok = (prev_close > 0) & (df["close"] > 0) & ratio.between(0.01, 100.0)
    ratio = ratio.where(ok, 1.0)
    # 그 행 이후(그 행 미포함) 조정계수의 곱 = 뒤에서부터 누적곱 ÷ 자기 비율
    rc = ratio[::-1].groupby(df["ticker"][::-1], sort=False).cumprod()[::-1]
    cum = (rc / ratio).astype(float)
    for c in ("open", "high", "low", "close"):
        df[f"{c}_adj"] = (df[c] * cum).round(2)
    df["adj_factor"] = cum
    df["adj_event"] = ~np.isclose(ratio, 1.0)
    df["no_trade"] = df["volume"] <= 0
    return df


def build(base: str) -> None:
    import pandas as pd

    raw = os.path.join(base, "raw_krx_mdc")
    krx5 = os.path.join(os.path.dirname(base.rstrip("/")), "krx_daily", "parquet")
    lines: list[str] = []
    main = _load_mdc(os.path.join(raw, "main_1996_2009.jsonl"), "mdc")
    tail = _load_mdc(os.path.join(raw, "tail_2025_2026.jsonl"), "mdc")
    b10 = _load_mdc(os.path.join(raw, "bridge_2010.jsonl"), "mdc_bridge")
    b20 = _load_mdc(os.path.join(raw, "bridge_2020.jsonl"), "mdc_bridge")
    oa = _load_openapi_jsonl(os.path.join(base, "raw_krx_2010_2020.jsonl"), "openapi")
    k5 = _load_5y(krx5)
    lines.append(f"정보데이터시스템 1996~2009: 행 {len(main)} 날짜 {main['bas_dd'].nunique()} 종목 {main['ticker'].nunique()} "
                 f"({main['bas_dd'].min().date()}~{main['bas_dd'].max().date()})")
    lines.append(f"Open API 2010~2020: 행 {len(oa)} 날짜 {oa['bas_dd'].nunique()} 종목 {oa['ticker'].nunique()} "
                 f"({oa['bas_dd'].min().date()}~{oa['bas_dd'].max().date()})")
    lines.append(f"5년 보관소: 행 {len(k5)} 날짜 {k5['bas_dd'].nunique()} 종목 {k5['ticker'].nunique()}")
    lines.append(f"정보데이터시스템 꼬리: 행 {len(tail)} 날짜 {tail['bas_dd'].nunique()} "
                 f"({tail['bas_dd'].min().date()}~{tail['bas_dd'].max().date()})")
    _compare(b10, oa, "경계 2010-01 (정보데이터시스템 vs Open API)", lines)
    _compare(b20, oa, "경계 2020-09 (정보데이터시스템 vs Open API)", lines)
    _compare(b20, k5, "경계 2020-10 (정보데이터시스템 vs 5년 보관소)", lines)
    _compare(tail, k5, "경계 2025-09 (정보데이터시스템 vs 5년 보관소)", lines)

    parts = [
        main[main["bas_dd"] <= "2009-12-31"],
        oa[(oa["bas_dd"] >= "2010-01-01") & (oa["bas_dd"] <= "2020-10-02")],
        k5[(k5["bas_dd"] >= "2020-10-05") & (k5["bas_dd"] <= "2025-10-02")],
        tail[tail["bas_dd"] >= "2025-10-03"],
    ]
    df = pd.concat(parts, ignore_index=True)
    df = df[df["ticker"].astype(str).str.len() > 0]
    dup = df.duplicated(["ticker", "bas_dd"]).sum()
    lines.append(f"합본: 행 {len(df)} · 중복(ticker,날짜) {dup} · 종목 {df['ticker'].nunique()} · 날짜 {df['bas_dd'].nunique()} "
                 f"({df['bas_dd'].min().date()}~{df['bas_dd'].max().date()})")
    df = df.drop_duplicates(["ticker", "bas_dd"], keep="first")
    df = _adjust(df)
    last = df.groupby("ticker")["bas_dd"].max()
    end = df["bas_dd"].max()
    df["last_date"] = df["ticker"].map(last)
    df["delisted_by_end"] = df["last_date"] < end - pd.Timedelta(days=14)
    lines.append(f"조정 사건(종목×날짜) {int(df['adj_event'].sum())} · 마지막 거래일이 끝보다 2주 이상 이른 종목(폐지·이전 등) "
                 f"{int(df.groupby('ticker')['delisted_by_end'].first().sum())}")
    out = os.path.join(base, "unified")
    os.makedirs(out, exist_ok=True)
    df["year"] = df["bas_dd"].dt.year
    for yr, gdf in df.groupby("year"):
        gdf.drop(columns=["year"]).to_parquet(os.path.join(out, f"krx_unified_{yr}.parquet"), index=False)
    by = df.groupby("year").agg(rows=("ticker", "size"), tickers=("ticker", "nunique"), days=("bas_dd", "nunique"),
                               src=("source", lambda s: ",".join(sorted(set(s)))))
    lines.append(by.to_string())
    txt = "\n".join(lines)
    with open(os.path.join(base, "meta", "boundary_check.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)


def _read_unified(base: str, cols=None, years=None):
    import pandas as pd

    d = os.path.join(base, "unified")
    fs = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    if years:
        fs = [f for f in fs if int(f[-12:-8]) in years]
    return pd.concat([pd.read_parquet(os.path.join(d, f), columns=cols) for f in fs], ignore_index=True)


def naver_check(base: str) -> None:
    import numpy as np
    import pandas as pd

    lines = []
    for a, b in (("1996-01-01", "2009-12-31"), ("2010-01-01", "2020-10-02"), ("2020-10-05", "2026-10-02")):
        yrs = range(int(a[:4]), int(b[:4]) + 1)
        u = _read_unified(base, ["ticker", "bas_dd", "close_adj", "volume"], yrs)
        u = u[(u["bas_dd"] >= a) & (u["bas_dd"] <= b)]
        nd = os.path.join(base, "parquet")
        n = pd.concat([pd.read_parquet(os.path.join(nd, f"naver_daily_{y}.parquet"), columns=["ticker", "bas_dd", "close"])
                       for y in yrs if os.path.exists(os.path.join(nd, f"naver_daily_{y}.parquet"))])
        n = n[(n["bas_dd"] >= a) & (n["bas_dd"] <= b)]
        m = u.merge(n, on=["ticker", "bas_dd"]).sort_values(["ticker", "bas_dd"])
        m["ru"] = m.groupby("ticker")["close_adj"].pct_change()
        m["rn"] = m.groupby("ticker")["close"].pct_change()
        d = (m["ru"] - m["rn"]).abs().dropna()
        tu, tn = set(u["ticker"]), set(n["ticker"])
        lines.append(f"{a}~{b}: KRX 종목 {len(tu)} · 네이버 종목 {len(tn)} · KRX에만 {len(tu - tn)} · 네이버에만 {len(tn - tu)} | "
                     f"수익률 차 ≤0.01%p {(d <= 1e-4).mean() * 100:.2f}% ≤0.1%p {(d <= 1e-3).mean() * 100:.2f}% "
                     f"≤1%p {(d <= 1e-2).mean() * 100:.3f}% (n={len(d)})")
    txt = "\n".join(lines)
    with open(os.path.join(base, "meta", "naver_crosscheck.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)


def index(base: str) -> None:
    import pandas as pd

    rows = []
    with open(os.path.join(base, "raw_krx_mdc", "index_1995_2026.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            o = json.loads(line)
            for r in o["rows"]:
                rows.append((o["index"], r["TRD_DD"].replace("/", "-"), _n(r["OPNPRC_IDX"]), _n(r["HGPRC_IDX"]),
                             _n(r["LWPRC_IDX"]), _n(r["CLSPRC_IDX"]), _n(r["ACC_TRDVOL"]), _n(r["ACC_TRDVAL"])))
    df = pd.DataFrame(rows, columns=["index", "date", "open", "high", "low", "close", "volume", "trade_value"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(["index", "date"]).sort_values(["index", "date"])
    # 초기 몇 해는 시고저가 비어 0 으로 온다 — 0 을 값으로 쓰지 않게 비운다(종가는 다 있다)
    df[["open", "high", "low"]] = df[["open", "high", "low"]].mask(df[["open", "high", "low"]] <= 0)
    outd = os.path.join(base, "index")
    for name, g in df.groupby("index"):
        g.drop(columns=["index"]).to_csv(os.path.join(outd, f"krx_{name.lower()}.csv"), index=False)
        print(f"[index] {name} {len(g)}행 {g['date'].min().date()}~{g['date'].max().date()}")
    # 캐시(FDR)와 대조
    for name, c in (("KOSPI", "ks11"), ("KOSPI200", "ks200"), ("KOSDAQ", "kq11")):
        a = df[df["index"] == name].set_index("date")["close"]
        p = os.path.join(outd, f"{c}_all.csv")
        if os.path.exists(p):
            b = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["Close"]
            j = pd.concat([a, b], axis=1, keys=["krx", "fdr"]).dropna()
            print(f"[index] {name} vs FDR 캐시: 겹침 {len(j)} 종가 0.01 이내 {((j.krx - j.fdr).abs() <= 0.011).mean() * 100:.3f}%")
    # 시장 유닛 입력 연속 계열: 069500(네이버 ETF 수정주가) + 상장 전은 KOSPI200 지수를 첫날 비율로 이어 붙인다
    k200 = df[df["index"] == "KOSPI200"].set_index("date")[["open", "high", "low", "close"]]
    ed = os.path.join(base, "parquet_etf")
    etf = pd.concat([pd.read_parquet(os.path.join(ed, f)) for f in os.listdir(ed) if f.endswith(".parquet")])
    e = etf[etf["ticker"] == "069500"].set_index("bas_dd").sort_index()[["open", "high", "low", "close"]]
    first = e.index.min()
    scale = e.loc[first, "close"] / k200.loc[first, "close"]
    pre = (k200[k200.index < first] * scale).round(2)
    pre["source"] = "KOSPI200 지수×%.6f" % scale
    e = e.copy()
    e["source"] = "069500 네이버 수정주가"
    ser = pd.concat([pre, e])
    ser.index.name = "date"
    ser.to_csv(os.path.join(outd, "market_unit_series.csv"))
    print(f"[index] 시장 유닛 연속 계열 {len(ser)}행 {ser.index.min().date()}~{ser.index.max().date()} · 이음 {first.date()} 배율 {scale:.6f}")


def regime(base: str) -> None:
    import csv

    meta = os.path.join(base, "meta")
    with open(os.path.join(meta, "regime_price_limit.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["market", "from", "to", "limit_pct", "evidence"])
        rows = [
            ("KOSPI", "1995-04-01", "1996-11-24", 6, "보관소 상한가 최빈값 6% · 외부: 1995-04 6%"),
            ("KOSPI", "1996-11-25", "1998-03-01", 8, "11-22 6% → 11-25 8%"),
            ("KOSPI", "1998-03-02", "1998-12-06", 12, "02-28 8~9% → 03-04 12%"),
            ("KOSPI", "1998-12-07", "2015-06-14", 15, "12-04 12% → 12-07 15%"),
            ("KOSDAQ", "1996-07-01", "1996-11-24", "정액제", "외부: 1996-11 비율제 전환"),
            ("KOSDAQ", "1996-11-25", "1998-05-24", 8, "1996-11 최빈 8%"),
            ("KOSDAQ", "1998-05-25", "2005-03-27", 12, "05-23 6~8% → 05-25 12%"),
            ("KOSDAQ", "2005-03-28", "2015-06-14", 15, "03-25 12% → 03-28 15%"),
            ("ALL", "2015-06-15", "", 30, "06-12 15% → 06-15 30%"),
        ]
        w.writerows(rows)
    with open(os.path.join(meta, "regime_sessions.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "from", "to", "note"])
        w.writerows([
            ("토요일 장", "", "1998-12-05", "마지막 토요일 거래일(보관소 실측). 1996~1998 연 292~293 거래일"),
            ("정규장 15:30 마감", "2016-08-01", "", "이전 15:00(일반 지식)"),
            ("NXT 개장", "2025-03-04", "", "일반 지식"),
        ])
    with open(os.path.join(meta, "regime_costs.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["from", "to", "sell_tax_kospi_pct", "sell_tax_kosdaq_pct", "fee_one_way_pct_assumed",
                    "round_trip_pct_assumed", "source"])
        w.writerows([
            ("1996-01-01", "1996-03-31", 0.45, 0.45, 0.5, 1.45, "거래세 0.30+농특세 0.15(1995-07~) · 수수료 최고 0.5%(1991-04 자율화)"),
            ("1996-04-01", "1999-06-30", 0.30, 0.30, 0.5, 1.30, "1996-04 거래세 인하(한국일보 1996-03-20)"),
            ("1999-07-01", "2005-12-31", 0.30, 0.30, 0.1, 0.50, "1999-06 사이버 0.5→0.1%(한국일보 1999-06-17)"),
            ("2006-01-01", "2019-05-29", 0.30, 0.30, 0.03, 0.36, "온라인 0.03% 미만(가정)"),
            ("2019-05-30", "2020-12-31", 0.25, 0.25, 0.015, 0.28, "나무위키 증권거래세 표"),
            ("2021-01-01", "2022-12-31", 0.23, 0.23, 0.015, 0.26, ""),
            ("2023-01-01", "2023-12-31", 0.20, 0.20, 0.015, 0.23, ""),
            ("2024-01-01", "2024-12-31", 0.18, 0.18, 0.015, 0.21, ""),
            ("2025-01-01", "2025-12-31", 0.15, 0.15, 0.015, 0.18, ""),
            ("2026-01-01", "", 0.20, 0.20, 0.015, 0.23, ""),
        ])
    print("[regime] meta/regime_price_limit.csv · regime_sessions.csv · regime_costs.csv")


def main() -> None:
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        sys.exit(1)
    {"build": build, "naver_check": naver_check, "index": index, "regime": regime}[a[0]](a[1])


if __name__ == "__main__":
    main()
