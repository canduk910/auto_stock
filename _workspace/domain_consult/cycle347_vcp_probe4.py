"""cycle347 — 4차 (읽기 전용). 돌파 발생일의 장중 로그 정밀 추적."""
import asyncio, os
import asyncpg
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
Q = """SELECT timestamp AT TIME ZONE 'Asia/Seoul' ts, log_level, left(message,330) m FROM system_logs
 WHERE timestamp >= ($1::timestamp AT TIME ZONE 'Asia/Seoul') AND timestamp < ($2::timestamp AT TIME ZONE 'Asia/Seoul') AND {cond} ORDER BY timestamp"""
async def show(c, title, a, b, cond, *args, limit=60):
    rows = await c.fetch(Q.format(cond=cond) + f" LIMIT {limit}", a, b, *args)
    print(f"== {title} ({len(rows)})")
    for r in rows: print(r["ts"], r["log_level"], r["m"])
async def main():
    c = await asyncpg.connect(DSN)
    import datetime as dt
    D = lambda s: dt.datetime.fromisoformat(s)
    for day, tks in (("2026-09-21", ["029460", "071320"]), ("2026-09-22", ["071320", "029460"]), ("2026-09-23", ["003490"])):
        for t in tks:
            await show(c, f"{day} {t} 08:00-15:30 (stale 재등록 제외)", D(day+" 08:00"), D(day+" 15:31"),
                       "message LIKE '%' || $3 || '%' AND message NOT LIKE '%강제 재%' AND message NOT LIKE '%실시간 시세 구독 완료%'", t)
    for day in ("2026-09-21", "2026-09-22", "2026-09-23"):
        await show(c, f"{day} vcp/VCP 전체(구독 완료·설정 로드 제외)", D(day+" 07:00"), D(day+" 16:00"),
                   "(message ILIKE '%vcp%') AND message NOT LIKE '%실시간 시세 구독 완료%' AND message NOT LIKE '%DB 전략 설정 로드%' AND message NOT LIKE '[tradable_skip]%'")
        await show(c, f"{day} tradable_skip 장중 vcp 포함", D(day+" 09:05"), D(day+" 14:31"),
                   "message LIKE '[tradable_skip]%' AND message LIKE '%vcp_breakout%'", limit=3)
        await show(c, f"{day} 자금배분/allocate", D(day+" 07:00"), D(day+" 16:00"),
                   "(message ILIKE '%allocate%' OR message LIKE '%자금 배분%' OR message LIKE '%투자금%' OR message LIKE '%cash_usage_ratio_source%')", limit=15)
        await show(c, f"{day} 재시작/boot", D(day+" 07:00"), D(day+" 16:30"),
                   "(message LIKE '%_boot%' OR message LIKE '%서버 시작%' OR message LIKE '%매매 시작%' OR message LIKE '%startup%')", limit=15)
    await c.close()
asyncio.run(main())
