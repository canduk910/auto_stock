"""cycle353 F2 스캔 단계 주가 상한 — 1차 실측 (읽기 전용, SELECT 만).

운영 backend 컨테이너 안에서 실행한다(DATABASE_URL 은 컨테이너 env).
출력 = JSON 한 덩어리(stdout).
"""
import asyncio, os, json, datetime, decimal
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")


def _j(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def rows(rs):
    return [{k: _j(v) for k, v in dict(r).items()} for r in rs]


async def main():
    c = await asyncpg.connect(DSN)
    out = {}
    # 1) 전략 설정
    rs = await c.fetch("SELECT strategy_id, enabled, weight, params, updated_at FROM strategy_config ORDER BY strategy_id")
    cfg = {}
    for r in rs:
        p = r["params"] if isinstance(r["params"], dict) else json.loads(r["params"] or "{}")
        keep = {k: p.get(k) for k in (
            "position_ratio", "max_positions", "max_scan_stocks", "min_market_cap", "min_trade_amount",
            "sizing_mode", "risk_pct", "max_lot_ratio_mult", "max_lot_units", "stop_loss_rate",
            "intraday_stop_loss", "overnight_stop_loss", "k_value_krx_main", "min_prdy_rate",
            "tradable_boards", "exchange", "buy_threshold", "gap_up_threshold",
        ) if k in p}
        cfg[r["strategy_id"]] = {"enabled": r["enabled"], "weight": _j(r["weight"]), "params": keep,
                                 "updated_at": _j(r["updated_at"])}
    out["strategy_config"] = cfg
    # 2) system_config 관련 키
    cols = await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='system_config' ORDER BY ordinal_position")
    out["system_config_cols"] = [x[0] for x in cols]
    try:
        rs = await c.fetch("SELECT key, value, updated_at FROM system_config WHERE key ILIKE ANY(ARRAY['%price_filter%','%cash_usage%','%auto_regime%','%trade_amount_filter%','%dkstock%'])")
        out["system_config"] = rows(rs)
    except Exception as e:
        out["system_config_err"] = repr(e)
    # 3) 순자산 — daily_performance 의 total 행
    cols = await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='daily_performance' ORDER BY ordinal_position")
    out["dp_cols"] = [x[0] for x in cols]
    rs = await c.fetch("SELECT * FROM daily_performance WHERE strategy='total' ORDER BY date DESC LIMIT 8")
    out["dp_total"] = rows(rs)
    rs = await c.fetch("SELECT * FROM daily_performance WHERE date=(SELECT max(date) FROM daily_performance) ORDER BY strategy")
    out["dp_latest_all"] = rows(rs)
    # 4) 부팅 자금 분배 로그 (최근)
    rs = await c.fetch("""SELECT timestamp, log_level, left(message, 300) AS message FROM system_logs
        WHERE (message LIKE '%%자금 분배%%' OR message LIKE '[cash_usage_ratio]%%' OR message LIKE '%%ratio_cap_config%%')
          AND timestamp >= now() - interval '6 days' ORDER BY timestamp DESC LIMIT 60""")
    out["alloc_logs"] = rows(rs)
    # 5) 캡·폴백 마커 (최근)
    rs = await c.fetch("""SELECT timestamp, log_level, left(message, 400) AS message FROM system_logs
        WHERE (message LIKE '[oversized_fallback]%%' OR message LIKE '[ratio_notional_blocked]%%'
               OR message LIKE '[fallback_notional_capped]%%' OR message LIKE '[risk_silent_skip]%%'
               OR message LIKE '%%매수 수량 0%%')
          AND timestamp >= now() - interval '12 days' ORDER BY timestamp DESC LIMIT 200""")
    out["cap_logs"] = rows(rs)
    # 6) trade_history 컬럼 + 매수 체결 요약
    cols = await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='trade_history' ORDER BY ordinal_position")
    out["th_cols"] = [x[0] for x in cols]
    rs = await c.fetch("""SELECT strategy, count(*) n, min(timestamp) first_ts, max(timestamp) last_ts
        FROM trade_history WHERE trade_type='BUY' AND status='COMPLETED' GROUP BY 1 ORDER BY 1""")
    out["buy_summary"] = rows(rs)
    rs = await c.fetch("""SELECT timestamp, strategy, ticker, price, quantity, status FROM trade_history
        WHERE trade_type='BUY' AND timestamp >= '2026-09-20' ORDER BY timestamp""")
    out["buys_since_0920"] = rows(rs)
    # 7) funnel snapshots 구조
    cols = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='strategy_funnel_snapshots' ORDER BY ordinal_position")
    out["funnel_cols"] = [(x[0], x[1]) for x in cols]
    rs = await c.fetch("""SELECT strategy_id, step_no, count(*) n, min(target_date) d0, max(target_date) d1
        FROM strategy_funnel_snapshots GROUP BY 1,2 ORDER BY 1,2""")
    out["funnel_coverage"] = rows(rs)
    await c.close()
    print(json.dumps(out, ensure_ascii=False, default=str))


asyncio.run(main())
