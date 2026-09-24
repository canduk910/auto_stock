"""cycle347 — 7차 (읽기 전용). 09-21 두 종목의 nxt_tradable 갱신 시각 + 09-21 WARNING 전수(틱·구독 계열)."""
import asyncio, os
import asyncpg
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
async def main():
    c = await asyncpg.connect(DSN)
    cols = [r[0] for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='stock_master'")]
    print("stock_master cols", cols)
    tcols = [x for x in cols if "at" in x or "nxt" in x]
    for r in await c.fetch(f"SELECT ticker, {', '.join(tcols)} FROM stock_master WHERE ticker = ANY($1)", ["029460", "071320", "204620", "180640"]):
        print(dict(r))
    print("== 09-21 07:40-15:35 WARNING/ERROR with priority_drop / tick / subscribe / no_feed")
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, log_level, left(message,400) m FROM system_logs
        WHERE timestamp >= '2026-09-21 07:40+09' AND timestamp < '2026-09-21 15:35+09' AND log_level <> 'INFO'
        AND (message ILIKE '%priority_drop%' OR message ILIKE '%tick%' OR message ILIKE '%구독%' OR message ILIKE '%no_feed%' OR message ILIKE '%channel%')
        ORDER BY timestamp LIMIT 40"""):
        print(r["ts"], r["log_level"], r["m"])
    await c.close()
asyncio.run(main())
