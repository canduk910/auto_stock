"""cycle353 F2 — 2차 실측 (읽기 전용, SELECT 만). 운영 backend 컨테이너 안에서 실행.

(a) 전 전략 체결 (BUY/SELL COMPLETED) — 페어·가격대별 성과용
(b) 퍼널 최종 단계 생존 종목 (VB step6 · LTV step7 · 나머지 최종 step)
(c) 캡·폴백 마커 (system_logs 접두 = "[로거] 메시지" 라 앞뒤 % 필요)
(d) 지금 stock_master 에서 VB/LTV 유니버스 조건을 통과하는 행 전부 + 가격 raw 키
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
    rs = await c.fetch("""SELECT id, timestamp, strategy, ticker, trade_type, price, quantity, profit_loss, status, order_no
        FROM trade_history WHERE status='COMPLETED' ORDER BY timestamp, id""")
    out["trades"] = rows(rs)
    rs = await c.fetch("""SELECT target_date, strategy_id, step_no, step_name, survived_count, survived_tickers,
               is_provisional, snapshot_at
        FROM strategy_funnel_snapshots
        WHERE (strategy_id='volatility_breakout' AND step_no IN (1,2,6))
           OR (strategy_id='long_tail_volatility' AND step_no IN (1,2,7))
           OR (strategy_id IN ('bull_flag_breakout','vcp_breakout','donchian_swing','kojiro') AND step_no=9)
        ORDER BY target_date, strategy_id, step_no""")
    fr = []
    for r in rs:
        d = {k: _j(v) for k, v in dict(r).items()}
        st = d.get("survived_tickers")
        if isinstance(st, str):
            try:
                st = json.loads(st)
            except Exception:
                pass
        tick = []
        if isinstance(st, list):
            for e in st:
                if isinstance(e, dict):
                    tick.append(e.get("ticker"))
                else:
                    tick.append(e)
        d["survived_tickers"] = tick
        fr.append(d)
    out["funnel"] = fr
    rs = await c.fetch("""SELECT timestamp, log_level, left(message, 420) AS message FROM system_logs
        WHERE (message LIKE '%[oversized_fallback]%' OR message LIKE '%[ratio_notional_blocked]%'
               OR message LIKE '%[fallback_notional_capped]%' OR message LIKE '%[ratio_cap_skipped]%'
               OR message LIKE '%[risk_silent_skip]%')
          AND timestamp >= now() - interval '35 days' ORDER BY timestamp""")
    out["markers"] = rows(rs)
    rs = await c.fetch("""SELECT log_level, min(timestamp) t0, count(*) n FROM system_logs GROUP BY 1""")
    out["log_retention"] = rows(rs)
    # 지금 유니버스 조건 통과 행 (VB: mcap>=500억, trade>=500억 / LTV: mcap>=500억, trade>=200억)
    rs = await c.fetch("""SELECT ticker, name, refreshed_at, hts_avls_eok, acml_tr_pbmn_won,
               raw->>'bfdy_clpr' AS bfdy_clpr, raw->>'stck_prpr' AS stck_prpr, raw->>'prdy_clpr' AS prdy_clpr,
               raw->>'stck_sdpr' AS stck_sdpr, nxt_tradable
        FROM stock_master WHERE hts_avls_eok >= 500 AND acml_tr_pbmn_won >= 20000000000
        ORDER BY refreshed_at DESC""")
    out["univ_ltv_now"] = rows(rs)
    rs = await c.fetch("SELECT count(*) n, max(refreshed_at) mx, min(refreshed_at) mn FROM stock_master")
    out["sm_count"] = rows(rs)
    rs = await c.fetch("""SELECT k, count(*) FROM stock_master, jsonb_object_keys(raw) k
        WHERE k ILIKE '%clpr%' OR k ILIKE '%prpr%' OR k ILIKE '%sdpr%' GROUP BY 1 ORDER BY 2 DESC""")
    out["raw_price_keys"] = [tuple(r) for r in rs]
    await c.close()
    print(json.dumps(out, ensure_ascii=False, default=str))


asyncio.run(main())
