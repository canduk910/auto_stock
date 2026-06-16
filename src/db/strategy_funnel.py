"""strategy_funnel_snapshots CRUD — 조건검색 단계별 후보 영구 추적 (사이클 34, 2026-05-21).

배경:
- 사용자 5/21 15:26 funnel 결함 (donchian 111→0 / BFB 30→0 / VCP 113→0) 시 단계별 살아남은
  종목 + 탈락 사유를 알 수 없어 디버깅 곤란.

본 모듈:
- `insert_snapshot(target_date, strategy_id, step_no, step_name, ...)` — 단일 단계 1행 INSERT
  + JSONB cap 자동 적용 (survived 200 / excluded 20)
- `list_snapshots(target_date, strategy_id=None)` — 단일 영업일 모든 단계 조회 (step_no ASC)
- `list_recent_by_strategy(strategy_id, days=7)` — 추이 분석용 (target_date DESC)

자금 안전: 본 모듈은 진단/추적 전용. 매매 동작 영향 0.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.db.supabase import supabase

logger = logging.getLogger(__name__)

TABLE_NAME = "strategy_funnel_snapshots"

# JSONB cap (응답 크기 + 저장 크기 보호)
SURVIVED_TICKERS_CAP = 200
EXCLUDED_SAMPLE_CAP = 20

# KST 영업일 비교용
_KST_TZ = timezone(timedelta(hours=9))


async def insert_snapshot(
    *,
    target_date: date,
    strategy_id: str,
    step_no: int,
    step_name: str,
    survived_tickers: list | None = None,  # list[str | dict] 모두 허용 (사이클 41)
    excluded_sample: list[dict[str, Any]] | None = None,
    survived_count: int | None = None,
    excluded_count: int = 0,
    step_conditions: str | None = None,  # 사이클 41 — 단계 조건 (UI 툴팁)
) -> dict | None:
    """1단계 snapshot UPSERT (사이클 145 — UPSERT 전환 영구 영속).

    Args:
        target_date: 영업일 (KST).
        strategy_id: 전략 ID (donchian_swing / bull_flag_breakout / vcp_breakout / momentum / ...).
        step_no: 단계 번호 (1, 2, 3, ...).
        step_name: 단계 이름 (UI 명세와 정확히 일치).
        survived_tickers: 단계 통과 종목 리스트.
            - 사이클 34: list[str] (`["005930", ...]`).
            - 사이클 41 (2026-05-22): list[dict] (`[{"ticker": "...", "name": "..."}]`) 도 허용.
            JSONB cap 200 자동 적용. 하위 호환 — DB 응답 시 호출자가 형식 분기 처리.
        excluded_sample: 탈락 종목 sample.
            - 사이클 34: `[{"ticker": str, "reason": str}, ...]`.
            - 사이클 41: `[{"ticker": str, "name": str, "reason": str}, ...]` 권장 (종목명 추가).
            cap 20 자동 적용.
        survived_count: 통과 카운트 (None 이면 len(survived_tickers) 사용).
        excluded_count: 탈락 카운트.
        step_conditions: 단계 필터 조건 (UI 툴팁용, 사이클 41). DB 저장 안 함 (API 응답만).

    Returns:
        upsert 된 row dict (id 포함) 또는 None (실패 시).

    Note:
        사이클 145 (2026-06-16) — UPSERT 전환 영구 영속 (결함 3 시정).
        - 사이클 34 시점 = `.insert(row)` + UNIQUE `(target_date, strategy_id, step_no, snapshot_at)`
          → snapshot_at 매번 갱신 → 중복 INSERT 가능 → 운영 DB 영역 영구 영속 6/15 BFB step_no=1 = 8 row 결함.
        - 사이클 145 시정 = `.upsert(on_conflict="target_date,strategy_id,step_no")` 전환
          + migration 035 영역 영구 영속 UNIQUE 변경 (snapshot_at 키 폐기).
        - 같은 (target_date, strategy_id, step_no) 영역 영구 영속 = 최신 값 영구 영속 1 row.
        - snapshot_at 영역 영구 영속 = supabase DEFAULT now() (UPSERT 시 자동 갱신).
        - 매매 안전성 무영향 (진단/추적 영역 한정).
    """
    if not strategy_id:
        raise ValueError("strategy_id 필수")

    survived = list(survived_tickers or [])[:SURVIVED_TICKERS_CAP]
    excluded = list(excluded_sample or [])[:EXCLUDED_SAMPLE_CAP]

    if survived_count is None:
        survived_count = len(survived)

    # 사이클 145 — UPSERT 영역 영구 영속 (id 영역 영구 영속 conflict 시 EXCLUDED.id 영구 영속 유지).
    # snapshot_at = supabase DEFAULT now() (사이클 145 — UPSERT 시 자동 갱신, 최신 시각만 영구 영속).
    row = {
        "id": str(uuid.uuid4()),
        "target_date": target_date.isoformat(),
        "strategy_id": strategy_id,
        "step_no": int(step_no),
        "step_name": step_name,
        "survived_count": int(survived_count),
        "excluded_count": int(excluded_count),
        "survived_tickers": survived,
        "excluded_sample": excluded,
    }

    try:
        # 사이클 145 — `.upsert(on_conflict="target_date,strategy_id,step_no")` 영역 영구 영속.
        # migration 035 UNIQUE = (target_date, strategy_id, step_no) 정합 영구 영속.
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME).upsert(
                row,
                on_conflict="target_date,strategy_id,step_no",
            ).execute()
        )
        data = getattr(result, "data", None) or []
        return data[0] if data else None
    except Exception as exc:
        logger.warning(
            "strategy_funnel upsert 실패 — target=%s strategy=%s step=%d err=%s",
            target_date, strategy_id, step_no, exc,
        )
        return None


async def list_snapshots(
    *,
    target_date: date,
    strategy_id: str | None = None,
) -> list[dict]:
    """단일 영업일 snapshot 조회 (step_no ASC).

    Args:
        target_date: 영업일.
        strategy_id: 단일 전략 필터 (None 이면 전체).

    Returns:
        snapshot row list. 응답 cap 없음 (전략당 단계 수 ≤ 10 가정).
    """
    def _query():
        q = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("target_date", target_date.isoformat())
            .order("step_no")
        )
        if strategy_id:
            q = q.eq("strategy_id", strategy_id)
        return q.execute()

    try:
        result = await asyncio.to_thread(_query)
        return getattr(result, "data", None) or []
    except Exception as exc:
        logger.warning(
            "strategy_funnel list 실패 — target=%s strategy=%s err=%s",
            target_date, strategy_id, exc,
        )
        return []


async def list_recent_by_strategy(
    strategy_id: str,
    days: int = 7,
) -> list[dict]:
    """특정 전략의 최근 N일 snapshot 추이 조회 (target_date DESC).

    Args:
        strategy_id: 전략 ID.
        days: 최근 N일 (기본 7).

    Returns:
        snapshot row list — target_date DESC, step_no ASC.
    """
    if days <= 0:
        return []

    today_kst = datetime.now(_KST_TZ).date()
    from_date = today_kst - timedelta(days=days - 1)

    def _query():
        return (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("strategy_id", strategy_id)
            .gte("target_date", from_date.isoformat())
            .lte("target_date", today_kst.isoformat())
            .order("target_date", desc=True)
            .order("step_no")
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        return getattr(result, "data", None) or []
    except Exception as exc:
        logger.warning(
            "strategy_funnel recent 실패 — strategy=%s err=%s",
            strategy_id, exc,
        )
        return []
