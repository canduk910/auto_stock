# 읽기 전용 조회 — stock_master 의 ETP 판정 필드(SELECT 만, default_transaction_read_only=on)
import asyncio, os, json
import asyncpg

async def main():
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(dsn, server_settings={"default_transaction_read_only": "on"})
    try:
        ro = await conn.fetchval("SHOW default_transaction_read_only")
        rows = await conn.fetch(
            """
            SELECT ticker, name,
                   raw->>'scty_grp_id_cd'            AS grp,
                   raw->>'etf_txtn_type_cd'          AS txtn,
                   raw->>'etf_chas_erng_rt_dbnb'     AS mult,
                   raw->>'etf_etn_ivst_heed_item_yn' AS heed,
                   raw->>'etf_type_cd'               AS etf_type,
                   raw->>'etf_dvsn_cd'               AS etf_dvsn,
                   hts_avls_eok,
                   refreshed_at
            FROM stock_master
            WHERE raw->>'scty_grp_id_cd' IN ('EF','EN','FE')
            ORDER BY ticker
            """
        )
        total = await conn.fetchval("SELECT count(*) FROM stock_master")
        out = {"read_only": ro, "stock_master_rows": total,
               "rows": [{k: (str(v) if k == "refreshed_at" else v) for k, v in dict(r).items()} for r in rows]}
        print(json.dumps(out, ensure_ascii=False, default=str))
    finally:
        await conn.close()

asyncio.run(main())
