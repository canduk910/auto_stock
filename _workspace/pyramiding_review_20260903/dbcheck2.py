import asyncio, json
from src.db import pg
async def main():
    await pg.init_pool()
    rows = await pg.fetch("""SELECT p.ticker, p.strategy_id, COUNT(d.bas_dd) n_daily, MAX(d.bas_dd)::text last_dd
                             FROM positions p LEFT JOIN stock_master_daily d ON d.ticker = p.ticker
                             GROUP BY p.ticker, p.strategy_id ORDER BY p.strategy_id, p.ticker""")
    print("DAILY_COVERAGE", [dict(r) for r in rows])
    n = await pg.fetch("SELECT COUNT(DISTINCT ticker) n FROM stock_master_daily")
    print("DAILY_DISTINCT_TICKERS", [dict(r) for r in n])
    await pg.close_pool()
asyncio.run(main())
