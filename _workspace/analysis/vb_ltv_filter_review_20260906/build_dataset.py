#!/usr/bin/env python3
"""VB 관찰 훅 재검정 — 데이터 추출 (읽기 전용, SELECT 만).

운영 DB 는 `ssh auto-stock` 경유 psql 로만 접근한다. 모든 쿼리는 SELECT 이며
결과는 0x1F(unit separator) 구분 텍스트로 data/ 아래에 저장된다.

산출:
  data/funnel_vb_raw.usv      strategy_funnel_snapshots VB step 6~9 전 기간 (JSON 포함)
  data/daily_raw.usv          stock_master_daily 2026-06-01~ 전 종목 OHLCV
  data/trades_raw.usv         trade_history VB·LTV 2026-07-01~
  data/strategy_config.usv    VB·LTV 설정
  data/funnel_long.csv        롱 포맷 (target_date, snapshot_at_kst, is_provisional, step, ticker, score)
"""
from __future__ import annotations

import csv
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
SEP = "\x1f"


def run_sql(sql: str, out_path: str) -> int:
    """SELECT 하나를 원격 psql 로 실행해 out_path 에 저장. 행 수 반환."""
    assert sql.lstrip().upper().startswith("SELECT"), "SELECT only"
    remote = (
        "cd ~/auto_stock && "
        "DSN=$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '\"') && "
        "psql \"$DSN\" -X -q -At -F $'\\x1f' -c " + shlex.quote(sql)
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(
            ["ssh", "auto-stock", "bash", "-s"],
            input=remote, text=True, stdout=fh, stderr=subprocess.PIPE,
        )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"psql failed: {out_path}")
    with open(out_path, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


QUERIES = {
    "funnel_vb_raw.usv": (
        "SELECT id, target_date, "
        "to_char(snapshot_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') AS snapshot_kst, "
        "step_no, is_provisional, survived_count, survived_tickers::text "
        "FROM strategy_funnel_snapshots "
        "WHERE strategy_id='volatility_breakout' AND step_no IN (6,7,8,9) "
        "ORDER BY target_date, snapshot_at, step_no"
    ),
    "daily_raw.usv": (
        "SELECT ticker, bas_dd, open_price, high_price, low_price, close_price, volume, trade_value, change_rate "
        "FROM stock_master_daily WHERE bas_dd >= '2026-06-01' ORDER BY ticker, bas_dd"
    ),
    "trades_raw.usv": (
        "SELECT id, to_char(timestamp AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') AS ts_kst, "
        "ticker, ticker_name, trade_type, price, quantity, profit_loss, status, strategy, order_no "
        "FROM trade_history WHERE strategy IN ('volatility_breakout','long_tail_volatility') "
        "AND timestamp >= '2026-07-01 00:00:00+09' ORDER BY timestamp"
    ),
    "strategy_config.usv": (
        "SELECT strategy_id, enabled, weight, params::text FROM strategy_config "
        "WHERE strategy_id IN ('volatility_breakout','long_tail_volatility')"
    ),
}


def build_funnel_long() -> None:
    src = os.path.join(DATA, "funnel_vb_raw.usv")
    dst = os.path.join(DATA, "funnel_long.csv")
    n = 0
    with open(src, encoding="utf-8") as fh, open(dst, "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["snapshot_id", "target_date", "snapshot_at_kst", "is_provisional",
                    "step_no", "ticker", "f_score", "mf_rank", "rs", "rsi"])
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            sid, tdate, snap, step, prov, cnt, js = line.split(SEP, 6)
            items = json.loads(js) if js else []
            for it in items:
                t = str(it.get("ticker", "")).strip()
                if not t:
                    continue
                w.writerow([sid, tdate, snap, prov, step, t,
                            it.get("f_score"), it.get("mf_rank"), it.get("rs"), it.get("rsi")])
                n += 1
    print(f"funnel_long.csv rows={n}")


if __name__ == "__main__":
    only = set(sys.argv[1:])
    for fname, sql in QUERIES.items():
        if only and fname not in only:
            continue
        rows = run_sql(sql, os.path.join(DATA, fname))
        print(f"{fname}: {rows} rows")
    build_funnel_long()
