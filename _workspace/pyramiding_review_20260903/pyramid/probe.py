import asyncio, json
from src.db import pg
async def main():
    await pg.init_pool()
    cols = await pg.fetch("select column_name,data_type from information_schema.columns where table_name='trade_history' order by ordinal_position")
    print("COLS", json.dumps(cols, default=str))
    r = await pg.fetch("""select strategy, trade_type, status, count(*) n, min(timestamp) mn, max(timestamp) mx
        from trade_history where strategy in ('donchian_swing','kojiro') group by 1,2,3 order by 1,2,3""")
    print("COUNTS", json.dumps(r, default=str))
    r2 = await pg.fetch("select ticker,ticker_name,buy_price,quantity,strategy_id,buy_date,high_since_buy from positions order by buy_date")
    print("POS", json.dumps(r2, default=str))
    r3 = await pg.fetch("select strategy_id, enabled, weight, params from strategy_config where strategy_id in ('donchian_swing','kojiro')")
    print("CFG", json.dumps(r3, default=str))
    r4 = await pg.fetch("select min(bas_dd) mn, max(bas_dd) mx, count(distinct ticker) nt, count(*) n from stock_master_daily")
    print("DAILY", json.dumps(r4, default=str))
    await pg.close_pool()
asyncio.run(main())
