"""cycle347 — 5차 (읽기 전용). 09-21 장중 — 케이씨·지역난방공사 매수가 기대됐는데 없던 날."""
import asyncio, os
import asyncpg
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
async def main():
    c = await asyncpg.connect(DSN)
    print("== trade_history 09-21 by strategy/type")
    for r in await c.fetch("""SELECT strategy, trade_type, status, count(*) FROM trade_history
        WHERE timestamp >= '2026-09-21 00:00+09' AND timestamp < '2026-09-22 00:00+09' GROUP BY 1,2,3 ORDER BY 1"""):
        print(dict(r))
    print("== trade_history 029460/071320/003490 since 09-10")
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, ticker, trade_type, status, strategy, price, quantity FROM trade_history
        WHERE ticker = ANY($1) AND timestamp >= '2026-09-10' ORDER BY timestamp""", ["029460", "071320", "003490"]):
        print(dict(r))
    print("== positions table now")
    for r in await c.fetch("SELECT * FROM positions ORDER BY 1"):
        d = dict(r); print({k: d[k] for k in list(d)[:8]})
    print("== 09-21 09:00-14:35 WARNING/ERROR distinct heads")
    for r in await c.fetch("""SELECT log_level, left(regexp_replace(message,'[0-9]{6}','######','g'),110) h, count(*), min(timestamp AT TIME ZONE 'Asia/Seoul') f
        FROM system_logs WHERE timestamp >= '2026-09-21 09:00+09' AND timestamp < '2026-09-21 14:35+09' AND log_level <> 'INFO'
        GROUP BY 1,2 ORDER BY 3 DESC LIMIT 40"""):
        print(r["log_level"], r["count"], r["f"], r["h"])
    print("== 09-21 WARNING/ERROR mentioning 029460/071320 08:00-15:30")
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, log_level, left(message,300) m FROM system_logs
        WHERE timestamp >= '2026-09-21 08:00+09' AND timestamp < '2026-09-21 15:31+09' AND (message LIKE '%029460%' OR message LIKE '%071320%')"""):
        print(r["ts"], r["log_level"], r["m"])
    print("== daily_log_reports 09-21 metrics strategy_funnel/vcp snippet")
    r = await c.fetchrow("SELECT metrics FROM daily_log_reports WHERE target_date='2026-09-21'")
    if r:
        import json
        m = r["metrics"] if isinstance(r["metrics"], dict) else json.loads(r["metrics"])
        print("keys", list(m.keys()))
        for k in ("strategy_funnel", "signals", "buy_signals", "vcp"):
            if k in m: print(k, json.dumps(m[k], ensure_ascii=False)[:1500])
    await c.close()
asyncio.run(main())
