"""거래일지 워커 진입점 — ``python -m jw run`` | ``python -m jw backfill <경로…>``."""
from __future__ import annotations

import asyncio
import logging
import os
import sys


_USAGE = "usage: python -m jw backfill <log-path> [<log-path> ...]"


def _setup_logging():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s")
    # httpx 는 요청마다 INFO 1줄을 남긴다(하루 약 6,600줄) — jw.* 의 INFO 는 그대로 두고 httpx 만 낮춘다.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _pool():
    import asyncpg

    return await asyncpg.create_pool(os.environ.get("JOURNAL_DATABASE_URL"), min_size=1, max_size=2)


async def _run_forever():
    from jw.config import BASE_URL, LOG_DIR
    from jw.db import JournalDB
    from jw.http import build_client
    from jw.main import Worker, run_forever

    pool = await _pool()
    client = build_client(base_url=BASE_URL, reporter_key=os.environ.get("API_REPORTER_KEY"))
    try:
        await run_forever(Worker(client=client, db=JournalDB(pool), log_dir=LOG_DIR).rotate)
    finally:
        await client.aclose()
        await pool.close()


async def _backfill(paths):
    from jw import backfill as backfill_mod
    from jw.db import JournalDB

    pool = await _pool()
    try:
        res = await backfill_mod.run_backfill(paths, JournalDB(pool))
        logging.getLogger("jw.backfill").info("[journal_backfill] %s", res)
    finally:
        await pool.close()


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "run"
    _setup_logging()
    if cmd == "backfill":
        if len(argv) < 2:
            print(_USAGE, file=sys.stderr)
            raise SystemExit(2)
        asyncio.run(_backfill(argv[1:]))
    else:
        asyncio.run(_run_forever())


if __name__ == "__main__":
    main()
