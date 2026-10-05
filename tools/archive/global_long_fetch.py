#!/usr/bin/env python3
"""여러 나라 자산배분 연구용 장기 원자료 수집 — 매매 DB 밖 보관소 ``data/archive/global_long/raw/``.

출처
- Yahoo Finance chart API(v8, 일봉 · 지수 종가) — 평범한 curl 로 받힌다.
- FRED ``fredgraph.csv`` — 평범한 curl 은 응답이 없어 insane-search 엔진(``engine.fetch``)으로 받는다
  (2026-09-11 사용자 지시 · 외부 검색 규칙).

원본을 그대로 저장한다(Yahoo = JSON, FRED = CSV). 가공은 ``tools/replay/global_alloc_data.py`` 가 한다.

    python3 tools/archive/global_long_fetch.py <out_dir>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

YAHOO = ["^GSPC", "^SP500TR", "^NDX", "^XNDX", "^N225", "^HSI", "^HSCE", "000001.SS", "000300.SS",
         "^TNX", "^IRX", "KRW=X", "JPY=X", "HKD=X", "^KS200", "^KS11"]
FRED = ["DGS10", "DTB3", "DEXKOUS", "DEXJPUS", "DEXHKUS", "IR3TIB01KRM156N", "IR3TIB01JPM156N",
        "IRLTLT01KRM156N", "INTDSRKRM193N", "IRSTCI01KRM156N"]
INSANE = os.path.expanduser(
    "~/.claude/plugins/cache/gptaku-plugins/insane-search/0.16.3/skills/insane-search")


def yahoo(sym: str, out: str) -> str:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2=9999999999&interval=1d"
    path = os.path.join(out, "yahoo_" + sym.replace("^", "").replace("=", "_") + ".json")
    subprocess.run(["curl", "-s", "-m", "120", "-A", "Mozilla/5.0", url, "-o", path], check=True)
    with open(path) as f:
        j = json.load(f)
    n = len(j["chart"]["result"][0]["timestamp"])
    return f"{sym} {n} rows -> {os.path.basename(path)}"


def fred(sid: str, out: str) -> str:
    if INSANE not in sys.path:
        sys.path.insert(0, INSANE)
    from engine import fetch  # noqa: E402  (insane-search)
    r = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", max_attempts=3,
              enable_markdown=False, enable_extraction=False)
    txt = r.content or ""
    if not txt.lstrip().startswith(("observation_date", "DATE")):
        return f"{sid} FAIL ({r.verdict}, {len(txt)} bytes)"
    path = os.path.join(out, f"fred_{sid}.csv")
    with open(path, "w") as f:
        f.write(txt)
    return f"{sid} {txt.count(chr(10))} rows -> {os.path.basename(path)}"


def main(out_dir: str) -> None:
    raw = os.path.join(out_dir, "raw")
    os.makedirs(raw, exist_ok=True)
    log = []
    for s in YAHOO:
        try:
            log.append(yahoo(s, raw))
        except Exception as e:  # 한 심볼 실패가 전체를 멈추지 않게
            log.append(f"{s} FAIL {e!r}"[:200])
        time.sleep(1)
    for s in FRED:
        try:
            log.append(fred(s, raw))
        except Exception as e:
            log.append(f"{s} FAIL {e!r}"[:200])
    stamp = time.strftime("%Y-%m-%d %H:%M:%S KST")
    with open(os.path.join(out_dir, "fetch_log.txt"), "a") as f:
        f.write(f"# {stamp}\n" + "\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main(sys.argv[1])
