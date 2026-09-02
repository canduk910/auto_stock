import asyncio, json
from src.db import pg
async def main():
    await pg.init_pool()
    q = """select to_char(timestamp at time zone 'Asia/Seoul','MM-DD HH24:MI') ts, left(message,220) m from system_logs
           where timestamp >= now() - interval '75 days' and (message like %s) order by timestamp limit %d"""
    for pat, lim in (("%[kojiro_recompute] 236200%",3),("%[kojiro_recompute] 012750%",3),("%[kojiro_recompute] 111770%",2),
                     ("%donchian_turtle_stop] 096770%",3),("%donchian_turtle_stop]%",6),("%entry_atr%192820%",4),("%entry_atr%095340%",3),("%kojiro_buy%236200%",3),("%kojiro%ATR%236200%",3)):
        rows = await pg.fetch(q.replace("%s","$1").replace("%d",str(lim)), pat)
        print("###", pat)
        for r in rows: print("  ", r["ts"], r["m"])
    await pg.close_pool()
asyncio.run(main())
