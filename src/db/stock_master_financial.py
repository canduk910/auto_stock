"""사이클 C1 (2026-07-15) — stock_master_financial CRUD.

퀀트 재무필터 (마법공식 + F-Score-7) 데이터 계층. `src/db/stock_master_daily.py`
100% 미러 (사이클 122 답습).

영속 의무:
- 사이클 30 trade_history ON CONFLICT 답습 (PK 복합 키 패턴)
- 사이클 68 KST 영속 (`src/db/_kst.py` 헬퍼 의무)
- 사이클 81 G-AST1 raw JSONB 영속
- 사이클 88 G-REJECT graceful 단위 의무
- 사이클 187 read 함수 `execute_with_retry` 경유
- 매매 안전성 무영향 — scanner 단계 매수 진입 전 영역만 (사이클 38)

supabase 동기 SDK 호출은 모두 `asyncio.to_thread()` 위임.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.db._kst import now_kst_iso
from src.db.supabase import supabase, execute_with_retry

logger = logging.getLogger(__name__)

TABLE_NAME = "stock_master_financial"

# Batch upsert 단위 — Supabase HTTP/2 stale connection 회피 (사이클 26 답습)
_BATCH_SIZE = 100


def _safe_float(value, default: float = 0.0) -> float:
    """문자열/숫자 → float 변환. 빈 값/예외 시 default 반환 (graceful)."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """문자열/숫자 → int 변환. 빈 값/예외 시 default 반환 (graceful)."""
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


async def upsert_financial_batch(ticker: str, rows: list[dict]) -> int:
    """재무 row batch upsert — 100건 chunk + ON CONFLICT PK 3키 + graceful.

    Args:
        ticker: KRX 6자리 단축코드 (row 내 ticker 는 호출자가 이미 채움).
        rows: 정규화 재무 row list (스키마 컬럼명, `stac_yymm`/`div_cls` 포함).

    Returns:
        upsert 성공 건수 (graceful 실패 chunk 는 제외 카운트).

    영속 의무:
    - 사이클 26 Supabase HTTP/2 stale connection 회피 (batch 100건)
    - 사이클 88 G-REJECT graceful (개별 chunk 실패 시 다음 chunk 진행)
    - 사이클 68 KST refreshed_at (now_kst_iso 경유)
    """
    if not rows:
        return 0

    stamped_rows = []
    for row in rows:
        r = dict(row)
        r["refreshed_at"] = now_kst_iso()
        stamped_rows.append(r)

    total_upserted = 0
    for i in range(0, len(stamped_rows), _BATCH_SIZE):
        chunk = stamped_rows[i:i + _BATCH_SIZE]
        try:
            await asyncio.to_thread(
                lambda c=chunk: supabase.table(TABLE_NAME)
                .upsert(c, on_conflict="ticker,stac_yymm,div_cls")
                .execute()
            )
            total_upserted += len(chunk)
        except Exception:
            # 사이클 88 G-REJECT graceful — 개별 chunk 실패 시 다음 chunk 진행
            logger.exception(
                "[stock_master_financial] upsert_financial_batch ticker=%s "
                "chunk_start=%d 실패 graceful",
                ticker, i,
            )

    return total_upserted


async def get_financial_series(
    ticker: str, div_cls: str = "0", limit: int = 3
) -> list[dict]:
    """최근 N기 재무 시계열 조회 — stac_yymm DESC.

    Args:
        ticker: KRX 6자리 단축코드.
        div_cls: "0"=년/"1"=분기.
        limit: 조회 기수.

    Returns:
        list[dict] — raw row. 미존재/예외 시 빈 list (graceful).
    """
    try:
        result = await execute_with_retry(
            lambda: supabase.table(TABLE_NAME)
            .select("*")
            .eq("ticker", ticker)
            .eq("div_cls", div_cls)
            .order("stac_yymm", desc=True)
            .limit(limit)
            .execute(),
            op="get_financial_series",
        )
        return result.data or []
    except Exception:
        # 사이클 88 G-REJECT graceful
        logger.exception(
            "[stock_master_financial] get_financial_series 실패 graceful ticker=%s",
            ticker,
        )
        return []


async def max_stac_yymm(ticker: str, div_cls: str = "0") -> Optional[str]:
    """최신 stac_yymm 조회 — 백필/증분 분기 키.

    Args:
        ticker: KRX 6자리 단축코드.
        div_cls: "0"=년/"1"=분기.

    Returns:
        str — 최신 stac_yymm. 미존재/예외 시 None (graceful).
    """
    try:
        result = await execute_with_retry(
            lambda: supabase.table(TABLE_NAME)
            .select("stac_yymm")
            .eq("ticker", ticker)
            .eq("div_cls", div_cls)
            .order("stac_yymm", desc=True)
            .limit(1)
            .execute(),
            op="max_stac_yymm",
        )
        rows = result.data or []
        if not rows:
            return None
        return rows[0].get("stac_yymm")
    except Exception:
        logger.exception(
            "[stock_master_financial] max_stac_yymm 실패 graceful ticker=%s",
            ticker,
        )
        return None


async def count_all() -> int:
    """전체 행 카운트 (진단 + 운영 모니터링)."""
    try:
        result = await execute_with_retry(
            lambda: supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .limit(1)
            .execute(),
            op="count_all",
        )
        if hasattr(result, "count") and result.count is not None:
            return int(result.count)
        return len(result.data or [])
    except Exception:
        logger.exception("[stock_master_financial] count_all 실패 graceful")
        return 0
