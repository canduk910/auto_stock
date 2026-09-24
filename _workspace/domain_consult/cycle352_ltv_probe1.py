"""cycle352 LTV 상한가 당일 트레일링 — 1차 실측 (읽기 전용, SELECT 만)."""
import asyncio, os, json
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")

async def main():
    c = await asyncpg.connect(DSN)
    r = await c.fetchrow("SELECT params, enabled, weight, updated_at FROM strategy_config WHERE strategy_id='long_tail_volatility'")
    p = r["params"] if isinstance(r["params"], dict) else json.loads(r["params"])
    print("== LTV strategy_config enabled=", r["enabled"], "weight=", r["weight"], "updated=", r["updated_at"])
    print(json.dumps(p, ensure_ascii=False, sort_keys=True))
    cols = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='trade_history' ORDER BY ordinal_position")
    print("cols trade_history", [(x[0], x[1]) for x in cols])
    cols = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='positions' ORDER BY ordinal_position")
    print("cols positions", [(x[0], x[1]) for x in cols])
    cols = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='stock_master_daily' ORDER BY ordinal_position")
    print("cols smd", [(x[0], x[1]) for x in cols])
    rows = await c.fetch("SELECT trade_type, status, count(*), min(timestamp), max(timestamp) FROM trade_history WHERE strategy='long_tail_volatility' GROUP BY 1,2 ORDER BY 1,2")
    print("== LTV trades:", [tuple(x) for x in rows])
    rows = await c.fetch("SELECT min(bas_dd), max(bas_dd), count(*), count(distinct ticker) FROM stock_master_daily")
    print("== smd range:", [tuple(x) for x in rows])
    rows = await c.fetch("SELECT min(timestamp), max(timestamp), count(*) FROM system_logs")
    print("== system_logs range:", [tuple(x) for x in rows])
    rows = await c.fetch("SELECT * FROM positions WHERE strategy_id='long_tail_volatility'")
    print("== LTV positions now:", [dict(x) for x in rows])
    await c.close()

asyncio.run(main())
