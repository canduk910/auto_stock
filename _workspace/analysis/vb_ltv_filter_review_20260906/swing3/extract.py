#!/usr/bin/env python3
"""스윙 3전략(donchian·kojiro·VCP) 후보-레벨 관측 — 원천 추출 (SELECT 만).

운영 DB 는 `ssh auto-stock` 경유 psql. build_dataset.py 접속 패턴 재사용.
결과는 0x1F(unit separator) 구분 텍스트로 data/ 아래 저장.
"""
from __future__ import annotations
import os, shlex, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)


def run_sql(sql: str, out_path: str) -> int:
    assert sql.lstrip().upper().startswith("SELECT"), "SELECT only"
    remote = (
        "cd ~/auto_stock && "
        "DSN=$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '\"') && "
        "psql \"$DSN\" -X -q -At -F $'\\x1f' -c " + shlex.quote(sql)
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(["ssh", "auto-stock", "bash", "-s"],
                              input=remote, text=True, stdout=fh, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"psql failed: {out_path}")
    with open(out_path, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


QUERIES = {
    # 1) 세 전략 funnel 전 단계 (+ BFB 참고)
    "funnel_raw.usv": (
        "SELECT strategy_id, target_date::text, "
        "to_char(snapshot_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'), "
        "step_no, step_name, is_provisional::text, survived_count, excluded_count, "
        "coalesce(survived_tickers::text,'[]') "
        "FROM strategy_funnel_snapshots "
        "WHERE strategy_id IN ('donchian_swing','kojiro','vcp_breakout','bull_flag_breakout') "
        "ORDER BY strategy_id, target_date, step_no"
    ),
    # 2) 일봉 전체 (RS/RSI/ATR/EMA/성과 산출용)
    "daily_raw.usv": (
        "SELECT ticker, bas_dd::text, open_price, high_price, low_price, close_price, "
        "volume, trade_value, change_rate, "
        "to_char(created_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD') "
        "FROM stock_master_daily ORDER BY ticker, bas_dd"
    ),
    # 3) 재무 (F-Score-7 · 마법공식)
    "fin_raw.usv": (
        "SELECT ticker, stac_yymm, div_cls, sale_account, sale_totl_prfi, bsop_prti, "
        "thtr_ntin, depr_cost, cras, fxas, total_aset, flow_lblt, total_lblt, total_cptl, "
        "cpfn, cptl_ntin_rate, sale_totl_rate, lblt_rate, crnt_rate, ebitda, ev_ebitda, "
        "to_char(refreshed_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD') "
        "FROM stock_master_financial ORDER BY ticker, stac_yymm, div_cls"
    ),
    # 4) 종목마스터 (시총 = 마법공식 EV 폴백 · 이름)
    "master_raw.usv": (
        "SELECT ticker, coalesce(name,''), coalesce(hts_avls_eok,0), "
        "coalesce(acml_tr_pbmn_won,0), coalesce(is_kospi200,false)::text, "
        "coalesce(is_kosdaq150,false)::text, coalesce(nxt_tradable,true)::text "
        "FROM stock_master ORDER BY ticker"
    ),
    # 5) 실체결
    "trades_raw.usv": (
        "SELECT id::text, to_char(timestamp AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'), "
        "ticker, coalesce(ticker_name,''), trade_type, price, quantity, "
        "coalesce(profit_loss,0), status, strategy, coalesce(order_no,'') "
        "FROM trade_history WHERE strategy IN "
        "('donchian_swing','kojiro','vcp_breakout','bull_flag_breakout') ORDER BY timestamp"
    ),
}

if __name__ == "__main__":
    only = set(sys.argv[1:])
    for fname, sql in QUERIES.items():
        if only and fname not in only:
            continue
        print(f"{fname}: {run_sql(sql, os.path.join(DATA, fname))} rows", flush=True)
