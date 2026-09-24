"""cycle347 VCP 체결 0건 원인 실측 — 1차 (읽기 전용, SELECT 만)."""
import asyncio, os, json
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")

async def main():
    c = await asyncpg.connect(DSN)
    r = await c.fetchrow("SELECT params, enabled, weight FROM strategy_config WHERE strategy_id='vcp_breakout'")
    p = r["params"] if isinstance(r["params"], dict) else json.loads(r["params"])
    print("== strategy_config enabled=", r["enabled"], "weight=", r["weight"])
    print(json.dumps(p, ensure_ascii=False, sort_keys=True))

    for t in ("trade_history", "llm_buy_evaluations", "system_logs", "strategy_funnel_snapshots"):
        cols = await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name=$1 ORDER BY ordinal_position", t)
        print("cols", t, [x[0] for x in cols][:40])

    rows = await c.fetch("SELECT strategy, trade_type, status, count(*) FROM trade_history WHERE strategy ILIKE '%vcp%' GROUP BY 1,2,3")
    print("== trade_history vcp:", [dict(x) for x in rows])

    rows = await c.fetch("""SELECT target_date, step_no, survived_count, is_provisional, snapshot_at, survived_tickers
        FROM strategy_funnel_snapshots WHERE strategy_id='vcp_breakout' AND target_date >= '2026-09-14'
        ORDER BY target_date, snapshot_at, step_no""")
    for x in rows:
        st = x["survived_tickers"]
        if isinstance(st, str): st = json.loads(st)
        show = st if x["step_no"] in (9, 99) else ""
        print("funnel", x["target_date"], x["step_no"], x["survived_count"], x["is_provisional"], x["snapshot_at"], show)

    rows = await c.fetch("SELECT log_level, min(timestamp), max(timestamp), count(*) FROM system_logs GROUP BY 1")
    print("== system_logs retention:", [tuple(x) for x in rows])
    await c.close()

asyncio.run(main())
