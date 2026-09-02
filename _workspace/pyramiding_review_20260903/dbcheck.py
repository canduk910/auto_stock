import asyncio, json
from src.db import pg
async def main():
    await pg.init_pool()
    pos = await pg.fetch("SELECT ticker, strategy_id, buy_price, quantity, high_since_buy, buy_date::text, order_no FROM positions ORDER BY strategy_id, ticker")
    print("POSITIONS", json.dumps([dict(r) for r in pos], ensure_ascii=False, default=str))
    cfg = await pg.fetch("SELECT strategy_id, enabled, weight, params FROM strategy_config WHERE strategy_id IN ('kojiro','donchian_swing')")
    for r in cfg:
        p = r["params"] if isinstance(r["params"], dict) else json.loads(r["params"])
        keys = ["risk_pct","sizing_mode","breakeven_promote_atr","max_positions","position_ratio","max_open_risk_pct","stop_atr","trail_atr","hard_stop_pct","max_units_per_stock","max_units_total"]
        print("CFG", r["strategy_id"], r["enabled"], r["weight"], {k: p.get(k, "<absent>") for k in keys})
    sc = await pg.fetch("SELECT key, value FROM system_config WHERE key LIKE 'account_risk%' OR key='cash_usage_ratio'")
    print("SYSCFG", [dict(r) for r in sc])
    dp = await pg.fetch("SELECT date::text, strategy, total_asset FROM daily_performance WHERE strategy='total' ORDER BY date DESC LIMIT 2")
    print("DP", [dict(r) for r in dp])
    th = await pg.fetch("""SELECT strategy, COUNT(*) n, SUM(CASE WHEN quantity=1 THEN 1 ELSE 0 END) one
                           FROM trade_history WHERE trade_type='BUY' AND status='COMPLETED'
                           AND timestamp >= now() - interval '120 days' GROUP BY strategy ORDER BY strategy""")
    print("ONE_SHARE", [dict(r) for r in th])
    await pg.close_pool()
asyncio.run(main())
