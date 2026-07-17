"""market_regime_snapshots CRUD — 사이클 2 (2026-05-17, 시장 레짐 필터).

테이블: ``market_regime_snapshots`` (supabase/migrations/022).
PK: ``id`` (uuid 자동). UNIQUE: ``snapshot_date``.

용도: _boot (07:50) 시점 dkstock.cloud 매크로 응답 1행 영구 저장.
운영자가 사후 회고/디버깅/Grafana 분석에 사용.

사이클 M1-2 (Supabase→RDS 이전 단계1 증분2): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존.

핵심 안전 원칙:
- 중복 INSERT (UNIQUE 충돌) 는 None 반환 (graceful — _boot 중복 호출 안전)
- 외부 매크로 fetch 실패 시 호출자(MarketRegime.refresh)가 흡수 → 본 모듈 호출 안 함
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)

TABLE_NAME = "market_regime_snapshots"


def _now_iso() -> str:
    """사이클 68 G-8 — KST ISO 문자열 반환 (UTC 폐기)."""
    return now_kst_iso()


async def insert_snapshot(
    snapshot_date: date,
    regime: str,
    regime_desc: Optional[str],
    cycle_phase: Optional[str],
    vix: Optional[float],
    fear_greed_score: Optional[float],
    buffett_ratio: Optional[float],
    raw_response: dict[str, Any],
    computed_cash_usage_ratio: Optional[float],
    buy_blocked: bool,
    block_reason: Optional[str],
) -> Optional[dict]:
    """market_regime_snapshots 1 row INSERT.

    동일 ``snapshot_date`` 가 이미 있으면 UNIQUE 충돌 → None (graceful).
    """
    # M6 — snapshot_date DATE 컬럼 바인딩. str 입력도 date 로 강제 변환.
    bound_snapshot_date = to_date(snapshot_date)

    # 사전 중복 확인
    existing = await pg.fetch(
        "SELECT id FROM market_regime_snapshots WHERE snapshot_date = $1",
        bound_snapshot_date,
    )
    if existing:
        logger.info("market_regime_snapshots 중복 skip: %s", snapshot_date)
        return None

    row_id = str(uuid.uuid4())
    sql = """
        INSERT INTO market_regime_snapshots (
            id, snapshot_date, regime, regime_desc, cycle_phase,
            vix, fear_greed_score, buffett_ratio, raw_response,
            computed_cash_usage_ratio, buy_blocked, block_reason, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13)
        RETURNING *
    """
    try:
        row = await pg.fetchrow(
            sql,
            row_id,
            bound_snapshot_date,
            regime,
            regime_desc,
            cycle_phase,
            vix,
            fear_greed_score,
            buffett_ratio,
            dict(raw_response or {}),
            computed_cash_usage_ratio,
            bool(buy_blocked),
            block_reason,
            datetime.fromisoformat(now_kst_iso()),
        )
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            logger.warning("market_regime_snapshots UNIQUE 충돌 (race): %s", snapshot_date)
            return None
        logger.exception("market_regime_snapshots INSERT 실패: %s", snapshot_date)
        return None

    if row:
        logger.info(
            "[market_regime_snapshot] insert: %s regime=%s buy_blocked=%s",
            snapshot_date, regime, buy_blocked,
        )
        return row
    return None


async def get_by_date(snapshot_date: date) -> Optional[dict]:
    """단일 영업일 조회."""
    try:
        return await pg.fetchrow(
            "SELECT * FROM market_regime_snapshots WHERE snapshot_date = $1 LIMIT 1",
            to_date(snapshot_date),
        )
    except Exception:
        logger.exception("market_regime_snapshots get_by_date 실패: %s", snapshot_date)
        return None


async def get_latest() -> Optional[dict]:
    """가장 최근 snapshot_date 1행."""
    try:
        return await pg.fetchrow(
            "SELECT * FROM market_regime_snapshots ORDER BY snapshot_date DESC LIMIT 1",
        )
    except Exception:
        logger.exception("market_regime_snapshots get_latest 실패")
        return None


async def list_recent(days: int = 30) -> list[dict]:
    """최근 N 영업일 신규순 조회 (Dashboard sparkline 용)."""
    try:
        rows = await pg.fetch(
            "SELECT * FROM market_regime_snapshots ORDER BY snapshot_date DESC LIMIT $1",
            days,
        )
    except Exception:
        logger.exception("market_regime_snapshots list_recent 실패")
        return []
    return rows or []
