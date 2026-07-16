"""사이클 C1 (2026-07-15) — stock_master_financial CRUD.

퀀트 재무필터 (마법공식 + F-Score-7) 데이터 계층. `src/db/stock_master_daily.py`
100% 미러 (사이클 122 답습).

사이클 M3a (Supabase→RDS 이전 단계3, 분석·관찰 비 hot-path): supabase-py → `src.db.pg`
(asyncpg) 전환. 함수 시그니처·반환형·graceful 100% 보존 — 호출부 diff 0.

영속 의무:
- 사이클 30 trade_history ON CONFLICT 답습 (PK 복합 키 패턴)
- 사이클 68 KST 영속 (`src/db/_kst.py` 헬퍼 의무)
- 사이클 81 G-AST1 raw JSONB 영속
- 사이클 88 G-REJECT graceful 단위 의무
- 사이클 187 read 함수 retry 정책 계승 (`pg.fetch`/`pg.fetchval` 내부 `pg._with_retry` 경유)
- 매매 안전성 무영향 — scanner 단계 매수 진입 전 영역만 (사이클 38)
"""

from __future__ import annotations

import asyncio  # noqa: F401 — Red autouse fixture 호환(monkeypatch.setattr(smf.asyncio, ...))
import logging
from datetime import datetime
from typing import Optional

import src.db.pg as pg
from src.db._kst import now_kst_iso

logger = logging.getLogger(__name__)

TABLE_NAME = "stock_master_financial"

# Batch upsert 단위 — Supabase HTTP/2 stale connection 회피 (사이클 26 답습)
_BATCH_SIZE = 100

_UPSERT_SQL = f"""
    INSERT INTO {TABLE_NAME} (
        ticker, stac_yymm, div_cls, sale_account, sale_totl_prfi, bsop_prti,
        thtr_ntin, depr_cost, cras, fxas, total_aset, flow_lblt, total_lblt,
        total_cptl, cpfn, cptl_ntin_rate, sale_totl_rate, lblt_rate, crnt_rate,
        ebitda, ev_ebitda, raw, refreshed_at
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
        $17, $18, $19, $20, $21, $22::jsonb, $23
    )
    ON CONFLICT (ticker, stac_yymm, div_cls) DO UPDATE SET
        sale_account = EXCLUDED.sale_account,
        sale_totl_prfi = EXCLUDED.sale_totl_prfi,
        bsop_prti = EXCLUDED.bsop_prti,
        thtr_ntin = EXCLUDED.thtr_ntin,
        depr_cost = EXCLUDED.depr_cost,
        cras = EXCLUDED.cras,
        fxas = EXCLUDED.fxas,
        total_aset = EXCLUDED.total_aset,
        flow_lblt = EXCLUDED.flow_lblt,
        total_lblt = EXCLUDED.total_lblt,
        total_cptl = EXCLUDED.total_cptl,
        cpfn = EXCLUDED.cpfn,
        cptl_ntin_rate = EXCLUDED.cptl_ntin_rate,
        sale_totl_rate = EXCLUDED.sale_totl_rate,
        lblt_rate = EXCLUDED.lblt_rate,
        crnt_rate = EXCLUDED.crnt_rate,
        ebitda = EXCLUDED.ebitda,
        ev_ebitda = EXCLUDED.ev_ebitda,
        raw = EXCLUDED.raw,
        refreshed_at = EXCLUDED.refreshed_at
"""

_NUMERIC_COLUMNS = (
    "sale_account", "sale_totl_prfi", "bsop_prti", "thtr_ntin", "depr_cost",
    "cras", "fxas", "total_aset", "flow_lblt", "total_lblt", "total_cptl",
    "cpfn", "cptl_ntin_rate", "sale_totl_rate", "lblt_rate", "crnt_rate",
    "ebitda", "ev_ebitda",
)


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


def _row_to_args(row: dict, refreshed_at: datetime) -> tuple:
    return (
        row["ticker"],
        row["stac_yymm"],
        row["div_cls"],
        *(row.get(col) for col in _NUMERIC_COLUMNS),
        row.get("raw") or {},
        refreshed_at,
    )


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

    refreshed_at = datetime.fromisoformat(now_kst_iso())
    args_list = [_row_to_args(row, refreshed_at) for row in rows]

    total_upserted = 0
    for i in range(0, len(args_list), _BATCH_SIZE):
        chunk = args_list[i:i + _BATCH_SIZE]
        try:
            await pg.executemany(_UPSERT_SQL, chunk)
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
        rows = await pg.fetch(
            f"SELECT * FROM {TABLE_NAME} WHERE ticker = $1 AND div_cls = $2 "
            f"ORDER BY stac_yymm DESC LIMIT $3",
            ticker, div_cls, limit,
        )
        return rows or []
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
        rows = await pg.fetch(
            f"SELECT stac_yymm FROM {TABLE_NAME} WHERE ticker = $1 AND div_cls = $2 "
            f"ORDER BY stac_yymm DESC LIMIT 1",
            ticker, div_cls,
        )
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
        count = await pg.fetchval(f"SELECT count(*) FROM {TABLE_NAME}")
        return int(count or 0)
    except Exception:
        logger.exception("[stock_master_financial] count_all 실패 graceful")
        return 0
