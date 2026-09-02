import asyncio
from src.db import pg
async def main():
    await pg.init_pool()
    r = await pg.fetchrow("select min(timestamp) mn, max(timestamp) mx, count(*) n from system_logs")
    print("RANGE", r)
    for pat in ("%236200%", "%012750%", "%192820%", "%095340%", "%000815%"):
        rows = await pg.fetch("""select to_char(timestamp at time zone 'Asia/Seoul','MM-DD HH24:MI') ts, left(message,200) m from system_logs
            where message like $1 and (message ilike '%atr%' or message ilike '%unit%' or message ilike '%sizing%') order by timestamp limit 6""", pat)
        print("###", pat, len(rows))
        for x in rows: print("  ", x["ts"], x["m"])
    await pg.close_pool()
asyncio.run(main())
