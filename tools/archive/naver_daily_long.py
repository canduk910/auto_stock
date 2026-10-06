"""30년 일봉 보관소 — 네이버 금융 차트(siseJson) 종목별 일봉 수집 (2026-10-05).

결과 보고 = `_workspace/domain_consult/2026-10-05_archive_30y_build.md`.

왜 이 출처인가:
- KRX Open API(`stk_bydd_trd`)는 2010-01-04 부터만 준다(KRX 서비스 설명) — 1996~2009 는 다른 출처가 필요하다.
- KRX 정보데이터시스템(data.krx.co.kr, pykrx 가 쓰는 곳)은 2025 말부터 회원 로그인이 필요하다(실측: "LOGOUT").
- 네이버 `api.finance.naver.com/siseJson.naver` 는 1990년대부터 종목별 일봉을 준다. 단 (실측)
  2007년 중반 이전에 상장폐지된 종목은 비어 있고, 시가총액·상장주식수는 없다. 가격은 액면분할 등이
  반영된 수정주가다.

이 스크립트는 로컬(맥)에서 돈다. 운영 서버·운영 DB·KIS 는 건드리지 않는다.
종목 목록 = FinanceData/fdr_krx_data_cache 의 상장 목록 + 상장폐지 목록(KIND 기반).

  python tools/archive/naver_daily_long.py universe <listing.csv> <delisting.csv> <out_universe.csv>
  python tools/archive/naver_daily_long.py collect <universe.csv> <raw_dir> [--sleep 1.2] [--start 19960101] [--end 20261002]

collect 는 종목 하나 = 파일 하나(`raw_dir/<ticker>.json`)로 쓰고, 이미 있는 파일은 건너뛴다(이어 받기).
진행 로그는 stderr, 끝에 DONE 한 줄.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

_URL = (
    "https://api.finance.naver.com/siseJson.naver?symbol={sym}&requestType=1"
    "&startTime={s}&endTime={e}&timeframe=day"
)
_UA = "Mozilla/5.0 (research; low-rate daily archive)"

# 가격 시계열이 있는 지분증권만 — 수익증권(ETF·펀드)·신주인수권은 뺀다(ETF 는 별도 수집).
_KEEP_SECU = {"주권", "외국주권", "주식예탁증권", "부동산투자회사", "선박투자회사", "투자회사"}
_KEEP_MKT = {"KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"}


def universe(listing_csv: str, delisting_csv: str, out_csv: str, since: str = "1996-01-01") -> None:
    out = []
    with open(listing_csv, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["Market"] in _KEEP_MKT:
                out.append({"ticker": r["Code"], "name": r["Name"], "market": r["Market"],
                            "secu": "", "listing": "", "delisting": "", "reason": "", "src": "listed"})
    with open(delisting_csv, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["Market"] in _KEEP_MKT and r["SecuGroup"] in _KEEP_SECU and r["DelistingDate"] >= since:
                out.append({"ticker": r["Symbol"], "name": r["Name"], "market": r["Market"],
                            "secu": r["SecuGroup"], "listing": r["ListingDate"],
                            "delisting": r["DelistingDate"], "reason": r["Reason"], "src": "delisted"})
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    n_t = len({r["ticker"] for r in out})
    print(f"[universe] rows={len(out)} unique_tickers={n_t} -> {out_csv}")


def _fetch(sym: str, s: str, e: str) -> list[list]:
    req = urllib.request.Request(_URL.format(sym=sym, s=s, e=e), headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "ignore")
    rows = []
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith('["') or "날짜" in line:
            continue
        # ["19960103", 1849, 1915, 1842, 1896, 221350, 0.0]  (마지막 칸 외국인소진율, 빈칸 가능)
        parts = [p.strip().strip('"') for p in line.strip("[]").split(",")]
        try:
            rows.append([parts[0]] + [float(p) if p else None for p in parts[1:7]])
        except ValueError:
            continue
    return rows


def collect(universe_csv: str, raw_dir: str, sleep: float, start: str, end: str) -> None:
    os.makedirs(raw_dir, exist_ok=True)
    with open(universe_csv, encoding="utf-8") as fh:
        tickers = list(dict.fromkeys(r["ticker"] for r in csv.DictReader(fh)))
    done = skipped = empty = errs = 0
    t0 = time.time()
    for i, sym in enumerate(tickers):
        path = os.path.join(raw_dir, f"{sym}.json")
        if os.path.exists(path):
            skipped += 1
            continue
        rows = None
        for attempt in range(3):
            try:
                rows = _fetch(sym, start, end)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as ex:
                print(f"[collect] {sym} retry {attempt + 1} ({type(ex).__name__})", file=sys.stderr, flush=True)
                time.sleep(sleep * (attempt + 3) * 2)
        if rows is None:
            errs += 1
            print(f"[collect] {sym} ERROR", file=sys.stderr, flush=True)
            time.sleep(sleep)
            continue
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"ticker": sym, "rows": rows}, fh)
        os.replace(tmp, path)
        done += 1
        if not rows:
            empty += 1
        if (i + 1) % 100 == 0:
            print(f"[collect] progress {i + 1}/{len(tickers)} done={done} skipped={skipped} empty={empty} "
                  f"errors={errs} elapsed_s={time.time() - t0:.0f}", file=sys.stderr, flush=True)
        time.sleep(sleep)
    print(f"[collect] DONE tickers={len(tickers)} done={done} skipped={skipped} empty={empty} errors={errs} "
          f"elapsed_s={time.time() - t0:.0f}", file=sys.stderr, flush=True)


def main() -> None:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)

    def opt(name: str, default: str) -> str:
        return a[a.index(name) + 1] if name in a else default

    if a[0] == "universe":
        universe(a[1], a[2], a[3])
    elif a[0] == "collect":
        collect(a[1], a[2], float(opt("--sleep", "1.2")), opt("--start", "19960101"), opt("--end", "20261002"))
    else:
        print(f"unknown mode: {a[0]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
