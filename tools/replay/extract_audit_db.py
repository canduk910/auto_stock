#!/usr/bin/env python3
"""운용 전략 전수 점검(2026-10-05) — 운영 DB 읽기 전용 추출. (평균회귀 extract_db.py 와 같은 방식)

READ-ONLY. 세션을 ``default_transaction_read_only = on`` 으로 열고 SELECT 만 한다.
INSERT/UPDATE/DELETE 0. 분석은 하지 않는다 — 운영 컨테이너에는 statsmodels 가 없다
(지시서 ``_workspace/design/2026-10-01_mean_reversion_handoff.md`` §3.1).

출력 = 표준출력에 JSON Lines. 한 줄 = ``{"section": ..., "row": [...]}``, 첫 줄은 열 이름.

실행 (기존 도구 ``tools/kojiro_live_review.py`` 와 같은 방식):
    ssh auto-stock 'cd ~/auto_stock && docker compose -f docker-compose.prod.yml exec -T backend python -' \
        < tools/replay/extract_audit_db.py | gzip > audit_db_extract.jsonl.gz
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
    ("trades_all", """
        SELECT * FROM trade_history ORDER BY timestamp
    """),
    ("strategy_config", """
        SELECT * FROM strategy_config ORDER BY strategy_id
    """),
    ("param_recs", """
        SELECT id, created_at, target_date, strategy_id, current_params, recommended_params,
               status, applied_params, applied_at, rejected_at
        FROM parameter_recommendations ORDER BY target_date, strategy_id
    """),
    ("positions", """
        SELECT * FROM positions
    """),
    ("perf", """
        SELECT * FROM daily_performance ORDER BY date, strategy
    """),
    ("system_config", """
        SELECT * FROM system_config
    """),
    ("master", """
        SELECT ticker, name, excg_dvsn_cd, hts_avls_eok, nxt_tradable, is_kospi200, is_kosdaq150,
               raw->>'mket_id_cd' AS mket_id_cd, raw->>'scty_grp_id_cd' AS scty_grp_id_cd,
               master_raw->>'scty_grp_id_cd' AS scty_grp_id_cd_master,
               master_raw
        FROM stock_master ORDER BY ticker
    """),
    ("daily", """
        SELECT ticker, bas_dd, open_price, high_price, low_price, close_price,
               volume, trade_value, change_rate, flng_cls_code, prtt_rate, updated_at
        FROM stock_master_daily WHERE bas_dd >= DATE '2025-09-01' ORDER BY ticker, bas_dd
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
    if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
        return v
    return str(v)  # UUID 등


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
