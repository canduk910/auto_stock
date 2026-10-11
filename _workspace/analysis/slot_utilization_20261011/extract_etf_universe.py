#!/usr/bin/env python3
"""etf_trend 유동성·ATR 밴드 통과(funnel step3) ETF 의 일봉 — 예산별 0주 비율 계산용.

READ-ONLY(SELECT 만, read_only 세션). 종목 목록은 표준입력 첫 줄 JSON 배열이 아니라
아래 TICKERS 자리에 붙여 넣어 실행한다(extract.py 결과의 funnel step3 survived_tickers 합집합).
실행: docker compose -f docker-compose.prod.yml exec -T backend python - < extract_etf_universe.py
"""
import asyncio, json, os, ssl
from urllib.parse import urlsplit, urlunsplit, parse_qs

TICKERS = __TICKERS__


async def main():
    import asyncpg
    p = urlsplit(os.environ["DATABASE_URL"]); q = parse_qs(p.query); q.pop("sslmode", None)
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(urlunsplit((p.scheme, p.netloc, p.path, "&".join(f"{k}={v[0]}" for k, v in q.items()), "")), ssl=ctx)
    try:
        await conn.execute("SET default_transaction_read_only = on")
        rows = await conn.fetch(
            """SELECT d.ticker, d.bas_dd::text AS d, d.open_price o, d.high_price h, d.low_price l, d.close_price c,
                      m.name
               FROM stock_master_daily d LEFT JOIN stock_master m ON m.ticker = d.ticker
               WHERE d.ticker = ANY($1::text[]) AND d.bas_dd BETWEEN '2026-08-20' AND '2026-10-10'
               ORDER BY d.ticker, d.bas_dd""", TICKERS)
    finally:
        await conn.close()
    print(json.dumps([dict(r) for r in rows], ensure_ascii=False))

asyncio.run(main())
