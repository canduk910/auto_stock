#!/usr/bin/env python3
"""칸 수·예산 사용률 + etf_trend D3 측정용 원자료 추출 (2026-10-11).

READ-ONLY — SELECT 만. 세션 `default_transaction_read_only = on`. KIS 호출 0.
실행(EC2):
    docker compose -f docker-compose.prod.yml exec -T backend python - \
        < extract.py > raw_20261011.json
비밀값(DSN·키)·계좌번호를 출력하지 않는다. 표준출력 = JSON 한 덩어리.
"""
from __future__ import annotations

import asyncio
import json
import os
import ssl as ssl_mod
import urllib.request
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit, urlunsplit

SINCE = date(2026, 6, 1)          # 비교 기간(60영업일)까지 넉넉히
PRIMARY_SINCE = date(2026, 9, 21)
ETF_CANDS_1007 = [
    "455850", "305720", "475300", "471990", "475310", "462010",
    "471760", "457990", "305540", "461950", "455860",
]


def _prep_dsn(dsn: str):
    parts = urlsplit(dsn)
    q = parse_qs(parts.query)
    sslmode = q.pop("sslmode", ["require"])[0]
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path,
                        "&".join(f"{k}={v[0]}" for k, v in q.items()), parts.fragment))
    ctx = None
    if sslmode in ("require", "prefer", "allow", "verify-ca", "verify-full"):
        ctx = ssl_mod.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl_mod.CERT_NONE
    return clean, ctx


def _conv(v):
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _rows(rs):
    return [{k: _conv(v) for k, v in dict(r).items()} for r in rs]


def _api(path: str):
    """백엔드 자기 자신(localhost:8000) GET — 키는 환경변수에서 읽고 출력하지 않는다."""
    key = os.environ.get("API_AUTH_KEY", "")
    req = urllib.request.Request(f"http://localhost:8000{path}", headers={"X-API-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


async def main() -> None:
    import asyncpg

    clean, ctx = _prep_dsn(os.environ["DATABASE_URL"])
    conn = await asyncpg.connect(clean, ssl=ctx)
    out: dict = {}
    try:
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        await conn.execute("SET default_transaction_read_only = on")

        out["strategy_config"] = _rows(await conn.fetch(
            "SELECT strategy_id, enabled, weight, params, "
            "to_char(updated_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') AS updated_kst "
            "FROM strategy_config ORDER BY strategy_id"))
        out["system_config"] = _rows(await conn.fetch(
            "SELECT key, value FROM system_config WHERE key IN "
            "('cash_usage_ratio','auto_regime_adjust','dkstock_regime_enabled')"))
        out["trades"] = _rows(await conn.fetch(
            """SELECT strategy, ticker, trade_type, price, quantity, status, order_no,
                      to_char(timestamp AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD"T"HH24:MI:SS') AS ts_kst
               FROM trade_history
               WHERE timestamp >= ($1::date)::timestamp AT TIME ZONE 'Asia/Seoul'
               ORDER BY timestamp""", SINCE))
        out["daily_performance"] = _rows(await conn.fetch(
            "SELECT * FROM daily_performance WHERE date >= $1 ORDER BY date, strategy", SINCE))
        out["positions"] = _rows(await conn.fetch(
            "SELECT ticker, strategy_id, quantity, buy_price, buy_date FROM positions ORDER BY ticker"))
        out["funnel"] = _rows(await conn.fetch(
            """SELECT target_date, strategy_id, step_no, step_name, survived_count, survived_tickers,
                      is_provisional
               FROM strategy_funnel_snapshots
               WHERE target_date >= $1 ORDER BY strategy_id, target_date, step_no""", PRIMARY_SINCE))
        out["etf_bars"] = _rows(await conn.fetch(
            """SELECT ticker, bas_dd, open_price, high_price, low_price, close_price, volume
               FROM stock_master_daily
               WHERE ticker = ANY($1::text[]) AND bas_dd BETWEEN '2026-09-01' AND '2026-10-10'
               ORDER BY ticker, bas_dd""", ETF_CANDS_1007))
        out["etf_names"] = _rows(await conn.fetch(
            "SELECT ticker, name FROM stock_master WHERE ticker = ANY($1::text[])", ETF_CANDS_1007))
        # 사건 보강 — 비중·파라미터 변경 흔적(WARNING 이상은 보존이 길다)
        out["config_logs"] = _rows(await conn.fetch(
            """SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') AS ts_kst,
                      log_level, left(message, 400) AS message
               FROM system_logs
               WHERE timestamp >= '2026-09-19'
                 AND (message ILIKE '%weights%' OR message ILIKE '%buy_paused%'
                      OR message ILIKE '%params_updated%' OR message ILIKE '%allocate%'
                      OR message ILIKE '%cash_usage_ratio_source%')
               ORDER BY timestamp LIMIT 500"""))
    finally:
        await conn.close()

    out["api_strategies"] = _api("/api/strategies")
    print(json.dumps(out, ensure_ascii=False, default=str))


asyncio.run(main())
