"""청산 AI 섀도 워커 진입점 — ``python -m lw``."""
from __future__ import annotations

import asyncio
import logging
import os
import sys


def _setup_logging():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


async def _pool():
    import asyncpg

    return await asyncpg.create_pool(os.environ.get("LLM_DATABASE_URL"), min_size=1, max_size=2)


def _build_openai_client():
    key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=key, max_retries=0)


async def _run_forever():
    from lw.config import BASE_URL, EXIT_AI_MODEL_DEFAULT
    from lw.db import ExitAiDB
    from lw.exit_shadow import Runner
    from lw.http import build_client
    from lw.schedule import run_forever

    mode = str(os.environ.get("EXIT_AI_MODE") or "shadow").strip().lower()
    model = str(os.environ.get("EXIT_AI_MODEL") or "").strip() or EXIT_AI_MODEL_DEFAULT

    pool = await _pool()
    client = build_client(base_url=BASE_URL, reporter_key=os.environ.get("API_REPORTER_KEY"))
    openai_client = _build_openai_client() if mode != "off" else None
    runner = Runner(client=client, db=ExitAiDB(pool), openai_client=openai_client, model=model, mode=mode)
    try:
        await run_forever(runner.run_once)
    finally:
        await client.aclose()
        await pool.close()


def main(argv=None) -> None:
    _setup_logging()
    asyncio.run(_run_forever())


if __name__ == "__main__":
    main()
