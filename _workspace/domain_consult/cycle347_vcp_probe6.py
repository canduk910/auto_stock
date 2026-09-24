"""cycle347 — 6차 (읽기 전용). 09-21 일일 로그 리포트(metrics) 안에 남은 VCP 흔적."""
import asyncio, os, json
import asyncpg
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from walk(v, f"{path}[{i}]")
    else:
        yield path, o
async def main():
    c = await asyncpg.connect(DSN)
    for d in ("2026-09-21",):
        r = await c.fetchrow("SELECT metrics FROM daily_log_reports WHERE target_date=$1", __import__("datetime").date.fromisoformat(d))
        m = r["metrics"] if isinstance(r["metrics"], dict) else json.loads(r["metrics"])
        print("logs type", type(m.get("logs")), (list(m["logs"].keys()) if isinstance(m.get("logs"), dict) else len(m.get("logs") or [])))
        print("stages vcp", json.dumps((m.get("strategy_funnel_stages") or {}).get("vcp_breakout"), ensure_ascii=False)[:1500])
        print("tick_blind", json.dumps(m.get("tick_blind"), ensure_ascii=False)[:800])
        hits = [(p, v) for p, v in walk(m) if isinstance(v, str) and ("vcp" in v.lower() or "029460" in v or "071320" in v)]
        print("hits", len(hits))
        for p, v in hits[:40]: print(p, str(v)[:250])
    await c.close()
asyncio.run(main())
