"""거래일지 워커 진입점 — ``python -m jw run`` | ``python -m jw backfill``."""
from __future__ import annotations

import asyncio
import os
import sys


async def _run_forever():
    import asyncpg

    from jw.config import BASE_URL, LOG_DIR
    from jw.db import JournalDB
    from jw.http import build_client
    from jw.main import Worker, run_forever

    dsn = os.environ.get("JOURNAL_DATABASE_URL")
    reporter_key = os.environ.get("API_REPORTER_KEY")
    pool = await asyncpg.create_pool(dsn)
    client = build_client(base_url=BASE_URL, reporter_key=reporter_key)
    db = JournalDB(pool)
    worker = Worker(client=client, db=db, log_dir=LOG_DIR)
    try:
        await run_forever(worker.rotate)
    finally:
        await client.aclose()
        await pool.close()


def _run_backfill():
    from jw import backfill as backfill_mod  # noqa: F401 — "backfill" 분기 안에서만 import

    raise SystemExit("backfill 은 docker compose run --rm journal_worker backfill 로 수동 실행한다")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "run"
    if cmd == "backfill":
        _run_backfill()
    else:
        asyncio.run(_run_forever())


if __name__ == "__main__":
    main()
