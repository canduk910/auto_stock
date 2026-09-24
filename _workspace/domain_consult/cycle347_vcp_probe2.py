"""cycle347 VCP 체결 0건 원인 실측 — 2차 (읽기 전용, SELECT 만).

후보(funnel step 9) × 날짜마다 prepare 의 _detect_base 를 D-1 까지 일봉으로 재현해
base_high 를 구하고, 그날 실제 시가/고가/종가/거래량과 대조한다.
"""
import asyncio, os, json
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")

def detect_base(rows, base_min, base_max, depth_pct):
    highs = [r["high_price"] for r in rows]; lows = [r["low_price"] for r in rows]; vols = [r["volume"] for r in rows]
    for length in range(base_max, base_min - 1, -1):
        if length > len(rows): continue
        h = max(highs[:length]); lo = min(lows[:length])
        if h <= 0 or lo <= 0: continue
        if (h - lo) / h > depth_pct: continue
        return {"high": h, "low": lo, "length": length, "avg20": int(sum(vols[:20]) / 20) if len(vols) >= 20 else 0,
                "high_age": highs[:length].index(h)}
    return None

async def main():
    c = await asyncpg.connect(DSN)
    snaps = await c.fetch("""SELECT DISTINCT ON (target_date) target_date, survived_tickers FROM strategy_funnel_snapshots
        WHERE strategy_id='vcp_breakout' AND step_no=99 AND target_date >= '2026-09-14' ORDER BY target_date, snapshot_at DESC""")
    VM = 1.2; CAP = 7.5; DEPTH = 0.35
    summary = []
    for s in snaps:
        D = s["target_date"]; tick = s["survived_tickers"]
        if isinstance(tick, str): tick = json.loads(tick)
        base_max = 40 if str(D) >= "2026-09-19" else 75
        for t in tick:
            hist = await c.fetch("SELECT bas_dd, open_price, high_price, low_price, close_price, volume FROM stock_master_daily WHERE ticker=$1 AND bas_dd < $2 ORDER BY bas_dd DESC LIMIT 260", t, D)
            day = await c.fetchrow("SELECT open_price, high_price, low_price, close_price, volume FROM stock_master_daily WHERE ticker=$1 AND bas_dd=$2", t, D)
            name = await c.fetchval("SELECT name FROM stock_master WHERE ticker=$1", t)
            b = detect_base([dict(x) for x in hist], 25, base_max, DEPTH)
            if not b or not day:
                print(D, t, name, "base" if b else "NOBASE", "day" if day else "NODAY"); continue
            bh = b["high"]; pc = hist[0]["close_price"]
            thr = int(b["avg20"] * VM)
            crossed = day["high_price"] >= bh
            gap_ext = (day["open_price"] - bh) / bh * 100
            row = dict(date=str(D), t=t, name=name, base_len=b["length"], high_age=b["high_age"], base_high=bh, base_low=b["low"],
                       prev_close=pc, dist_pct=round((bh - pc) / pc * 100, 2),
                       o=day["open_price"], h=day["high_price"], cl=day["close_price"], vol=day["volume"], vol_thr=thr,
                       crossed=crossed, gap_ext_pct=round(gap_ext, 2), vol_ratio=round(day["volume"] / thr, 2) if thr else None,
                       close_vs_bh=round((day["close_price"] - bh) / bh * 100, 2))
            summary.append(row)
            print(json.dumps(row, ensure_ascii=False))
    post = [r for r in summary if r["date"] >= "2026-09-19"]
    import statistics
    for label, rs in (("pre-G", [r for r in summary if r["date"] < "2026-09-19"]), ("post-G", post)):
        if not rs: continue
        print(label, "n=", len(rs), "crossed=", sum(r["crossed"] for r in rs),
              "median dist_pct=", statistics.median(r["dist_pct"] for r in rs),
              "median high_age=", statistics.median(r["high_age"] for r in rs))
    await c.close()

asyncio.run(main())
