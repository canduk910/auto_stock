"""cycle352 — 일봉 전수 덤프(모집단 분석용, 읽기 전용 SELECT 만). stdout = CSV."""
import asyncio, os, sys
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")

async def main():
    c = await asyncpg.connect(DSN)
    w = sys.stdout.write
    w("ticker,d,o,h,l,c,v,tv,mcap_eok_now,name\n")
    mc = {r["ticker"]: (r["hts_avls_eok"], r["name"]) for r in await c.fetch(
        "SELECT ticker, hts_avls_eok, coalesce(name,'') AS name FROM stock_master")}
    async with c.transaction():
        async for r in c.cursor("""SELECT ticker, to_char(bas_dd,'YYYY-MM-DD') d, open_price o, high_price h,
                low_price l, close_price c, volume v, trade_value tv FROM stock_master_daily ORDER BY ticker, bas_dd""",
                prefetch=5000):
            m, n = mc.get(r["ticker"], (None, ""))
            w(f'{r["ticker"]},{r["d"]},{r["o"]},{r["h"]},{r["l"]},{r["c"]},{r["v"]},{r["tv"]},{m if m is not None else ""},{n.replace(",", " ")}\n')
    await c.close()

asyncio.run(main())
