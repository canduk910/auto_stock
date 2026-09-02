import asyncio, json
from src.db import pg
async def main():
    await pg.init_pool()
    out={}
    rows = await pg.fetch("""SELECT ticker, ticker_name, strategy, trade_type, price, quantity, status, order_no,
        to_char(timestamp at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') ts
        FROM trade_history WHERE ticker IN ('042700','001440','092220') ORDER BY timestamp""")
    out['multi']=[dict(r) for r in rows]
    cols = await pg.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='stock_master' ORDER BY ordinal_position")
    out['sm_cols']=[r['column_name'] for r in cols]
    rows = await pg.fetch("""WITH latest AS (SELECT max(bas_dd) d FROM stock_master_daily)
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY close_price) med, count(*) n,
               percentile_cont(0.25) WITHIN GROUP (ORDER BY close_price) q1,
               percentile_cont(0.75) WITHIN GROUP (ORDER BY close_price) q3
        FROM stock_master_daily s, latest WHERE s.bas_dd = latest.d AND close_price > 0""")
    out['universe_price_all']=[dict(r) for r in rows]
    try:
        rows = await pg.fetch("""WITH latest AS (SELECT max(bas_dd) d FROM stock_master_daily)
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY s.close_price) med, count(*) n
            FROM stock_master_daily s JOIN stock_master m ON m.ticker=s.ticker, latest
            WHERE s.bas_dd=latest.d AND s.close_price>0 AND (m.is_kospi200 OR m.is_kosdaq150)""")
        out['universe_price_k200_kq150']=[dict(r) for r in rows]
    except Exception as e:
        out['universe_price_k200_kq150']=str(e)
    rows = await pg.fetch("""SELECT strategy, count(*) n,
        sum(CASE WHEN profit_loss>0 THEN 1 ELSE 0 END) wins,
        round(avg(CASE WHEN profit_loss>0 THEN profit_loss END)) avg_win,
        round(avg(CASE WHEN profit_loss<0 THEN profit_loss END)) avg_loss,
        round(avg(CASE WHEN profit_loss>0 THEN profit_loss/(price*quantity-profit_loss)*100 END)::numeric,2) avg_win_pct,
        round(avg(CASE WHEN profit_loss<0 THEN profit_loss/(price*quantity-profit_loss)*100 END)::numeric,2) avg_loss_pct,
        round(sum(profit_loss)) total
        FROM trade_history WHERE trade_type='SELL' AND status IN ('COMPLETED','PARTIAL') AND profit_loss IS NOT NULL
        AND strategy IN ('donchian_swing','kojiro') GROUP BY 1""")
    out['pnl']=[dict(r) for r in rows]
    print(json.dumps(out, default=str, ensure_ascii=False))
    await pg.close_pool()
asyncio.run(main())
