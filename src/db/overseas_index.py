"""overseas_index_daily CRUD — cycle443(ndx2x_riskoff 전략의 신호 원천).

테이블: ``overseas_index_daily`` (supabase/migrations/048). PK: ``(index_code, bas_dd)``.

용도: KIS FHKST03030100 종가를 영구 보관하고, 전략이 매일 최근 N영업일 종가열을
읽어 T7/R4(규칙 C)를 계산한다. upsert 는 멱등(같은 날짜 재적재 시 close_price 덮어쓰기
허용 — KIS 의 `mod_yn`(수정) 반영, 과거 확정치를 조용히 틀리게 두지 않는다).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)

TABLE_NAME = "overseas_index_daily"


async def upsert_many(index_code: str, rows: list[tuple[str, float]], *, raw_by_date: dict[str, dict] | None = None) -> int:
    """`(YYYYMMDD, 종가)` 목록을 upsert — 멱등(동일 날짜는 `close_price` 덮어쓰기).

    Returns:
        upsert 를 시도한 행 수(성공 건수 — asyncpg `executemany` 는 개별 실패를 구분하지
        않으므로 예외 시 0 을 반환하고 로깅만 한다).
    """
    if not rows:
        return 0
    raw_by_date = raw_by_date or {}
    now_iso = now_kst_iso()
    args_list = []
    for bsop, close in rows:
        bound_date = to_date(datetime.strptime(bsop, "%Y%m%d").date())
        args_list.append((
            index_code, bound_date, close,
            dict(raw_by_date.get(bsop, {})),
            datetime.fromisoformat(now_iso),
        ))
    sql = """
        INSERT INTO overseas_index_daily (index_code, bas_dd, close_price, raw, updated_at)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (index_code, bas_dd) DO UPDATE SET
            close_price = EXCLUDED.close_price,
            raw = EXCLUDED.raw,
            updated_at = EXCLUDED.updated_at
    """
    try:
        await pg.executemany(sql, args_list)
    except Exception:
        logger.exception("overseas_index_daily upsert_many 실패: index_code=%s rows=%d", index_code, len(rows))
        return 0
    return len(args_list)


async def get_recent_closes(index_code: str, *, limit: int = 400) -> list[tuple[date, float]]:
    """최근 `limit` 영업일 종가 — **오름차순(오래된→최신)** 으로 돌린다(지표 계산 입력 순서)."""
    try:
        rows = await pg.fetch(
            """
            SELECT bas_dd, close_price FROM overseas_index_daily
            WHERE index_code = $1
            ORDER BY bas_dd DESC
            LIMIT $2
            """,
            index_code, limit,
        )
    except Exception:
        logger.exception("overseas_index_daily get_recent_closes 실패: %s", index_code)
        return []
    ordered = sorted(rows or [], key=lambda r: r["bas_dd"])
    return [(r["bas_dd"], float(r["close_price"])) for r in ordered]


async def get_latest_date(index_code: str) -> date | None:
    """가장 최근 저장된 `bas_dd`. 없으면 None."""
    try:
        val = await pg.fetchval(
            "SELECT MAX(bas_dd) FROM overseas_index_daily WHERE index_code = $1",
            index_code,
        )
    except Exception:
        logger.exception("overseas_index_daily get_latest_date 실패: %s", index_code)
        return None
    return val
