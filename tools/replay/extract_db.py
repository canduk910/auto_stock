#!/usr/bin/env python3
"""평균회귀 연구(트랙 R) — 운영 DB 읽기 전용 추출.

READ-ONLY. 세션을 ``default_transaction_read_only = on`` 으로 열고 SELECT 만 한다.
INSERT/UPDATE/DELETE 0. 분석은 하지 않는다 — 운영 컨테이너에는 statsmodels 가 없다
(지시서 ``_workspace/design/2026-10-01_mean_reversion_handoff.md`` §3.1).

출력 = 표준출력에 JSON Lines. 한 줄 = ``{"section": ..., "row": [...]}``, 첫 줄은 열 이름.

실행 (기존 도구 ``tools/kojiro_live_review.py`` 와 같은 방식):
    ssh auto-stock 'cd ~/auto_stock && docker compose -f docker-compose.prod.yml exec -T backend python -' \
        < tools/replay/extract_db.py | gzip > mr_db_extract.jsonl.gz
"""
from __future__ import annotations

import asyncio
import json
import os
import ssl as ssl_mod
import sys
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit, urlunsplit

SECTIONS: "list[tuple[str, str]]" = [
    ("daily", """
        SELECT ticker, bas_dd, open_price, high_price, low_price, close_price,
               volume, trade_value, change_rate, updated_at
        FROM stock_master_daily ORDER BY ticker, bas_dd
    """),
    ("master", """
        SELECT ticker, name, excg_dvsn_cd, raw->>'mket_id_cd' AS mket_id_cd,
               raw->>'scty_grp_id_cd' AS scty_grp_id_cd, hts_avls_eok
        FROM stock_master
    """),
    ("trades", """
        SELECT timestamp, ticker, trade_type, price, quantity, profit_loss, status,
               strategy, order_no
        FROM trade_history WHERE status IN ('COMPLETED', 'PARTIAL') ORDER BY timestamp
    """),
    ("strategy_config", """
        SELECT strategy_id, enabled, weight FROM strategy_config
    """),
    ("perf_total", """
        SELECT date, strategy, total_asset FROM daily_performance ORDER BY date
    """),
]


def _prep_dsn(dsn: str):
    parts = urlsplit(dsn)
    q = parse_qs(parts.query)
    sslmode = q.pop("sslmode", ["require"])[0]
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path,
                        "&".join(f"{k}={v[0]}" for k, v in q.items()), parts.fragment))
    ctx = None
    if sslmode in ("require", "prefer", "allow", "verify-ca", "verify-full"):
        ctx = ssl_mod.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl_mod.CERT_NONE
    return clean, ctx


def _j(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL") or ""
    if not dsn:
        print(json.dumps({"section": "error", "row": ["DATABASE_URL missing"]}))
        sys.exit(1)
    import asyncpg

    clean, ctx = _prep_dsn(dsn)
    conn = await asyncpg.connect(clean, ssl=ctx)
    try:
        await conn.execute("SET default_transaction_read_only = on")
        for name, sql in SECTIONS:
            # 커서로 흘려 보낸다 — 운영 박스(2GB) 메모리에 전량을 올리지 않는다.
            try:
                async with conn.transaction(readonly=True):
                    first = True
                    async for r in conn.cursor(sql, prefetch=2000):
                        if first:
                            print(json.dumps({"section": name, "cols": list(r.keys())}))
                            first = False
                        print(json.dumps({"section": name, "row": [_j(v) for v in r.values()]},
                                         ensure_ascii=False))
            except Exception as e:  # noqa: BLE001 — 섹션별 graceful
                print(json.dumps({"section": name, "error": f"{type(e).__name__}: {e}"}))
            sys.stdout.flush()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
