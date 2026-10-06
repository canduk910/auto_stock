#!/usr/bin/env python3
"""섹터 RS 연구 — KRX 정보데이터시스템 「업종분류 현황」(MDCSTAT03901) 월초 스냅숏 수집(2026-10-06).

사전 등록 = ``_workspace/analysis/sector_rs_20261006/prereg.md`` §1.
매월 첫 거래일(KOSPI200 지수 일별 파일의 날짜) × 시장(STK·KSQ) 한 번씩 요청해 원본 행을 jsonl 한 줄로 쓴다.
이미 받은 (날짜, 시장)은 건너뛴다(이어 받기). 로그인·요청 간격·계정 취급은 ``tools/archive/krx_mdc_daily.py`` 를 그대로 쓴다.

    python tools/replay/sector_rs_fetch.py <out.jsonl> [<start YYYY-MM>] [<end YYYY-MM>]
"""
from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
MAIN_REPO = "/Users/koscom/Projects/auto_stock"
for _p in (os.path.join(_ROOT, "tools", "archive"), os.path.join(MAIN_REPO, "tools", "archive")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

LONG_DIR = os.path.join(MAIN_REPO, "data/archive/krx_daily_long")


def month_first_days(start: str, end: str) -> "list[str]":
    d = pd.read_csv(os.path.join(LONG_DIR, "index", "krx_kospi200.csv"), usecols=["date"])["date"]
    d = pd.to_datetime(d)
    d = d[(d >= pd.Timestamp(start + "-01")) & (d <= pd.Timestamp(end + "-01") + pd.offsets.MonthEnd(0))]
    first = d.groupby(d.dt.to_period("M")).min()
    return [x.strftime("%Y%m%d") for x in first]


def fetch(s, url, mkt, dd, sleep):
    data = {"bld": "dbms/MDC/STAT/standard/MDCSTAT03901", "locale": "ko_KR", "mktId": mkt, "trdDd": dd,
            "money": "1", "csvxls_isNo": "false"}
    for attempt in range(4):
        try:
            r = s.post(url, data=data, timeout=30)
            if r.status_code == 200 and r.text.strip() not in ("", "LOGOUT"):
                return r.json().get("block1", [])
            print(f"[srs_fetch] {mkt} {dd} http={r.status_code}", file=sys.stderr, flush=True)
        except Exception as ex:  # noqa: BLE001 — 계정은 로그인 요청에만 있다
            print(f"[srs_fetch] {mkt} {dd} {type(ex).__name__}", file=sys.stderr, flush=True)
        time.sleep(sleep * (2 ** (attempt + 1)))
    raise RuntimeError(f"{mkt} {dd} 실패")


def main():
    import krx_mdc_daily as K
    out = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else "2000-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2026-10"
    sleep = 2.0
    done = set()
    if os.path.exists(out):
        for line in open(out, encoding="utf-8"):
            try:
                o = json.loads(line)
                done.add((o["trd_dd"], o["mkt"]))
            except (json.JSONDecodeError, KeyError):
                pass
    s = K._login()
    t_login = time.time()
    n = 0
    with open(out, "a", encoding="utf-8") as fh:
        for dd in month_first_days(start, end):
            for mkt in ("STK", "KSQ"):
                if (dd, mkt) in done:
                    continue
                if time.time() - t_login > 50 * 60:
                    s = K._login()
                    t_login = time.time()
                rows = fetch(s, K._URL, mkt, dd, sleep)
                fh.write(json.dumps({"trd_dd": dd, "mkt": mkt, "n": len(rows), "rows": rows}, ensure_ascii=False) + "\n")
                fh.flush()
                n += 1
                if n % 20 == 0:
                    print(f"[srs_fetch] {dd} {mkt} rows={len(rows)} req={n}", file=sys.stderr, flush=True)
                time.sleep(sleep)
    print(f"[srs_fetch] DONE req={n}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
