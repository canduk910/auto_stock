"""cycle347 VCP 체결 0건 원인 실측 — 3차 (읽기 전용). system_logs 추적 + nxt_tradable + 라이브 targets 대조."""
import asyncio, os, json, urllib.request
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
CROSS = ["413630", "051160", "029460", "071320", "003490"]

async def main():
    c = await asyncpg.connect(DSN)
    print("== nxt_tradable of crossing tickers")
    for r in await c.fetch("SELECT ticker, name, nxt_tradable FROM stock_master WHERE ticker = ANY($1)", CROSS):
        print(dict(r))
    print("== WARNING+ vcp markers since 09-14 (retention 08-24~)")
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, log_level, left(message,260) m FROM system_logs
        WHERE timestamp >= '2026-09-13 15:00+00' AND log_level <> 'INFO' AND (message ILIKE '%vcp%') ORDER BY timestamp"""):
        print(r["ts"], r["log_level"], r["m"])
    print("== INFO vcp markers (retention 09-21 21:31 KST~)")
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, left(message,300) m FROM system_logs
        WHERE log_level='INFO' AND (message ILIKE '%vcp%' ) ORDER BY timestamp"""):
        print(r["ts"], r["m"])
    print("== INFO mentioning crossing tickers")
    for t in CROSS:
        rows = await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, log_level, left(message,260) m FROM system_logs
            WHERE timestamp >= '2026-09-13 15:00+00' AND message LIKE '%' || $1 || '%' ORDER BY timestamp LIMIT 40""", t)
        print("--", t, len(rows))
        for r in rows: print(r["ts"], r["log_level"], r["m"])
    print("== subscription / tradable_skip samples")
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, left(message,400) m FROM system_logs
        WHERE message LIKE '%실시간 시세 구독 완료%' ORDER BY timestamp"""):
        print(r["ts"], r["m"])
    for r in await c.fetch("""SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, left(message,300) m FROM system_logs
        WHERE message LIKE '[tradable_skip]%' AND message LIKE '%vcp%' ORDER BY timestamp LIMIT 5"""):
        print(r["ts"], r["m"])
    print("== llm_buy_evaluations vcp:", await c.fetchval("SELECT count(*) FROM llm_buy_evaluations WHERE strategy_id='vcp_breakout'"))
    await c.close()

    key = os.environ.get("API_AUTH_KEY", "")
    try:
        req = urllib.request.Request("http://localhost:8000/api/trading/status", headers={"X-API-Key": key})
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]
        strat = d.get("strategies", {}).get("vcp_breakout") or {}
        tg = strat.get("targets", {})
        print("== live targets (09-24 prepare):", len(tg))
        for t, v in tg.items():
            print(t, v.get("name"), "base_high", v.get("base_high"), "base_low", v.get("base_low"), "prev_close", v.get("prev_close"), "vol_thr", v.get("volume_threshold"))
        print("live state keys:", list(strat.keys())[:30])
        print("positions:", strat.get("positions"), "total_investment:", strat.get("total_investment"))
    except Exception as e:
        print("live status failed", e)

asyncio.run(main())
