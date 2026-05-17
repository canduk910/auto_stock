"""market_regime_snapshots CRUD — 사이클 2 (2026-05-17, 시장 레짐 필터).

테이블: ``market_regime_snapshots`` (supabase/migrations/022).
PK: ``id`` (uuid 자동). UNIQUE: ``snapshot_date``.

용도: _boot (07:50) 시점 dkstock.cloud 매크로 응답 1행 영구 저장.
운영자가 사후 회고/디버깅/Grafana 분석에 사용.

핵심 안전 원칙:
- supabase 동기 SDK 호출은 모두 ``asyncio.to_thread`` 위임 (src/db/CLAUDE.md 규약)
- 중복 INSERT (UNIQUE 충돌) 는 None 반환 (graceful — _boot 중복 호출 안전)
- 외부 매크로 fetch 실패 시 호출자(MarketRegime.refresh)가 흡수 → 본 모듈 호출 안 함
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from src.db.supabase import supabase

logger = logging.getLogger(__name__)

TABLE_NAME = "market_regime_snapshots"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    # 사전 중복 확인 (FakeSupabase + 운영 supabase 양쪽 호환)
    existing = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME)
        .select("id")
        .eq("snapshot_date", snapshot_date.isoformat())
        .execute()
    )
    if existing.data:
        logger.info("market_regime_snapshots 중복 skip: %s", snapshot_date)
        return None

    row = {
        "id": str(uuid.uuid4()),
        "snapshot_date": snapshot_date.isoformat(),
        "regime": regime,
        "regime_desc": regime_desc,
        "cycle_phase": cycle_phase,
        "vix": vix,
        "fear_greed_score": fear_greed_score,
        "buffett_ratio": buffett_ratio,
        "raw_response": dict(raw_response or {}),
        "computed_cash_usage_ratio": computed_cash_usage_ratio,
        "buy_blocked": bool(buy_blocked),
        "block_reason": block_reason,
        "created_at": _now_iso(),
    }
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME).insert(row).execute()
        )
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            logger.warning("market_regime_snapshots UNIQUE 충돌 (race): %s", snapshot_date)
            return None
        logger.exception("market_regime_snapshots INSERT 실패: %s", snapshot_date)
        return None

    if result.data:
        logger.info(
            "[market_regime_snapshot] insert: %s regime=%s buy_blocked=%s",
            snapshot_date, regime, buy_blocked,
        )
        return result.data[0]
    return row


async def get_by_date(snapshot_date: date) -> Optional[dict]:
    """단일 영업일 조회."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("*")
            .eq("snapshot_date", snapshot_date.isoformat())
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("market_regime_snapshots get_by_date 실패: %s", snapshot_date)
        return None
    rows = result.data or []
    return rows[0] if rows else None


async def get_latest() -> Optional[dict]:
    """가장 최근 snapshot_date 1행."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("*")
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("market_regime_snapshots get_latest 실패")
        return None
    rows = result.data or []
    return rows[0] if rows else None


async def list_recent(days: int = 30) -> list[dict]:
    """최근 N 영업일 신규순 조회 (Dashboard 사parkline 용)."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("*")
            .order("snapshot_date", desc=True)
            .limit(days)
            .execute()
        )
    except Exception:
        logger.exception("market_regime_snapshots list_recent 실패")
        return []
    return result.data or []
