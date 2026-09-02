import asyncio, json
from src.db import pg
async def main():
    await pg.init_pool()
    out = {}
    out["trades_strat"] = await pg.fetch("""
        select id::text, to_char(timestamp at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') ts_kst,
               ticker, ticker_name, trade_type, price::float8 price, quantity, profit_loss::float8 profit_loss, status, strategy, order_no
        from trade_history where strategy in ('donchian_swing','kojiro') order by timestamp""")
    tickers = sorted({r["ticker"] for r in out["trades_strat"]})
    pos = await pg.fetch("select ticker,ticker_name,buy_price,quantity,strategy_id,buy_date::text buy_date,high_since_buy from positions")
    out["positions"] = pos
    tickers = sorted(set(tickers) | {p["ticker"] for p in pos})
    out["trades_any"] = await pg.fetch("""
        select id::text, to_char(timestamp at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') ts_kst,
               ticker, ticker_name, trade_type, price::float8 price, quantity, profit_loss::float8 profit_loss, status, strategy, order_no
        from trade_history where ticker = any($1::text[]) order by timestamp""", tickers)
    out["daily"] = await pg.fetch("""
        select ticker, bas_dd::text bas_dd, open_price o, high_price h, low_price l, close_price c, volume v, flng_cls_code, prtt_rate::float8 prtt_rate
        from stock_master_daily where ticker = any($1::text[]) and bas_dd >= '2026-03-01' order by ticker, bas_dd""", tickers)
    out["perf"] = await pg.fetch("""
        select date::text d, strategy, total_asset::float8 total_asset, daily_profit_rate::float8 dpr, daily_realized_pnl::float8 rpnl, deposit::float8 deposit
        from daily_performance where date >= '2026-05-01' order by date, strategy""")
    out["cfg"] = await pg.fetch("select strategy_id, enabled, weight::float8 weight, params from strategy_config")
    out["syscfg"] = await pg.fetch("select * from system_config")
    out["tickers"] = tickers
    print(json.dumps(out, default=str, ensure_ascii=False))
    await pg.close_pool()
asyncio.run(main())
