"""domestic_index_daily CRUD — cycle455(시장 유닛 원천: 코스피·코스닥 종합지수).

테이블: ``domestic_index_daily`` (supabase/migrations/053). PK: ``(index_code, bas_dd)``.
모양은 ``overseas_index.py`` 와 같다. upsert 는 멱등(같은 날짜 재적재 = 덮어쓰기).
DB 예외는 전부 흡수한다(``0``/``[]``/``None`` + ``logger.exception``) — 호출자
(``engine/domestic_index_ingest.py``·``engine/market_unit.py``)가 fail-open 을 판단한다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)

TABLE_NAME = "domestic_index_daily"


async def upsert_many(
    index_code: str, rows: list[tuple[str, float]], *, raw_by_date: dict[str, dict] | None = None,
) -> int:
    """``(YYYYMMDD, 종가)`` 목록 upsert — 멱등. 반환 = 보낸 행 수(빈 입력·예외 = 0)."""
    if not rows:
        return 0
    raw_by_date = raw_by_date or {}
    now_dt = datetime.fromisoformat(now_kst_iso())
    args_list = []
    for bsop, close in rows:
        bound_date = to_date(datetime.strptime(bsop, "%Y%m%d").date())
        args_list.append((index_code, bound_date, close, dict(raw_by_date.get(bsop, {})), now_dt))
    sql = """
        INSERT INTO domestic_index_daily (index_code, bas_dd, close_price, raw, updated_at)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (index_code, bas_dd) DO UPDATE SET
            close_price = EXCLUDED.close_price,
            raw = EXCLUDED.raw,
            updated_at = EXCLUDED.updated_at
    """
    try:
        await pg.executemany(sql, args_list)
    except Exception:
        logger.exception("domestic_index_daily upsert_many 실패: index_code=%s rows=%d", index_code, len(rows))
        return 0
    return len(args_list)


async def get_recent_closes(index_code: str, *, limit: int) -> list[tuple[date, float]]:
    """최근 ``limit`` 행 종가 — **오름차순**(오래된→최신). 예외 = ``[]``."""
    try:
        rows = await pg.fetch(
            """
            SELECT bas_dd, close_price FROM domestic_index_daily
            WHERE index_code = $1
            ORDER BY bas_dd DESC
            LIMIT $2
            """,
            index_code, limit,
        )
    except Exception:
        logger.exception("domestic_index_daily get_recent_closes 실패: %s", index_code)
        return []
    ordered = sorted(rows or [], key=lambda r: r["bas_dd"])
    return [(r["bas_dd"], float(r["close_price"])) for r in ordered]


async def max_bas_dd(index_code: str) -> date | None:
    """가장 최근 ``bas_dd``. 없음·예외 = ``None``."""
    try:
        return await pg.fetchval(
            "SELECT MAX(bas_dd) FROM domestic_index_daily WHERE index_code = $1", index_code,
        )
    except Exception:
        logger.exception("domestic_index_daily max_bas_dd 실패: %s", index_code)
        return None


async def count(index_code: str) -> int:
    """그 지수 행 수. 예외 = 0."""
    try:
        val = await pg.fetchval(
            "SELECT count(*) FROM domestic_index_daily WHERE index_code = $1", index_code,
        )
    except Exception:
        logger.exception("domestic_index_daily count 실패: %s", index_code)
        return 0
    return int(val or 0)
