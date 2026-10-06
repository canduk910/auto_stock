#!/usr/bin/env python3
"""섹터 RS 배제 — 자료 층(사전 등록 §1 · §2).

입력 = KRX 업종분류 월초 스냅숏 jsonl(``sector_rs_fetch.py``) · 30년 보관소 ``unified/`` · KOSPI200 지수 일별 ·
ETF 보관소 ``parquet_etf/``. 출력 = 피클 하나(달력 · 스냅숏 · 버킷 지수 · 판별 하위 버킷 표 · 통계).

    python tools/replay/sector_rs_data.py <class.jsonl[,class2.jsonl …]> <out.pkl>
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import sys
import time
from collections import Counter

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from replay import sector_rs_core as R  # noqa: E402

LONG_DIR = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long"
KINDS = {"R60": 60, "R20": 20, "R120": 120, "IBD": "ibd"}


def load_snapshots(paths):
    """jsonl(들) → [(날짜, {종목: 버킷})] (시장 둘을 합침 · 한 시장이 그 달 비면 그 시장의 직전 스냅숏을 쓴다) + 통계."""
    by = {}
    for path in ([paths] if isinstance(paths, str) else paths):
        for line in open(path, encoding="utf-8"):
            o = json.loads(line)
            by.setdefault(o["trd_dd"], {})[o["mkt"]] = o["rows"]
    labels, unmapped = Counter(), Counter()
    last = {"STK": None, "KSQ": None}
    snaps, cover = [], []
    for dd in sorted(by):
        cur = {}
        for mkt in ("STK", "KSQ"):
            rows = by[dd].get(mkt) or []
            if rows:
                m = {}
                for r in rows:
                    lab = r.get("IDX_IND_NM", "")
                    labels[lab] += 1
                    b = R.label_bucket(lab)
                    if b is None:
                        unmapped[lab] += 1
                        continue
                    m[str(r["ISU_SRT_CD"])] = b
                last[mkt] = m
            if last[mkt]:
                cur.update(last[mkt])
        cover.append({"date": dd, "STK": len(by[dd].get("STK") or []), "KSQ": len(by[dd].get("KSQ") or []),
                      "n": len(cur)})
        if cur:
            snaps.append((pd.Timestamp(dd), cur))
    return snaps, {"labels": dict(labels), "unmapped": dict(unmapped), "cover": cover}


def load_panel():
    cols = ["ticker", "bas_dd", "close_adj", "mktcap"]
    parts = [pd.read_parquet(f, columns=cols) for f in sorted(glob.glob(os.path.join(LONG_DIR, "unified", "*.parquet")))]
    df = pd.concat(parts, ignore_index=True)
    df = df.sort_values(["ticker", "bas_dd"], kind="stable").reset_index(drop=True)
    same = df["ticker"].eq(df["ticker"].shift())
    prev_c = df["close_adj"].shift().where(same)
    prev_m = df["mktcap"].shift().where(same)
    df["r"] = df["close_adj"] / prev_c - 1.0
    df["w"] = prev_m
    ok = same & np.isfinite(df["r"]) & (df["r"].abs() <= R.RET_CAP) & (df["w"] > 0) & (prev_c > 0)
    return df.loc[ok, ["ticker", "bas_dd", "r", "w"]].reset_index(drop=True)


def sector_indices(panel: pd.DataFrame, cal: pd.DatetimeIndex, clf: R.Classifier):
    """버킷별 시가총액 가중 일 수익 → 수준(시작 1.0, 시작 전 NaN) · 그날 구성 종목 수 · 시작 색인."""
    snap_ns = np.array(clf.dates, dtype=np.int64)
    d_ns = panel["bas_dd"].values.astype("datetime64[ns]").astype(np.int64)
    si = np.searchsorted(snap_ns, d_ns, side="left") - 1
    if clf.backfill:
        si = np.where(si < 0, 0, si)
    rows = []
    for i, m in enumerate(clf.maps):
        rows.append(pd.DataFrame({"sid": i, "ticker": list(m.keys()), "bucket": list(m.values())}))
    mp = pd.concat(rows, ignore_index=True)
    p = panel.assign(sid=si)
    p = p[p["sid"] >= 0]
    a = p.merge(mp, on=["sid", "ticker"], how="left")
    miss = a["bucket"].isna()
    if miss.any():
        a.loc[miss, "ct"] = a.loc[miss, "ticker"].map(R.common_of)
        b2 = a.loc[miss, ["sid", "ct"]].merge(mp.rename(columns={"ticker": "ct"}), on=["sid", "ct"], how="left")
        a.loc[miss, "bucket"] = b2["bucket"].values
    a = a.dropna(subset=["bucket"])
    a["wr"] = a["w"] * a["r"]
    g = a.groupby(["bas_dd", "bucket"]).agg(wr=("wr", "sum"), w=("w", "sum"), n=("r", "size")).reset_index()
    levels, members, start = {}, {}, {}
    for b in R.BUCKETS:
        x = g[g["bucket"] == b].set_index("bas_dd").reindex(cal)
        n = x["n"].fillna(0).to_numpy(int)
        ret = (x["wr"] / x["w"]).to_numpy(float)
        ret = np.where((n >= R.MIN_MEMBERS) & np.isfinite(ret), ret, 0.0)
        ok = np.nonzero(n >= R.MIN_MEMBERS)[0]
        if len(ok) == 0:
            continue
        s0 = int(ok[0])
        lv = np.full(len(cal), np.nan)
        lv[s0:] = np.cumprod(1.0 + np.r_[0.0, ret[s0 + 1:]])
        levels[b], members[b], start[b] = lv, n, s0
    return levels, members, start


def etf_levels(cal: pd.DatetimeIndex):
    parts = [pd.read_parquet(f, columns=["ticker", "bas_dd", "close"])
             for f in sorted(glob.glob(os.path.join(LONG_DIR, "parquet_etf", "*.parquet")))]
    e = pd.concat(parts, ignore_index=True)
    levels, members, start, first = {}, {}, {}, {}
    for b, t in R.ETF_PROXY.items():
        s = e[e["ticker"] == t].set_index("bas_dd")["close"].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        if s.empty:
            continue
        x = s.reindex(cal).ffill(limit=5).to_numpy(float)
        ok = np.nonzero(np.isfinite(x))[0]
        if len(ok) == 0:
            continue
        levels[b] = x
        members[b] = np.where(np.isfinite(x), 99, 0)
        start[b] = int(ok[0])
        first[b] = str(s.index[0].date())
    return levels, members, start, first


def main():
    src, out = sys.argv[1].split(","), sys.argv[2]
    t0 = time.time()
    snaps, st = load_snapshots(src)
    print(f"[srs_data] 스냅숏 {len(snaps)} · 첫 {snaps[0][0].date()} · 미대응 업종명 {st['unmapped']}", flush=True)
    panel = load_panel()
    cal = pd.DatetimeIndex(sorted(panel["bas_dd"].unique()))
    k = pd.read_csv(os.path.join(LONG_DIR, "index", "krx_kospi200.csv"), parse_dates=["date"]).set_index("date")["close"]
    bench = k.reindex(cal).ffill().to_numpy(float)
    print(f"[srs_data] 패널 {len(panel):,}행 · 달력 {len(cal)} · {time.time() - t0:.0f}s", flush=True)
    res = {"cal": cal, "bench": bench, "snaps": snaps, "snap_stats": st, "excl": {}, "index": {}}
    for tag, bf in (("strict", False), ("bf", True)):
        clf = R.Classifier(snaps, backfill=bf)
        lv, mb, s0 = sector_indices(panel, cal, clf)
        res["index"][tag] = {"levels": lv, "members": mb, "start": s0}
        print(f"[srs_data] 버킷 지수 {tag} {len(lv)}개 · 시작 { {b: str(cal[i].date()) for b, i in s0.items()} } · "
              f"{time.time() - t0:.0f}s", flush=True)
    ix = res["index"]["strict"]
    for name, kind in KINDS.items():
        res["excl"][name] = R.excl_table(ix["levels"], ix["members"], bench, kind, start=ix["start"])
    ixb = res["index"]["bf"]
    res["excl"]["BF"] = R.excl_table(ixb["levels"], ixb["members"], bench, 60, start=ixb["start"])
    el, em, es, ef = etf_levels(cal)
    res["index"]["etf"] = {"levels": el, "members": em, "start": es, "first": ef}
    res["excl"]["ETF"] = R.excl_table(el, em, bench, 60, start=es)
    for name, ex in res["excl"].items():
        nz = [i for i, x in enumerate(ex) if x]
        print(f"[srs_data] 하위 표 {name}: 배제 있는 첫날 {cal[nz[0]].date() if nz else None} · 날 {len(nz)}", flush=True)
    with open(out, "wb") as fh:
        pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[srs_data] 저장 {out} · {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
