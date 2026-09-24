"""cycle352 — LTV 체결 전수 + 해당 종목 일봉(D-1..D+3) 덤프 (읽기 전용, SELECT 만).

출력 = JSON 한 덩어리(stdout). 분석은 로컬에서 한다.
"""
import asyncio, os, json
import asyncpg

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")

async def main():
    c = await asyncpg.connect(DSN)
    trades = await c.fetch("""
        SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS') AS ts_kst,
               ticker, ticker_name, trade_type, price::float8 AS price, quantity,
               profit_loss::float8 AS pl, status, order_no
        FROM trade_history
        WHERE strategy='long_tail_volatility' AND status='COMPLETED'
        ORDER BY timestamp""")
    tickers = sorted({r["ticker"] for r in trades})
    bars = await c.fetch("""
        SELECT ticker, to_char(bas_dd,'YYYY-MM-DD') AS d, open_price, high_price, low_price,
               close_price, volume, trade_value, change_rate::float8 AS chg
        FROM stock_master_daily WHERE ticker = ANY($1::text[]) ORDER BY ticker, bas_dd""", tickers)
    logs = await c.fetch("""
        SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS') AS ts, log_level, message
        FROM system_logs
        WHERE message LIKE '%long_tail_volatility%' OR message LIKE '%롱테일%' OR message LIKE '%트레일링 스탑 모드%'
           OR message LIKE '%익일 청산%'
        ORDER BY timestamp""")
    out = {
        "trades": [dict(r) for r in trades],
        "bars": [dict(r) for r in bars],
        "logs": [dict(r) for r in logs],
    }
    print(json.dumps(out, ensure_ascii=False, default=str))
    await c.close()

asyncio.run(main())
